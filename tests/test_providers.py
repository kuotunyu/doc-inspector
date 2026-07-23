from __future__ import annotations

import base64
from typing import Any

import pytest
from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError

from doc_inspector.config import AppSettings
from doc_inspector.errors import ProviderInvocationError, StructuredOutputError
from doc_inspector.ingest import NormalizedDocument, NormalizedPage
from doc_inspector.providers import (
    LangChainStructuredExtractor,
    build_provider_schema,
    build_multimodal_message,
    safe_parsing_error_summary,
)
from doc_inspector.schemas import LocatedValue, Receipt, SubsidyApplication


def sample_document() -> NormalizedDocument:
    return NormalizedDocument(
        source_file_name="sample.png",
        pages=(NormalizedPage(page_number=1, data=b"page-bytes", width=10, height=10),),
    )


def gemini_settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        GOOGLE_API_KEY="test-key",
        GEMINI_MODEL="configured-gemini-model",
    )


class FakeRawMessage:
    usage_metadata = {"input_tokens": 12, "output_tokens": 4, "total_tokens": 16}


class FakeStructuredModel:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.messages: Any = None

    def invoke(self, messages: Any) -> Any:
        self.messages = messages
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeModel:
    def __init__(self, structured: FakeStructuredModel) -> None:
        self.structured = structured
        self.schema: Any = None
        self.include_raw: bool | None = None

    def with_structured_output(self, schema: Any, *, include_raw: bool) -> FakeStructuredModel:
        self.schema = schema
        self.include_raw = include_raw
        return self.structured


class RecordingFactory:
    def __init__(self, model: FakeModel) -> None:
        self.model = model
        self.args: tuple[Any, ...] | None = None
        self.kwargs: dict[str, Any] | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> FakeModel:
        self.args = args
        self.kwargs = kwargs
        return self.model


def test_multimodal_message_uses_standard_blocks_in_page_order() -> None:
    message = build_multimodal_message(sample_document())

    assert message["role"] == "user"
    assert [block["type"] for block in message["content"]] == ["text", "text", "image"]
    image_block = message["content"][2]
    assert base64.b64decode(image_block["base64"]) == b"page-bytes"
    assert image_block["mime_type"] == "image/png"


def test_provider_schema_omits_caller_controlled_schema_name() -> None:
    schema = build_provider_schema("receipt")

    assert "schema_name" not in schema["properties"]
    assert "schema_name" not in schema.get("required", [])
    assert "merchant_name" in schema["properties"]


def test_gemini_structured_extraction_uses_configured_model_and_usage() -> None:
    parsed = SubsidyApplication(
        program_name=LocatedValue(value="測試補助", page_number=1, evidence_text="測試補助")
    )
    structured = FakeStructuredModel(
        {"raw": FakeRawMessage(), "parsed": parsed, "parsing_error": None}
    )
    model = FakeModel(structured)
    factory = RecordingFactory(model)
    extractor = LangChainStructuredExtractor(gemini_settings(), model_factory=factory)

    result = extractor.extract(sample_document(), "subsidy_application", "gemini")

    assert factory.args == ("configured-gemini-model",)
    assert factory.kwargs is not None
    assert factory.kwargs["model_provider"] == "google_genai"
    assert factory.kwargs["max_tokens"] == 4096
    assert model.schema["title"] == "SubsidyApplication"
    assert "schema_name" not in model.schema["properties"]
    assert model.include_raw is True
    assert result.usage.total_tokens == 16
    assert result.parsed == parsed


def test_openai_provider_switch_uses_openai_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    settings = AppSettings(
        _env_file=None,
        OPENAI_API_KEY="test-key",
        OPENAI_MODEL="configured-openai-model",
    )
    structured = FakeStructuredModel(
        {"raw": FakeRawMessage(), "parsed": Receipt(), "parsing_error": None}
    )
    factory = RecordingFactory(FakeModel(structured))

    result = LangChainStructuredExtractor(settings, model_factory=factory).extract(
        sample_document(), "receipt", "openai"
    )

    assert factory.kwargs is not None
    assert factory.kwargs["model_provider"] == "openai"
    assert result.provider == "openai"
    assert isinstance(result.parsed, Receipt)


def test_structured_parsing_error_is_returned_without_raw_content() -> None:
    structured = FakeStructuredModel(
        {
            "raw": object(),
            "parsed": None,
            "parsing_error": ValueError("private document content"),
        }
    )
    extractor = LangChainStructuredExtractor(
        gemini_settings(), model_factory=RecordingFactory(FakeModel(structured))
    )

    with pytest.raises(StructuredOutputError) as exc_info:
        extractor.extract(sample_document(), "receipt", "gemini")

    assert "private document content" not in str(exc_info.value)
    assert "ValueError" in str(exc_info.value)


def test_provider_failure_does_not_echo_upstream_message() -> None:
    structured = FakeStructuredModel(RuntimeError("private document content and secret"))
    extractor = LangChainStructuredExtractor(
        gemini_settings(), model_factory=RecordingFactory(FakeModel(structured))
    )

    with pytest.raises(ProviderInvocationError) as exc_info:
        extractor.extract(sample_document(), "receipt", "gemini")

    message = str(exc_info.value)
    assert "private document content" not in message
    assert "secret" not in message
    assert "RuntimeError" in message
    assert exc_info.value.__suppress_context__ is True


def test_safe_parsing_error_summary_keeps_paths_but_not_values() -> None:
    try:
        LocatedValue.model_validate(
            {"value": "private value", "page_number": 0, "evidence_text": "private evidence"}
        )
    except ValidationError as validation_error:
        parser_error = OutputParserException("contains private completion")
        parser_error.__cause__ = validation_error
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected validation failure")

    summary = safe_parsing_error_summary(parser_error)

    assert "page_number" in summary
    assert "greater_than_equal" in summary
    assert "private value" not in summary
    assert "private evidence" not in summary
    assert "private completion" not in summary
