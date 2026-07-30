"""Reproducible offline evaluation for verified evidence provenance.

This benchmark is deliberately separate from the decision-layer regression
suite. That suite measures whether fixed extractions produce the right red /
yellow / green outcome; this one measures whether the system can find the
claimed evidence in the document and, just as importantly, whether it admits it
when it cannot.

Ground truth comes from ``scripts/build_provenance_corpus.py``, which records
page and bounding box from the authored page layout. The runner never writes the
corpus, so an evaluation run can never quietly relabel the data it is scored on.
"""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any, Self

from pydantic import Field, model_validator

from doc_inspector.ingest import normalize_document
from doc_inspector.provenance import (
    build_match_index,
    iter_located_fields,
    resolve_field_provenance,
)
from doc_inspector.schemas import (
    PROVENANCE_VERSION,
    NormalizedBBox,
    ResolutionMethod,
    SchemaRegistry,
    StrictSchemaModel,
    VerificationStatus,
)

REGION_HIT_IOU = 0.5
"""A predicted box counts as a hit only at or above this intersection-over-union."""

GATE_MAX_FALSE_VERIFIED_RATE = 0.0
GATE_MIN_PAGE_ACCURACY = 0.95
GATE_MIN_VERIFIED_BBOX_HIT_RATE = 0.90


class FieldClaim(StrictSchemaModel):
    """The provider claim replayed for one corpus field."""

    value: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    evidence_text: str | None = None
    is_id_type: bool = False
    additional_field_label: str | None = None


class CorpusField(StrictSchemaModel):
    """One scored field: the claim plus the location the generator recorded."""

    field_path: str
    case_type: str
    expected_status: VerificationStatus
    localizable: bool
    claim: FieldClaim
    truth_page: int | None = Field(default=None, ge=1)
    bbox: list[float] | None = None

    @model_validator(mode="after")
    def validate_truth(self) -> Self:
        if self.bbox is not None:
            if len(self.bbox) != 4:
                raise ValueError("ground-truth bbox 必須是四個座標")
            if self.truth_page is None:
                raise ValueError("有 bbox 時必須記錄 truth_page")
        if self.localizable != (self.expected_status in {"verified", "approximate"}):
            raise ValueError("localizable 必須與 expected_status 一致")
        return self

    def truth_bbox(self) -> NormalizedBBox | None:
        if self.bbox is None:
            return None
        x0, y0, x1, y1 = self.bbox
        return NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1)


class CorpusPageGeometry(StrictSchemaModel):
    """Recorded geometry of one authored page."""

    page_number: int = Field(ge=1)
    width_points: float = Field(gt=0)
    height_points: float = Field(gt=0)
    rotation: int
    image_only: bool


class CorpusDocument(StrictSchemaModel):
    """One corpus PDF with its checksum, claims, and ground truth."""

    name: str
    file: str
    sha256: str
    byte_size: int = Field(ge=1)
    schema_name: str
    page_count: int = Field(ge=1)
    note: str
    page_geometry: list[CorpusPageGeometry]
    fields: list[CorpusField]


class CorpusGenerator(StrictSchemaModel):
    """Provenance of the corpus itself."""

    script: str
    library: str
    library_version: str
    mupdf_version: str
    font: str
    font_face: str


class ProvenanceCorpus(StrictSchemaModel):
    """Versioned manifest describing the whole synthetic corpus."""

    corpus_name: str
    version: str
    seed: int
    contains_real_personal_data: bool
    coordinate_space: str
    coordinate_scale: float
    ground_truth_source: str
    generator: CorpusGenerator
    documents: list[CorpusDocument]
    field_count: int = Field(ge=1)
    localizable_field_count: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.contains_real_personal_data:
            raise ValueError("評估語料不得包含真實個資")
        total = sum(len(document.fields) for document in self.documents)
        localizable = sum(
            1
            for document in self.documents
            for item in document.fields
            if item.localizable
        )
        if total != self.field_count or localizable != self.localizable_field_count:
            raise ValueError("manifest 的欄位計數與內容不一致")
        return self


class FieldOutcome(StrictSchemaModel):
    """Expected versus observed provenance for one corpus field."""

    document: str
    field_path: str
    case_type: str
    expected_status: VerificationStatus
    predicted_status: VerificationStatus
    status_matches: bool
    truth_page: int | None = None
    predicted_page: int | None = None
    page_matches: bool
    predicted_bbox: list[float] | None = None
    iou: float | None = None
    region_hit: bool
    resolution_method: ResolutionMethod
    match_score: float | None = None
    candidate_count: int
    false_verified: bool


class ProvenanceMetrics(StrictSchemaModel):
    """Aggregate metrics for the localization contract."""

    field_count: int
    localizable_field_count: int
    claimed_field_count: int
    overall_bbox_coverage: float
    status_exact_matches: int
    status_exact_match_rate: float
    page_localization_correct: int
    page_localization_accuracy: float
    bbox_localization_covered: int
    bbox_localization_coverage: float
    predicted_bbox_count: int
    region_hits: int
    bbox_hit_rate: float
    mean_iou: float
    median_iou: float
    verified_count: int
    verified_region_hits: int
    verified_bbox_hit_rate: float
    false_verified_count: int
    false_verified_rate: float
    expected_ambiguous_count: int
    detected_ambiguous_count: int
    ambiguous_detection_rate: float
    unresolved_count: int
    unresolved_rate: float
    page_only_count: int
    page_only_rate: float


class LatencyMetrics(StrictSchemaModel):
    """Per-field localization latency, excluded from reproducibility checks."""

    field_count: int
    p50_ms: float
    p95_ms: float
    max_ms: float


class CaseTypeBreakdown(StrictSchemaModel):
    """Error analysis for one authored failure mode."""

    case_type: str
    field_count: int
    status_matches: int
    region_hits: int
    false_verified: int


class ProvenanceEvaluationReport(StrictSchemaModel):
    """Serializable evaluation report with explicit scope boundaries."""

    benchmark_name: str
    corpus_version: str
    provenance_version: str
    region_hit_iou: float
    scope: str
    oracle_method: str
    uses_network: bool = False
    uses_api_keys: bool = False
    uses_gpu: bool = False
    corpus_checksums_verified: bool
    passed: bool
    gate_failures: list[str] = Field(default_factory=list)
    metrics: ProvenanceMetrics
    by_case_type: list[CaseTypeBreakdown]
    by_status: dict[str, dict[str, int]]
    outcomes: list[FieldOutcome]
    latency_ms: LatencyMetrics


def load_corpus(manifest_path: Path) -> ProvenanceCorpus:
    """Read and strictly validate the committed corpus manifest."""

    return ProvenanceCorpus.model_validate_json(
        Path(manifest_path).read_text(encoding="utf-8")
    )


def verify_corpus_checksums(corpus: ProvenanceCorpus, root: Path) -> list[str]:
    """Return the names of documents whose bytes no longer match the manifest."""

    mismatched: list[str] = []
    for document in corpus.documents:
        path = Path(root) / document.file
        if not path.is_file():
            mismatched.append(document.name)
            continue
        if sha256(path.read_bytes()).hexdigest() != document.sha256:
            mismatched.append(document.name)
    return mismatched


def _assign(payload: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: Any = payload
    for index, part in enumerate(parts[:-1]):
        following = parts[index + 1]
        default: Any = [] if following.isdigit() else {}
        if part.isdigit():
            position = int(part)
            while len(current) <= position:
                current.append({})
            if not isinstance(current[position], dict):
                current[position] = {}
            current = current[position]
        else:
            current = current.setdefault(part, default)
    final = parts[-1]
    if final.isdigit():
        position = int(final)
        while len(current) <= position:
            current.append({})
        current[position] = value
    else:
        current[final] = value


def build_extraction(document: CorpusDocument):
    """Rebuild the replayed extraction through the product's own strict schema."""

    payload: dict[str, Any] = {"schema_name": document.schema_name}
    for item in document.fields:
        located: dict[str, Any] = {
            "value": item.claim.value,
            "page_number": item.claim.page_number,
            "evidence_text": item.claim.evidence_text,
        }
        _assign(payload, item.field_path, located)
        if item.claim.additional_field_label is not None:
            label_path = item.field_path.rsplit(".", maxsplit=1)[0] + ".label"
            _assign(payload, label_path, item.claim.additional_field_label)
    model = SchemaRegistry.get(document.schema_name)  # type: ignore[arg-type]
    return model.model_validate(payload)


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def evaluate_corpus(
    corpus: ProvenanceCorpus,
    root: Path,
) -> ProvenanceEvaluationReport:
    """Resolve every corpus claim locally and score it against recorded truth."""

    root = Path(root)
    mismatched = verify_corpus_checksums(corpus, root)
    outcomes: list[FieldOutcome] = []
    localizable: list[FieldOutcome] = []
    durations: list[float] = []
    claimed_count = sum(
        1
        for document in corpus.documents
        for item in document.fields
        if (item.claim.value or "").strip() or (item.claim.evidence_text or "").strip()
    )

    for document in corpus.documents:
        normalized = normalize_document(root / document.file)
        extraction = build_extraction(document)
        index = build_match_index(normalized.text_layer)
        located = dict(iter_located_fields(extraction))
        page_count = len(normalized.text_layer.pages) or None

        for item in document.fields:
            claim = located[item.field_path]
            start = perf_counter()
            resolved = resolve_field_provenance(
                item.field_path,
                claim,
                index,
                page_count=page_count,
            )
            durations.append((perf_counter() - start) * 1000.0)

            truth_bbox = item.truth_bbox()
            predicted_bbox = resolved.bbox
            page_matches = resolved.resolved_page_number == item.truth_page
            iou = (
                round(predicted_bbox.iou(truth_bbox), 4)
                if predicted_bbox is not None and truth_bbox is not None
                else None
            )
            region_hit = bool(
                predicted_bbox is not None
                and truth_bbox is not None
                and page_matches
                and iou is not None
                and iou >= REGION_HIT_IOU
            )
            false_verified = resolved.verification_status == "verified" and not region_hit
            outcome = FieldOutcome(
                document=document.name,
                field_path=item.field_path,
                case_type=item.case_type,
                expected_status=item.expected_status,
                predicted_status=resolved.verification_status,
                status_matches=resolved.verification_status == item.expected_status,
                truth_page=item.truth_page,
                predicted_page=resolved.resolved_page_number,
                page_matches=page_matches,
                predicted_bbox=(
                    [
                        round(predicted_bbox.x0, 3),
                        round(predicted_bbox.y0, 3),
                        round(predicted_bbox.x1, 3),
                        round(predicted_bbox.y1, 3),
                    ]
                    if predicted_bbox is not None
                    else None
                ),
                iou=iou,
                region_hit=region_hit,
                resolution_method=resolved.resolution_method,
                match_score=resolved.match_score,
                candidate_count=resolved.candidate_count,
                false_verified=false_verified,
            )
            outcomes.append(outcome)
            if item.localizable:
                localizable.append(outcome)

    predicted_boxes = [outcome for outcome in outcomes if outcome.predicted_bbox is not None]
    ious = [outcome.iou for outcome in predicted_boxes if outcome.iou is not None]
    verified = [outcome for outcome in outcomes if outcome.predicted_status == "verified"]
    expected_ambiguous = [
        outcome for outcome in outcomes if outcome.expected_status == "ambiguous"
    ]

    metrics = ProvenanceMetrics(
        field_count=len(outcomes),
        localizable_field_count=len(localizable),
        claimed_field_count=claimed_count,
        overall_bbox_coverage=_rate(len(predicted_boxes), claimed_count),
        status_exact_matches=sum(outcome.status_matches for outcome in outcomes),
        status_exact_match_rate=_rate(
            sum(outcome.status_matches for outcome in outcomes), len(outcomes)
        ),
        page_localization_correct=sum(outcome.page_matches for outcome in localizable),
        page_localization_accuracy=_rate(
            sum(outcome.page_matches for outcome in localizable), len(localizable)
        ),
        bbox_localization_covered=sum(
            outcome.predicted_bbox is not None for outcome in localizable
        ),
        bbox_localization_coverage=_rate(
            sum(outcome.predicted_bbox is not None for outcome in localizable),
            len(localizable),
        ),
        predicted_bbox_count=len(predicted_boxes),
        region_hits=sum(outcome.region_hit for outcome in predicted_boxes),
        bbox_hit_rate=_rate(
            sum(outcome.region_hit for outcome in predicted_boxes), len(predicted_boxes)
        ),
        mean_iou=round(sum(ious) / len(ious), 4) if ious else 0.0,
        median_iou=round(median(ious), 4) if ious else 0.0,
        verified_count=len(verified),
        verified_region_hits=sum(outcome.region_hit for outcome in verified),
        verified_bbox_hit_rate=_rate(
            sum(outcome.region_hit for outcome in verified), len(verified)
        ),
        false_verified_count=sum(outcome.false_verified for outcome in verified),
        false_verified_rate=_rate(
            sum(outcome.false_verified for outcome in verified), len(verified)
        ),
        expected_ambiguous_count=len(expected_ambiguous),
        detected_ambiguous_count=sum(
            outcome.predicted_status == "ambiguous" for outcome in expected_ambiguous
        ),
        ambiguous_detection_rate=_rate(
            sum(outcome.predicted_status == "ambiguous" for outcome in expected_ambiguous),
            len(expected_ambiguous),
        ),
        unresolved_count=sum(
            outcome.predicted_status == "unresolved" for outcome in outcomes
        ),
        unresolved_rate=_rate(
            sum(outcome.predicted_status == "unresolved" for outcome in outcomes),
            len(outcomes),
        ),
        page_only_count=sum(
            outcome.predicted_status == "page_only" for outcome in outcomes
        ),
        page_only_rate=_rate(
            sum(outcome.predicted_status == "page_only" for outcome in outcomes),
            len(outcomes),
        ),
    )

    case_counter: Counter[str] = Counter(outcome.case_type for outcome in outcomes)
    by_case_type = [
        CaseTypeBreakdown(
            case_type=case_type,
            field_count=case_counter[case_type],
            status_matches=sum(
                outcome.status_matches
                for outcome in outcomes
                if outcome.case_type == case_type
            ),
            region_hits=sum(
                outcome.region_hit
                for outcome in outcomes
                if outcome.case_type == case_type
            ),
            false_verified=sum(
                outcome.false_verified
                for outcome in outcomes
                if outcome.case_type == case_type
            ),
        )
        for case_type in sorted(case_counter)
    ]
    by_status = {
        status: {
            "expected": sum(outcome.expected_status == status for outcome in outcomes),
            "predicted": sum(outcome.predicted_status == status for outcome in outcomes),
            "matched": sum(
                outcome.expected_status == status and outcome.status_matches
                for outcome in outcomes
            ),
        }
        for status in ("verified", "approximate", "ambiguous", "page_only", "unresolved")
    }

    gate_failures: list[str] = []
    if mismatched:
        gate_failures.append(f"corpus_checksum:{','.join(mismatched)}")
    if metrics.false_verified_rate > GATE_MAX_FALSE_VERIFIED_RATE:
        gate_failures.append("false_verified_rate")
    if metrics.page_localization_accuracy < GATE_MIN_PAGE_ACCURACY:
        gate_failures.append("page_localization_accuracy")
    if metrics.verified_bbox_hit_rate < GATE_MIN_VERIFIED_BBOX_HIT_RATE:
        gate_failures.append("verified_bbox_hit_rate")

    ordered = sorted(durations)
    return ProvenanceEvaluationReport(
        benchmark_name=corpus.corpus_name,
        corpus_version=corpus.version,
        provenance_version=PROVENANCE_VERSION,
        region_hit_iou=REGION_HIT_IOU,
        scope=(
            "固定合成 PDF 語料上的 evidence 定位與誠實度，"
            "不代表真實文件的 OCR、VLM 或端到端抽取準確率。"
        ),
        oracle_method=corpus.ground_truth_source,
        corpus_checksums_verified=not mismatched,
        passed=not gate_failures,
        gate_failures=gate_failures,
        metrics=metrics,
        by_case_type=by_case_type,
        by_status=by_status,
        outcomes=outcomes,
        latency_ms=LatencyMetrics(
            field_count=len(ordered),
            p50_ms=round(_percentile(ordered, 0.50), 4),
            p95_ms=round(_percentile(ordered, 0.95), 4),
            max_ms=round(ordered[-1], 4) if ordered else 0.0,
        ),
    )


def _percentile(ordered: list[float], fraction: float) -> float:
    if not ordered:
        return 0.0
    position = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[position]


def comparable_report(report: ProvenanceEvaluationReport | dict[str, Any]) -> dict[str, Any]:
    """Return the deterministic part of a report, excluding wall-clock timings."""

    payload = (
        report.model_dump(mode="json")
        if isinstance(report, ProvenanceEvaluationReport)
        else dict(report)
    )
    payload.pop("latency_ms", None)
    return payload


def write_provenance_report(report: ProvenanceEvaluationReport, path: Path) -> None:
    """Write stable UTF-8 JSON for review and CI artifacts."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
