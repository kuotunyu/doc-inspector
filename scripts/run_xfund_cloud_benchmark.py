"""Explicit, resumable, cost-gated XFUND benchmark for both cloud providers."""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
from time import perf_counter, sleep

from doc_inspector.benchmark import (
    BenchmarkPair,
    build_evaluation_split,
    load_xfund_documents,
    score_by_split,
)
from doc_inspector.benchmark_cloud import (
    CloudBenchmarkExtractor,
    conservative_request_cost_usd,
    usage_cost_usd,
)
from doc_inspector.config import load_settings
from doc_inspector.costs import parse_positive_usd, require_approved_budget
from doc_inspector.ingest import normalize_document
from doc_inspector.types import ProviderName

PRIOR_RUN_COST_RESERVE_USD = Decimal("0.057527")
CALIBRATION_DOCUMENTS = 3
MAX_ATTEMPTS = 3


def positive_decimal(value: str) -> Decimal:
    try:
        return parse_positive_usd(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="執行 XFUND 雙 provider 付費 benchmark。")
    parser.add_argument("--confirm-paid-api", action="store_true")
    parser.add_argument("--approved-max-cost-usd", type=positive_decimal)
    parser.add_argument("--approved-gemini-model")
    parser.add_argument("--approved-openai-model")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/xfund"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/benchmark"))
    return parser.parse_args()


def _record_path(output_dir: Path, provider: ProviderName, image_name: str) -> Path:
    return output_dir / "predictions" / provider / f"{Path(image_name).stem}.json"


def _load_record(path: Path, *, expected_model: str) -> dict[str, object] | None:
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("model") != expected_model:
        raise RuntimeError(f"既有 prediction 的模型與目前設定不同：{path.name}")
    return record


def _record_cost(record: dict[str, object]) -> Decimal:
    return Decimal(str(record.get("cost_usd", "0")))


def _write_record(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _provider_predictions(
    *,
    provider: ProviderName,
    model: str,
    documents: list,
    raw_dir: Path,
    output_dir: Path,
    extractor: CloudBenchmarkExtractor,
    approved_usd: Decimal,
    reserved_usd: Decimal,
    limit: int | None = None,
) -> tuple[dict[str, list[BenchmarkPair]], Decimal, int]:
    predictions: dict[str, list[BenchmarkPair]] = {}
    spent = Decimal("0")
    failure_reserve = Decimal("0")
    selected = documents[:limit] if limit is not None else documents
    worst_request = conservative_request_cost_usd(provider)

    for index, document in enumerate(selected, start=1):
        record_path = _record_path(output_dir, provider, document.image_name)
        existing = _load_record(record_path, expected_model=model)
        if existing is not None:
            pairs = [BenchmarkPair.model_validate(pair) for pair in existing["pairs"]]
            predictions[document.uid] = pairs
            spent += _record_cost(existing)
            continue

        require_approved_budget(
            approved_usd=approved_usd,
            estimated_usd=reserved_usd + spent + failure_reserve + worst_request,
        )
        error_type = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            started = perf_counter()
            try:
                normalized = normalize_document(raw_dir / "images" / document.image_name)
                result = extractor.extract(normalized, provider)
            except Exception as exc:
                error_type = type(exc).__name__
                failure_reserve += worst_request
                if attempt < MAX_ATTEMPTS:
                    sleep(2**attempt)
                    continue
                break

            actual_cost = usage_cost_usd(provider, result.usage)
            charged_cost = actual_cost if actual_cost is not None else worst_request
            spent += charged_cost
            record = {
                "uid": document.uid,
                "source_split": document.source_split,
                "image_name": document.image_name,
                "provider": provider,
                "model": model,
                "pairs": [pair.model_dump() for pair in result.prediction.pairs],
                "usage": result.usage.model_dump(),
                "cost_usd": str(charged_cost),
                "elapsed_seconds": round(perf_counter() - started, 3),
                "attempt": attempt,
            }
            _write_record(record_path, record)
            predictions[document.uid] = result.prediction.pairs
            error_type = ""
            break

        if error_type:
            print(f"{provider} {index}/{len(selected)} failed={error_type}")
        elif index % 5 == 0 or index == len(selected):
            print(f"{provider} {index}/{len(selected)} metered_cost=US${spent:.6f}")

    return predictions, spent + failure_reserve, len(predictions)


def main() -> int:
    args = parse_args()
    if not all(
        (
            args.confirm_paid_api,
            args.approved_max_cost_usd,
            args.approved_gemini_model,
            args.approved_openai_model,
        )
    ):
        raise SystemExit("拒絕執行：缺少付費確認、成本上限或核准模型 ID。")

    settings = load_settings()
    gemini = settings.provider_config("gemini")
    openai = settings.provider_config("openai")
    if gemini.model != args.approved_gemini_model or openai.model != args.approved_openai_model:
        raise SystemExit("拒絕執行：.env 模型 ID 與作者核准值不一致。")
    if settings.model_max_tokens > 4096:
        raise SystemExit("拒絕執行：MODEL_MAX_TOKENS 超過本次估價採用的 4096。")

    raw_dir = args.raw_dir.resolve()
    train = load_xfund_documents(raw_dir / "zh.train.json", "train_holdout")
    val = load_xfund_documents(raw_dir / "zh.val.json", "val")
    evaluation, _ = build_evaluation_split(train, val)
    initial_estimate = PRIOR_RUN_COST_RESERVE_USD + sum(
        conservative_request_cost_usd(provider) * len(evaluation)
        for provider in ("gemini", "openai")
    )
    try:
        require_approved_budget(
            approved_usd=args.approved_max_cost_usd,
            estimated_usd=initial_estimate,
        )
    except ValueError as exc:
        raise SystemExit(f"拒絕執行：{exc}") from None
    print(f"200 份請求含前序成本的保守上限：US${initial_estimate}／核准 US${args.approved_max_cost_usd}")

    extractor = CloudBenchmarkExtractor(settings)
    calibration_cost = Decimal("0")
    calibration_counts: dict[str, int] = {}
    for provider, model in (("gemini", gemini.model), ("openai", openai.model)):
        _, cost, count = _provider_predictions(
            provider=provider,
            model=model,
            documents=evaluation,
            raw_dir=raw_dir,
            output_dir=args.output_dir,
            extractor=extractor,
            approved_usd=args.approved_max_cost_usd,
            reserved_usd=PRIOR_RUN_COST_RESERVE_USD + calibration_cost,
            limit=CALIBRATION_DOCUMENTS,
        )
        calibration_cost += cost
        calibration_counts[provider] = count
    if any(count < CALIBRATION_DOCUMENTS for count in calibration_counts.values()):
        raise SystemExit("校準未達每個 provider 3 份，停止完整批次。")
    projected = PRIOR_RUN_COST_RESERVE_USD + calibration_cost / Decimal(CALIBRATION_DOCUMENTS) * Decimal(100)
    try:
        require_approved_budget(approved_usd=args.approved_max_cost_usd, estimated_usd=projected)
    except ValueError as exc:
        raise SystemExit(f"校準後停止：{exc}") from None
    print(f"3 份校準後投影總成本：US${projected:.6f}")

    all_results: dict[str, object] = {}
    cumulative = PRIOR_RUN_COST_RESERVE_USD
    for provider, model in (("gemini", gemini.model), ("openai", openai.model)):
        predictions, charged, success_count = _provider_predictions(
            provider=provider,
            model=model,
            documents=evaluation,
            raw_dir=raw_dir,
            output_dir=args.output_dir,
            extractor=extractor,
            approved_usd=args.approved_max_cost_usd,
            reserved_usd=cumulative,
        )
        cumulative += charged
        all_results[provider] = {
            "model": model,
            "success_count": success_count,
            "charged_or_reserved_cost_usd": str(charged),
            "metrics": score_by_split(evaluation, predictions),
        }

    results = {
        "documents": len(evaluation),
        "approved_max_cost_usd": str(args.approved_max_cost_usd),
        "prior_run_cost_reserve_usd": str(PRIOR_RUN_COST_RESERVE_USD),
        "total_charged_or_reserved_cost_usd": str(cumulative),
        "providers": all_results,
    }
    results_dir = args.output_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "cloud.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(results, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
