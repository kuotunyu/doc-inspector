"""Local ColQwen2 page retrieval with bounded-memory late interaction."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from PIL import Image
import torch


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    queries: int
    recall_at_1: float
    recall_at_3: float


def memory_efficient_maxsim(
    query_embeddings: Sequence[torch.Tensor],
    document_embeddings: Sequence[torch.Tensor],
    *,
    device: torch.device | str = "cpu",
) -> torch.Tensor:
    """Score query/document pairs without allocating the full Q×D×Lq×Ld tensor."""

    if not query_embeddings or not document_embeddings:
        return torch.empty(
            (len(query_embeddings), len(document_embeddings)),
            dtype=torch.float32,
        )
    selected_device = torch.device(device)
    rows: list[torch.Tensor] = []
    with torch.inference_mode():
        for query in query_embeddings:
            query_on_device = query.to(selected_device, dtype=torch.float32)
            row = []
            for document in document_embeddings:
                document_on_device = document.to(selected_device, dtype=torch.float32)
                score = (query_on_device @ document_on_device.transpose(0, 1)).amax(dim=1).sum()
                row.append(score.cpu())
            rows.append(torch.stack(row))
    return torch.stack(rows)


def retrieval_metrics(
    scores: torch.Tensor,
    expected_document_indexes: Sequence[int],
) -> RetrievalMetrics:
    """Calculate deterministic Recall@1 and Recall@3 for one target per query."""

    if scores.ndim != 2:
        raise ValueError("scores must have shape [queries, documents]")
    if scores.shape[0] != len(expected_document_indexes):
        raise ValueError("one expected document index is required per query")
    if scores.shape[1] == 0:
        return RetrievalMetrics(queries=scores.shape[0], recall_at_1=0.0, recall_at_3=0.0)
    top_k = min(3, scores.shape[1])
    ranked = torch.topk(scores, k=top_k, dim=1).indices
    hit_1 = hit_3 = 0
    for row_index, expected in enumerate(expected_document_indexes):
        if expected < 0 or expected >= scores.shape[1]:
            raise ValueError("expected document index is outside the corpus")
        hit_1 += int(ranked[row_index, 0].item() == expected)
        hit_3 += int(expected in ranked[row_index].tolist())
    count = len(expected_document_indexes)
    return RetrievalMetrics(
        queries=count,
        recall_at_1=hit_1 / count if count else 0.0,
        recall_at_3=hit_3 / count if count else 0.0,
    )


class ColQwenRetriever:
    """Small adapter around the Transformers-native ColQwen2 implementation."""

    def __init__(self, model_name: str, *, device: str = "cuda:0") -> None:
        self.model_name = model_name
        self.device = torch.device(device)
        self.model: Any | None = None
        self.processor: Any | None = None
        self.load_seconds: float | None = None

    def load(self) -> None:
        if self.model is not None:
            return
        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("ColQwen2 設定為 CUDA，但目前 PyTorch 無法存取 GPU。")
        from transformers import ColQwen2ForRetrieval, ColQwen2Processor

        started = perf_counter()
        self.model = ColQwen2ForRetrieval.from_pretrained(
            self.model_name,
            torch_dtype=torch.bfloat16,
            device_map={"": str(self.device)},
            attn_implementation="sdpa",
        ).eval()
        self.processor = ColQwen2Processor.from_pretrained(self.model_name)
        self.load_seconds = perf_counter() - started

    def _require_loaded(self) -> tuple[Any, Any]:
        if self.model is None or self.processor is None:
            raise RuntimeError("請先呼叫 ColQwenRetriever.load()。")
        return self.model, self.processor

    def embed_images(self, images: Sequence[Image.Image]) -> list[torch.Tensor]:
        model, processor = self._require_loaded()
        inputs = processor(images=list(images)).to(self.device)
        with torch.inference_mode():
            embeddings = model(**inputs).embeddings
        return [embedding.detach().cpu() for embedding in embeddings]

    def embed_queries(self, queries: Sequence[str]) -> list[torch.Tensor]:
        model, processor = self._require_loaded()
        inputs = processor(text=list(queries)).to(self.device)
        with torch.inference_mode():
            embeddings = model(**inputs).embeddings
        return [embedding.detach().cpu() for embedding in embeddings]
