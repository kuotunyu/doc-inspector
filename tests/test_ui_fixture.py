from __future__ import annotations

from pathlib import Path

import pytest

from doc_inspector.demo import PROVENANCE_DEMO_NAME, generate_demo_artifacts
from scripts_support import load_script_module

audit_ui_quality = load_script_module("audit_ui_quality")
serve_ui_fixture = load_script_module("serve_ui_fixture")
verify_ui_layout = load_script_module("verify_ui_layout")


def test_fixture_inspector_uses_named_synthetic_result(tmp_path: Path) -> None:
    generate_demo_artifacts(tmp_path)

    artifacts = serve_ui_fixture.fixture_inspector(
        tmp_path / "subsidy_red.png",
        "subsidy_application",
        "gemini",
    )
    bundle = artifacts.bundle

    assert bundle.model == "offline-ui-fixture"
    assert bundle.elapsed_ms == 0
    assert bundle.review_report.overall_level == "red"
    assert len(artifacts.pages) == 1
    assert bundle.provenance is not None
    assert {field.verification_status for field in bundle.provenance.fields} == {
        "page_only"
    }


def test_fixture_inspector_verifies_provenance_demo_against_real_text_layer(
    tmp_path: Path,
) -> None:
    generate_demo_artifacts(tmp_path)

    artifacts = serve_ui_fixture.fixture_inspector(
        tmp_path / f"{PROVENANCE_DEMO_NAME}.pdf",
        "subsidy_application",
        "gemini",
    )
    provenance = artifacts.bundle.provenance

    assert provenance is not None
    assert artifacts.bundle.page_count == 3
    assert {field.verification_status for field in provenance.fields} == {
        "verified",
        "approximate",
        "ambiguous",
        "page_only",
        "unresolved",
    }


def test_fixture_inspector_rejects_unknown_file(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.png"
    unknown.write_bytes(b"not-read-before-the-name-check")

    with pytest.raises(ValueError, match="不支援"):
        serve_ui_fixture.fixture_inspector(unknown, "receipt", "openai")


@pytest.mark.parametrize(
    "validator",
    [
        verify_ui_layout.validate_test_target,
        audit_ui_quality.validate_test_target,
    ],
)
def test_ui_audits_default_to_dedicated_offline_port(validator) -> None:
    validator("http://127.0.0.1:7862")

    with pytest.raises(RuntimeError, match="離線 fixture"):
        validator("http://127.0.0.1:7861")
    with pytest.raises(RuntimeError, match="離線 fixture"):
        validator("https://example.test")

    validator("https://example.test", allow_non_fixture=True)


def test_ui_audit_artifacts_default_to_ignored_output_directory() -> None:
    root = Path(__file__).resolve().parents[1]
    expected_output = root / "outputs" / "ui-audit"

    assert verify_ui_layout.DEFAULT_AUDIT_OUTPUT_DIR == expected_output
    assert verify_ui_layout.PUBLIC_ASSET_DIR == root / "docs" / "assets"
    assert audit_ui_quality.DEFAULT_AUDIT_OUTPUT_DIR == expected_output
    assert audit_ui_quality.REPORT_PATH == expected_output / "ui-quality-audit.json"
