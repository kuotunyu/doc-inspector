from __future__ import annotations

from pathlib import Path

import pytest

from scripts_support import load_script_module

audit_ui_quality = load_script_module("audit_ui_quality")
serve_ui_fixture = load_script_module("serve_ui_fixture")
verify_ui_layout = load_script_module("verify_ui_layout")


def test_fixture_inspector_uses_named_synthetic_result() -> None:
    bundle = serve_ui_fixture.fixture_inspector(
        Path("subsidy_red.png"),
        "subsidy_application",
        "gemini",
    )

    assert bundle.model == "offline-ui-fixture"
    assert bundle.elapsed_ms == 0
    assert bundle.review_report.overall_level == "red"


def test_fixture_inspector_rejects_unknown_file() -> None:
    with pytest.raises(ValueError, match="不支援"):
        serve_ui_fixture.fixture_inspector(
            Path("unknown.png"),
            "receipt",
            "openai",
        )


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
