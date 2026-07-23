"""LangChain 1.x structured-output adapter for both cloud providers."""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from langchain.chat_models import init_chat_model
from pydantic import ValidationError

from doc_inspector.config import AppSettings
from doc_inspector.errors import ProviderInvocationError, StructuredOutputError
from doc_inspector.ingest import NormalizedDocument
from doc_inspector.schemas import DocumentExtraction, SchemaRegistry, TokenUsage
from doc_inspector.types import ProviderName, SchemaName

EXTRACTION_PROMPT = """你是文件欄位抽取器。請依指定 schema 從以下頁面抽取資料。
規則：
1. 不得猜測；看不清楚或文件沒有的值請填 null。
2. 每個重要值都保留一開始編號的 page_number 與最多 300 字的短 evidence_text。
3. evidence_text 只摘錄支持該值的局部原文，不要轉錄整頁。
4. additional_fields 依文件出現順序填入，不建立任意巢狀物件。
5. 保留文件中的原始日期、金額與識別字串；正規化和檢核由後續規則負責。
"""

ModelFactory = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Provider-neutral result with raw response intentionally discarded."""

    provider: ProviderName
    model: str
    parsed: DocumentExtraction
    usage: TokenUsage
    warnings: tuple[str, ...] = ()


def build_multimodal_message(document: NormalizedDocument) -> dict[str, Any]:
    """Create standard LangChain multimodal content blocks in page order."""

    content: list[dict[str, Any]] = [{"type": "text", "text": EXTRACTION_PROMPT}]
    for page in document.pages:
        content.append({"type": "text", "text": f"以下是第 {page.page_number} 頁："})
        content.append(
            {
                "type": "image",
                "base64": base64.b64encode(page.data).decode("ascii"),
                "mime_type": page.mime_type,
            }
        )
    return {"role": "user", "content": content}


def build_provider_schema(schema: SchemaName) -> dict[str, Any]:
    """Build provider JSON Schema without model-generated control metadata."""

    schema_json = deepcopy(SchemaRegistry.get(schema).model_json_schema())
    properties = schema_json.get("properties")
    if isinstance(properties, dict):
        properties.pop("schema_name", None)
    required = schema_json.get("required")
    if isinstance(required, list):
        schema_json["required"] = [field for field in required if field != "schema_name"]
    return schema_json


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def extract_token_usage(raw_message: Any) -> TokenUsage:
    """Normalize common LangChain provider usage metadata without retaining raw payloads."""

    usage = getattr(raw_message, "usage_metadata", None)
    if not isinstance(usage, Mapping):
        response_metadata = getattr(raw_message, "response_metadata", None)
        if isinstance(response_metadata, Mapping):
            candidate = response_metadata.get("token_usage") or response_metadata.get("usage")
            usage = candidate if isinstance(candidate, Mapping) else None

    if not isinstance(usage, Mapping):
        return TokenUsage()

    input_tokens = _non_negative_int(usage.get("input_tokens"))
    if input_tokens is None:
        input_tokens = _non_negative_int(usage.get("prompt_tokens"))
    output_tokens = _non_negative_int(usage.get("output_tokens"))
    if output_tokens is None:
        output_tokens = _non_negative_int(usage.get("completion_tokens"))
    total_tokens = _non_negative_int(usage.get("total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def safe_parsing_error_summary(error: Any) -> str:
    """Describe parser failures using only types and schema paths, never values."""

    error_type = type(error).__name__
    current = error
    for _ in range(4):
        if isinstance(current, ValidationError):
            paths = []
            for detail in current.errors(
                include_url=False,
                include_context=False,
                include_input=False,
            )[:5]:
                path = ".".join(str(part) for part in detail.get("loc", ())) or "<root>"
                paths.append(f"{path}:{detail.get('type', 'validation_error')}")
            return f"{error_type}；Pydantic 路徑：{', '.join(paths)}"
        current = getattr(current, "__cause__", None)
        if current is None:
            break
    return error_type


class LangChainStructuredExtractor:
    """Single-request structured extraction; no Agent loop is involved."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        model_factory: ModelFactory = init_chat_model,
    ) -> None:
        self._settings = settings
        self._model_factory = model_factory

    def extract(
        self,
        document: NormalizedDocument,
        schema: SchemaName,
        provider: ProviderName,
    ) -> ExtractionResult:
        provider_config = self._settings.provider_config(provider)
        schema_model = SchemaRegistry.get(schema)
        model_provider = "google_genai" if provider == "gemini" else "openai"

        try:
            model = self._model_factory(
                provider_config.model,
                model_provider=model_provider,
                api_key=provider_config.api_key.get_secret_value(),
                max_tokens=self._settings.model_max_tokens,
            )
            structured_model = model.with_structured_output(
                build_provider_schema(schema),
                include_raw=True,
            )
            response = structured_model.invoke([build_multimodal_message(document)])
        except (ProviderInvocationError, StructuredOutputError):
            raise
        except Exception as exc:
            error_type = type(exc).__name__
            raise ProviderInvocationError(
                f"{provider} 模型呼叫失敗（{error_type}）；未保存完整 API 回應。"
            ) from None

        if not isinstance(response, Mapping):
            raise StructuredOutputError("供應商未回傳預期的 structured output 容器。")

        parsing_error = response.get("parsing_error")
        parsed = response.get("parsed")
        if parsing_error is not None or parsed is None:
            summary = (
                safe_parsing_error_summary(parsing_error)
                if parsing_error is not None
                else "MissingParsedValue"
            )
            raise StructuredOutputError(f"結構化回應驗證失敗（{summary}）。")

        try:
            if hasattr(parsed, "model_dump"):
                parsed = parsed.model_dump()
            if not isinstance(parsed, Mapping):
                raise TypeError("structured output is not a mapping")
            payload = dict(parsed)
            payload["schema_name"] = schema
            parsed = schema_model.model_validate(payload)
        except (ValidationError, TypeError, ValueError):
            raise StructuredOutputError("結構化回應未通過 Pydantic schema 驗證。") from None

        return ExtractionResult(
            provider=provider,
            model=provider_config.model,
            parsed=parsed,
            usage=extract_token_usage(response.get("raw")),
        )
