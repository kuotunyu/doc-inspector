"""Reproducible XFUND split, ground truth, OCR baseline, and exact-match metrics."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import random
import re
import subprocess
from tempfile import TemporaryDirectory
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from PIL import Image, ImageOps

XFUND_SEED = 20_260_723


class BenchmarkPair(BaseModel):
    """One key-value pair predicted from a benchmark form."""

    model_config = ConfigDict(extra="forbid")
    key: str
    value: str


class BenchmarkPrediction(BaseModel):
    """Provider-neutral structured prediction for one XFUND image."""

    model_config = ConfigDict(extra="forbid")
    pairs: list[BenchmarkPair] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BenchmarkDocument:
    uid: str
    source_split: str
    image_name: str
    ground_truth: tuple[BenchmarkPair, ...]


@dataclass(frozen=True, slots=True)
class MetricSummary:
    documents: int
    reference_pairs: int
    predicted_pairs: int
    matched_pairs: int
    exact_match_recall: float
    micro_precision: float
    micro_recall: float
    micro_f1: float
    macro_document_f1: float

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


def normalize_metric_text(value: str) -> str:
    """Apply only NFKC, ASCII Latin lowercase, trim, and whitespace collapse."""

    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"))
    return re.sub(r"\s+", " ", normalized).strip()


def ground_truth_pairs(document: dict[str, Any]) -> tuple[BenchmarkPair, ...]:
    """Convert deduplicated question-answer linking edges into ordered pairs."""

    entities = {int(entity["id"]): entity for entity in document["document"]}
    linked_ids: set[tuple[int, int]] = set()
    for entity in document["document"]:
        for raw_link in entity.get("linking", []):
            if not isinstance(raw_link, list) or len(raw_link) != 2:
                continue
            linked_ids.add(tuple(sorted((int(raw_link[0]), int(raw_link[1])))))

    pairs: list[BenchmarkPair] = []
    for left_id, right_id in sorted(linked_ids):
        left = entities.get(left_id)
        right = entities.get(right_id)
        if left is None or right is None:
            continue
        if left.get("label") == "question" and right.get("label") == "answer":
            question, answer = left, right
        elif right.get("label") == "question" and left.get("label") == "answer":
            question, answer = right, left
        else:
            continue
        key = str(question.get("text", "")).strip()
        value = str(answer.get("text", "")).strip()
        if key and value:
            pairs.append(BenchmarkPair(key=key, value=value))
    return tuple(pairs)


def load_xfund_documents(json_path: Path, source_split: str) -> list[BenchmarkDocument]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    documents = []
    for raw in payload["documents"]:
        uid = str(raw.get("uid") or raw["id"])
        documents.append(
            BenchmarkDocument(
                uid=uid,
                source_split=source_split,
                image_name=str(raw["img"]["fname"]),
                ground_truth=ground_truth_pairs(raw),
            )
        )
    return documents


def build_evaluation_split(
    train_documents: list[BenchmarkDocument],
    val_documents: list[BenchmarkDocument],
    *,
    seed: int = XFUND_SEED,
) -> tuple[list[BenchmarkDocument], list[BenchmarkDocument]]:
    """Return 50 train holdout + all 50 val, plus prompt-development train docs."""

    if len(train_documents) != 149 or len(val_documents) != 50:
        raise ValueError("XFUND zh 預期 149 train 與 50 val 文件。")
    ordered_train = sorted(train_documents, key=lambda document: document.uid)
    selected_uids = {
        document.uid for document in random.Random(seed).sample(ordered_train, 50)
    }
    holdout = [document for document in ordered_train if document.uid in selected_uids]
    prompt_development = [document for document in ordered_train if document.uid not in selected_uids]
    evaluation = [*sorted(val_documents, key=lambda document: document.uid), *holdout]
    return evaluation, prompt_development


def split_manifest(
    evaluation: list[BenchmarkDocument],
    prompt_development: list[BenchmarkDocument],
) -> dict[str, object]:
    return {
        "seed": XFUND_SEED,
        "evaluation": [
            {"uid": document.uid, "source_split": document.source_split, "image_name": document.image_name}
            for document in evaluation
        ],
        "prompt_development": [document.uid for document in prompt_development],
    }


def extract_pairs_from_ocr_text(text: str) -> list[BenchmarkPair]:
    """Produce a deliberately simple, transparent Tesseract + regex baseline."""

    pairs: list[BenchmarkPair] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        pieces = re.split(r"\s*[:：=]\s*|\s{2,}", line, maxsplit=1)
        if len(pieces) != 2:
            continue
        key, value = (piece.strip() for piece in pieces)
        if key and value:
            pairs.append(BenchmarkPair(key=key, value=value))
    return pairs


def run_tesseract(image_path: Path, *, executable: str = "tesseract") -> list[BenchmarkPair]:
    """Run the explicit `chi_sim+eng` OCR baseline for one image."""

    # Some official XFUND JPEGs contain recoverable stream warnings that
    # Leptonica rejects. Pillow can decode them, so normalize to a temporary
    # lossless PNG before OCR without retaining source content.
    with TemporaryDirectory(prefix="doc-inspector-ocr-") as temporary:
        normalized_path = Path(temporary) / "page.png"
        with Image.open(image_path) as image:
            ImageOps.exif_transpose(image).convert("RGB").save(normalized_path, format="PNG")
        completed = subprocess.run(
            [
                executable,
                str(normalized_path),
                "stdout",
                "-l",
                "chi_sim+eng",
                "--psm",
                "6",
                "-c",
                "preserve_interword_spaces=1",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    return extract_pairs_from_ocr_text(completed.stdout)


def _normalized_counter(pairs: list[BenchmarkPair] | tuple[BenchmarkPair, ...]) -> Counter[tuple[str, str]]:
    return Counter(
        (normalize_metric_text(pair.key), normalize_metric_text(pair.value))
        for pair in pairs
        if normalize_metric_text(pair.key) and normalize_metric_text(pair.value)
    )


def score_predictions(
    documents: list[BenchmarkDocument],
    predictions: dict[str, list[BenchmarkPair]],
) -> MetricSummary:
    """Score duplicate-aware exact pair matches with micro and macro metrics."""

    total_reference = total_predicted = total_matched = 0
    document_f1: list[float] = []
    for document in documents:
        references = _normalized_counter(document.ground_truth)
        predicted = _normalized_counter(predictions.get(document.uid, []))
        matched = sum((references & predicted).values())
        reference_count = sum(references.values())
        predicted_count = sum(predicted.values())
        total_reference += reference_count
        total_predicted += predicted_count
        total_matched += matched
        precision = matched / predicted_count if predicted_count else 0.0
        recall = matched / reference_count if reference_count else 0.0
        document_f1.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)

    micro_precision = total_matched / total_predicted if total_predicted else 0.0
    micro_recall = total_matched / total_reference if total_reference else 0.0
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if micro_precision + micro_recall
        else 0.0
    )
    return MetricSummary(
        documents=len(documents),
        reference_pairs=total_reference,
        predicted_pairs=total_predicted,
        matched_pairs=total_matched,
        exact_match_recall=micro_recall,
        micro_precision=micro_precision,
        micro_recall=micro_recall,
        micro_f1=micro_f1,
        macro_document_f1=sum(document_f1) / len(document_f1) if document_f1 else 0.0,
    )


def score_by_split(
    documents: list[BenchmarkDocument],
    predictions: dict[str, list[BenchmarkPair]],
) -> dict[str, dict[str, int | float]]:
    """Return val, train holdout, and combined summaries."""

    val = [document for document in documents if document.source_split == "val"]
    holdout = [document for document in documents if document.source_split == "train_holdout"]
    return {
        "val": score_predictions(val, predictions).to_dict(),
        "train_holdout": score_predictions(holdout, predictions).to_dict(),
        "combined": score_predictions(documents, predictions).to_dict(),
    }
