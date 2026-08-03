from __future__ import annotations

from pathlib import Path

from doc_inspector import docs_verify


def test_public_benchmark_artifacts_are_sanitized_and_match_docs() -> None:
    root = Path(__file__).resolve().parents[1]

    report = docs_verify.verify_public_docs(root)

    assert report["benchmark_artifact_issues"] == []
    assert report["benchmark_claim_issues"] == []


def test_benchmark_privacy_gate_finds_nested_sensitive_fields() -> None:
    payload = {
        "safe_summary": {
            "query_targets": [],
            "nested": {"top_3_indexes": []},
        }
    }

    issues = docs_verify._forbidden_benchmark_fields(payload)

    assert issues == [
        "safe_summary.query_targets",
        "safe_summary.nested.top_3_indexes",
    ]
