from __future__ import annotations

import pytest
from pydantic import ValidationError

from doc_inspector.errors import ConfigurationError
from doc_inspector.schemas import (
    InspectionBundle,
    LocatedValue,
    Receipt,
    ReviewReport,
    SchemaRegistry,
    SubsidyApplication,
)


def test_registry_contains_only_v1_presets() -> None:
    assert SchemaRegistry.names() == ("subsidy_application", "receipt")
    assert SchemaRegistry.get("subsidy_application") is SubsidyApplication
    assert SchemaRegistry.get("receipt") is Receipt


def test_registry_rejects_unknown_schema() -> None:
    with pytest.raises(ConfigurationError):
        SchemaRegistry.get("arbitrary_json_schema")  # type: ignore[arg-type]


def test_located_value_requires_one_based_page_number() -> None:
    with pytest.raises(ValidationError):
        LocatedValue(value="測試", page_number=0, evidence_text="測試")


def test_schema_rejects_unexpected_provider_fields() -> None:
    with pytest.raises(ValidationError):
        Receipt.model_validate({"schema_name": "receipt", "unexpected": "value"})


def test_inspection_bundle_uses_discriminated_extraction() -> None:
    bundle = InspectionBundle(
        provider="gemini",
        model="configured-model",
        source_file_name="sample.png",
        page_count=1,
        elapsed_ms=10,
        extraction=SubsidyApplication(
            program_name=LocatedValue(value="測試補助", page_number=1, evidence_text="測試補助")
        ),
        review_report=ReviewReport(
            overall_level="green",
            message="測試完成。",
        ),
    )

    dumped = bundle.model_dump()
    assert dumped["extraction"]["schema_name"] == "subsidy_application"
    assert dumped["review_report"]["status"] == "completed"
    assert dumped["rules_version"] == "1.0.0"
