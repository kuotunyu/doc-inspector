"""Offline verification for public Markdown links and private path leakage."""

from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import unquote


_MARKDOWN_LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
_INTERNAL_ROOT_DOCS = {"CLAUDE.md", "PLAN.md", "PROGRESS.md"}
_PRIVATE_PATH_MARKERS = ("C:\\Users\\", "/Users/", "/home/")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_BENCHMARK_ARTIFACT_PATHS = {
    "extraction": Path("docs/assets/xfund-extraction-benchmark.json"),
    "retrieval": Path("docs/assets/colqwen-retrieval-benchmark.json"),
}
_BENCHMARK_FORBIDDEN_KEYS = {
    "document_text",
    "key",
    "names",
    "per_item_predictions",
    "phone",
    "phone_number",
    "predictions",
    "query_targets",
    "raw_document_text",
    "top_3_indexes",
    "value",
}


def public_markdown_files(root: Path) -> list[Path]:
    """Return public Markdown without local workflow notes."""

    root = Path(root).resolve()
    files = [
        path
        for path in root.glob("*.md")
        if path.name not in _INTERNAL_ROOT_DOCS
    ]
    files.extend((root / "docs").rglob("*.md"))
    files.extend((root / ".github").rglob("*.md"))
    return sorted(path for path in files if path.is_file())


def _local_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    if " " in target:
        target = target.split(" ", maxsplit=1)[0]
    return unquote(target.split("#", maxsplit=1)[0])


def _forbidden_benchmark_fields(
    payload: object,
    prefix: str = "",
) -> list[str]:
    issues: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key).casefold() in _BENCHMARK_FORBIDDEN_KEYS:
                issues.append(path)
            issues.extend(_forbidden_benchmark_fields(value, path))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            path = f"{prefix}[{index}]"
            issues.extend(_forbidden_benchmark_fields(value, path))
    return issues


def _unexpected_keys(
    value: object,
    allowed: set[str],
    location: str,
) -> list[str]:
    if not isinstance(value, dict):
        return [f"{location}: expected object"]
    return [
        f"{location}: unexpected field {key}"
        for key in sorted(set(value) - allowed)
    ]


def _is_metric(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def _benchmark_artifact_issues(
    root: Path,
) -> tuple[list[str], dict[str, dict[str, object]]]:
    issues: list[str] = []
    artifacts: dict[str, dict[str, object]] = {}
    for kind, relative_path in _BENCHMARK_ARTIFACT_PATHS.items():
        path = root / relative_path
        if not path.is_file():
            issues.append(f"{relative_path.as_posix()}: missing")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            issues.append(f"{relative_path.as_posix()}: invalid JSON ({type(exc).__name__})")
            continue
        if not isinstance(payload, dict):
            issues.append(f"{relative_path.as_posix()}: expected object")
            continue
        artifacts[kind] = payload
        issues.extend(
            f"{relative_path.as_posix()}: forbidden field {field}"
            for field in _forbidden_benchmark_fields(payload)
        )
        source_sha256 = payload.get("source_sha256")
        if not isinstance(source_sha256, str) or _SHA256.fullmatch(source_sha256) is None:
            issues.append(f"{relative_path.as_posix()}: invalid source_sha256")

    extraction = artifacts.get("extraction")
    if extraction is not None:
        issues.extend(
            _unexpected_keys(
                extraction,
                {
                    "artifact_schema_version",
                    "artifact_type",
                    "source_sha256",
                    "dataset",
                    "split",
                    "document_count",
                    "results",
                    "cost_summary",
                    "methodology",
                },
                "extraction",
            )
        )
        issues.extend(
            _unexpected_keys(
                extraction.get("dataset"),
                {"name", "version", "language"},
                "extraction.dataset",
            )
        )
        issues.extend(
            _unexpected_keys(
                extraction.get("split"),
                {"description", "seed", "manifest_sha256"},
                "extraction.split",
            )
        )
        issues.extend(
            _unexpected_keys(
                extraction.get("cost_summary"),
                {
                    "provider_runs_charged_or_reserved_usd",
                    "prior_run_cost_reserve_usd",
                    "total_charged_or_reserved_cost_usd",
                    "approved_max_cost_usd",
                },
                "extraction.cost_summary",
            )
        )
        issues.extend(
            _unexpected_keys(
                extraction.get("methodology"),
                {"matching", "normalization", "reproduction_scripts"},
                "extraction.methodology",
            )
        )
        document_count = extraction.get("document_count")
        if not isinstance(document_count, int) or isinstance(document_count, bool) or document_count <= 0:
            issues.append("extraction.document_count: expected positive integer")
        results = extraction.get("results")
        if not isinstance(results, list) or not results:
            issues.append("extraction.results: expected non-empty list")
        else:
            for index, result in enumerate(results):
                location = f"extraction.results[{index}]"
                issues.extend(
                    _unexpected_keys(
                        result,
                        {
                            "provider",
                            "model",
                            "successful_document_count",
                            "metrics",
                            "charged_or_reserved_cost_usd",
                        },
                        location,
                    )
                )
                if not isinstance(result, dict):
                    continue
                if not all(
                    isinstance(result.get(field), str) and result[field]
                    for field in ("provider", "model")
                ):
                    issues.append(f"{location}: provider/model must be non-empty strings")
                success_count = result.get("successful_document_count")
                if (
                    not isinstance(success_count, int)
                    or isinstance(success_count, bool)
                    or not isinstance(document_count, int)
                    or not 0 <= success_count <= document_count
                ):
                    issues.append(f"{location}.successful_document_count: invalid")
                metrics = result.get("metrics")
                issues.extend(
                    _unexpected_keys(
                        metrics,
                        {"precision", "recall", "micro_f1", "macro_document_f1"},
                        f"{location}.metrics",
                    )
                )
                if not isinstance(metrics, dict) or any(
                    not _is_metric(metrics.get(metric))
                    for metric in (
                        "precision",
                        "recall",
                        "micro_f1",
                        "macro_document_f1",
                    )
                ):
                    issues.append(f"{location}.metrics: expected four metrics in [0, 1]")

    retrieval = artifacts.get("retrieval")
    if retrieval is not None:
        issues.extend(
            _unexpected_keys(
                retrieval,
                {
                    "artifact_schema_version",
                    "artifact_type",
                    "source_sha256",
                    "model",
                    "split",
                    "corpus_page_count",
                    "query_count",
                    "metrics",
                    "latency_seconds",
                    "peak_vram_gib",
                    "environment",
                    "methodology",
                },
                "retrieval",
            )
        )
        issues.extend(
            _unexpected_keys(
                retrieval.get("model"), {"name", "revision"}, "retrieval.model"
            )
        )
        issues.extend(
            _unexpected_keys(
                retrieval.get("split"),
                {"description", "manifest_sha256"},
                "retrieval.split",
            )
        )
        issues.extend(
            _unexpected_keys(
                retrieval.get("latency_seconds"),
                {
                    "model_load",
                    "corpus_total",
                    "corpus_per_page",
                    "queries_total",
                    "query_per_item",
                    "scoring_total",
                    "scoring_per_query",
                },
                "retrieval.latency_seconds",
            )
        )
        issues.extend(
            _unexpected_keys(
                retrieval.get("environment"),
                {
                    "device",
                    "torch_version",
                    "cuda_version",
                    "transformers_version",
                    "dtype",
                    "attention_implementation",
                },
                "retrieval.environment",
            )
        )
        issues.extend(
            _unexpected_keys(
                retrieval.get("methodology"),
                {"scoring", "reproduction_scripts"},
                "retrieval.methodology",
            )
        )
        metrics = retrieval.get("metrics")
        issues.extend(
            _unexpected_keys(
                metrics, {"recall_at_1", "recall_at_3"}, "retrieval.metrics"
            )
        )
        if not isinstance(metrics, dict) or any(
            not _is_metric(metrics.get(metric))
            for metric in ("recall_at_1", "recall_at_3")
        ):
            issues.append("retrieval.metrics: expected Recall@1/3 in [0, 1]")
        for field in ("corpus_page_count", "query_count"):
            value = retrieval.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                issues.append(f"retrieval.{field}: expected positive integer")

    return issues, artifacts


def _benchmark_claim_issues(
    root: Path,
    artifacts: dict[str, dict[str, object]],
) -> list[str]:
    extraction = artifacts.get("extraction")
    retrieval = artifacts.get("retrieval")
    if extraction is None or retrieval is None:
        return []
    readme = (root / "README.md").read_text(encoding="utf-8")
    case_study = (root / "docs" / "CASE_STUDY.md").read_text(encoding="utf-8")
    issues: list[str] = []

    for target, text, label in (
        ("docs/assets/xfund-extraction-benchmark.json", readme, "README extraction link"),
        ("docs/assets/colqwen-retrieval-benchmark.json", readme, "README retrieval link"),
        ("assets/xfund-extraction-benchmark.json", case_study, "case study extraction link"),
        ("assets/colqwen-retrieval-benchmark.json", case_study, "case study retrieval link"),
    ):
        if f"]({target})" not in text:
            issues.append(label)

    document_count = extraction["document_count"]
    f1_values: list[str] = []
    for result in extraction["results"]:
        metrics = result["metrics"]
        expected_row = (
            f"| `{result['model']}` | {document_count} | "
            f"{result['successful_document_count']} | {metrics['precision']:.4f} | "
            f"{metrics['recall']:.4f} | {metrics['micro_f1']:.4f} | "
            f"{metrics['macro_document_f1']:.4f} |"
        )
        if expected_row not in readme:
            issues.append(f"README extraction row: {result['provider']}")
        f1_values.append(f"{metrics['micro_f1']:.4f}")

    retrieval_metrics = retrieval["metrics"]
    for label, field in (("Recall@1", "recall_at_1"), ("Recall@3", "recall_at_3")):
        expected_row = f"| {label} | {retrieval_metrics[field]:.2f} |"
        if expected_row not in readme:
            issues.append(f"README retrieval row: {label}")

    expected_case_claim = (
        f"Micro F1 分別為 **{f1_values[0]}**、**{f1_values[1]}**"
        f"（[去識別抽取 artifact](assets/xfund-extraction-benchmark.json)）；"
        f"ColQwen2 的 Recall@1 為 **{retrieval_metrics['recall_at_1']:.2f}**"
        f"（[去識別檢索 artifact](assets/colqwen-retrieval-benchmark.json)）。"
    )
    if expected_case_claim not in case_study:
        issues.append("case study benchmark claim")
    return issues


def verify_public_docs(root: Path) -> dict[str, object]:
    """Check public documentation without network or Git metadata."""

    root = Path(root).resolve()
    missing_links: list[dict[str, str]] = []
    outside_workspace_links: list[dict[str, str]] = []
    private_path_markers: list[dict[str, str]] = []
    files = public_markdown_files(root)
    benchmark_artifact_issues, benchmark_artifacts = _benchmark_artifact_issues(root)
    benchmark_claim_issues = (
        []
        if benchmark_artifact_issues
        else _benchmark_claim_issues(root, benchmark_artifacts)
    )

    for source in files:
        text = source.read_text(encoding="utf-8")
        relative_source = source.relative_to(root).as_posix()
        for marker in _PRIVATE_PATH_MARKERS:
            if marker in text:
                private_path_markers.append(
                    {"source": relative_source, "marker": marker}
                )
        for match in _MARKDOWN_LINK.finditer(text):
            raw_target = match.group(1)
            target = _local_target(raw_target)
            if target is None:
                continue
            resolved = (source.parent / target).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                outside_workspace_links.append(
                    {"source": relative_source, "target": raw_target}
                )
                continue
            if not resolved.exists():
                missing_links.append(
                    {"source": relative_source, "target": raw_target}
                )

    return {
        "ready": not (
            missing_links
            or outside_workspace_links
            or private_path_markers
            or benchmark_artifact_issues
            or benchmark_claim_issues
        ),
        "file_count": len(files),
        "missing_links": missing_links,
        "outside_workspace_links": outside_workspace_links,
        "private_path_markers": private_path_markers,
        "benchmark_artifact_issues": benchmark_artifact_issues,
        "benchmark_claim_issues": benchmark_claim_issues,
        "uses_network": False,
        "reads_env_truth": False,
    }
