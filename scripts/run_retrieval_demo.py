"""Evaluate local ColQwen2 retrieval on the fixed 50-page XFUND validation corpus."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

from huggingface_hub import model_info
from PIL import Image, ImageOps
import torch

from doc_inspector.config import load_settings
from doc_inspector.retrieval import ColQwenRetriever, memory_efficient_maxsim, retrieval_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", type=Path, default=Path("data/benchmark/xfund_split.json"))
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("data/benchmark/xfund_ground_truth.json"),
    )
    parser.add_argument("--images", type=Path, default=Path("data/raw/xfund/images"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/benchmark/results/retrieval.json"),
    )
    parser.add_argument("--query-count", type=int, default=20)
    parser.add_argument("--smoke-pages", type=int, choices=(0, 2), default=0)
    return parser.parse_args()


def _query_for_pair(key: str, value: str) -> str:
    return f"哪一頁包含欄位「{key}」，而且該欄位內容為「{value}」？"


def main() -> int:
    args = parse_args()
    split_bytes = args.split.read_bytes()
    split = json.loads(split_bytes)
    ground_truth = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    val_documents = [item for item in split["evaluation"] if item["source_split"] == "val"]
    if len(val_documents) != 50:
        raise SystemExit(f"預期 50 頁 XFUND val，實際為 {len(val_documents)}。")
    if args.smoke_pages:
        val_documents = val_documents[: args.smoke_pages]

    query_documents = val_documents[: min(args.query_count, len(val_documents))]
    queries: list[str] = []
    expected_indexes: list[int] = []
    query_metadata: list[dict[str, str | int]] = []
    corpus_index = {item["uid"]: index for index, item in enumerate(val_documents)}
    for item in query_documents:
        pairs = ground_truth[item["uid"]]["pairs"]
        if not pairs:
            continue
        selected = pairs[len(pairs) // 2]
        query = _query_for_pair(selected["key"], selected["value"])
        queries.append(query)
        expected_indexes.append(corpus_index[item["uid"]])
        query_metadata.append(
            {
                "target_uid": item["uid"],
                "target_index": corpus_index[item["uid"]],
                "key": selected["key"],
                "value": selected["value"],
            }
        )

    settings = load_settings()
    retriever = ColQwenRetriever(settings.colqwen_model)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    retriever.load()

    document_embeddings: list[torch.Tensor] = []
    indexing_started = perf_counter()
    for index, item in enumerate(val_documents, start=1):
        with Image.open(args.images / item["image_name"]) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            document_embeddings.extend(retriever.embed_images([image]))
        print(f"indexed {index}/{len(val_documents)}")
    indexing_seconds = perf_counter() - indexing_started

    query_started = perf_counter()
    query_embeddings = retriever.embed_queries(queries)
    query_seconds = perf_counter() - query_started
    scoring_started = perf_counter()
    scores = memory_efficient_maxsim(
        query_embeddings,
        document_embeddings,
        device=retriever.device,
    )
    scoring_seconds = perf_counter() - scoring_started
    metrics = retrieval_metrics(scores, expected_indexes)
    ranked = torch.topk(scores, k=min(3, scores.shape[1]), dim=1).indices.tolist()

    try:
        revision = model_info(settings.colqwen_model).sha
    except Exception:
        revision = None
    result = {
        "model": settings.colqwen_model,
        "model_revision": revision,
        "attention_implementation": "sdpa",
        "dtype": "bfloat16",
        "device": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "transformers_version": __import__("transformers").__version__,
        "split_sha256": sha256(split_bytes).hexdigest(),
        "corpus_pages": len(val_documents),
        "queries": len(queries),
        "recall_at_1": metrics.recall_at_1,
        "recall_at_3": metrics.recall_at_3,
        "latency_seconds": {
            "model_load": retriever.load_seconds,
            "corpus_total": indexing_seconds,
            "corpus_per_page": indexing_seconds / len(val_documents),
            "queries_total": query_seconds,
            "query_per_item": query_seconds / len(queries),
            "scoring_total": scoring_seconds,
            "scoring_per_query": scoring_seconds / len(queries),
        },
        "peak_vram_gib": torch.cuda.max_memory_allocated() / (1024**3),
        "query_targets": query_metadata,
        "top_3_indexes": ranked,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("corpus_pages", "queries", "recall_at_1", "recall_at_3", "peak_vram_gib")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
