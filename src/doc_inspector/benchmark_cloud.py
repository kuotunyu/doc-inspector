"""Cloud structured extraction used only by the explicit XFUND benchmark runner."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from langchain.chat_models import init_chat_model
from pydantic import ValidationError

from doc_inspector.benchmark import BenchmarkPrediction
from doc_inspector.config import AppSettings
from doc_inspector.ingest import NormalizedDocument
from doc_inspector.providers import ModelFactory, extract_token_usage
from doc_inspector.schemas import TokenUsage
from doc_inspector.types import ProviderName

BENCHMARK_PROMPT = """你是表單 key-value 抽取器。請從這張 XFUND 表單圖片抽出所有明確的欄位名稱與對應值。
規則：
1. key 必須是圖片上可見的欄位標籤，value 必須是與它連結、同列或明確相鄰的可見值。
2. 不得猜測、補寫、翻譯或正規化；保留圖片中的原始文字。
3. 不要把表頭、說明文字或沒有對應值的文字當成 pair。
4. 相同 key 若在文件中出現多次，請保留為多筆 pair。
5. 只回傳 schema 要求的 pairs。
"""

PRICE_PER_MILLION: dict[ProviderName, tuple[Decimal, Decimal]] = {
    "gemini": (Decimal("0.30"), Decimal("2.50")),
    "openai": (Decimal("0.25"), Decimal("2.00")),
}


@dataclass(frozen=True, slots=True)
class CloudBenchmarkResult:
    provider: ProviderName
    model: str
    prediction: BenchmarkPrediction
    usage: TokenUsage


def usage_cost_usd(provider: ProviderName, usage: TokenUsage) -> Decimal | None:
    if usage.input_tokens is None or usage.output_tokens is None:
        return None
    input_price, output_price = PRICE_PER_MILLION[provider]
    return (
        Decimal(usage.input_tokens) * input_price
        + Decimal(usage.output_tokens) * output_price
    ) / Decimal(1_000_000)


def conservative_request_cost_usd(
    provider: ProviderName,
    *,
    input_tokens: int = 50_000,
    output_tokens: int = 4_096,
) -> Decimal:
    return usage_cost_usd(
        provider,
        TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
    ) or Decimal("0")


def build_benchmark_message(document: NormalizedDocument) -> dict[str, Any]:
    if len(document.pages) != 1:
        raise ValueError("XFUND benchmark 每份樣本必須正規化為單頁。")
    page = document.pages[0]
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": BENCHMARK_PROMPT},
            {
                "type": "image",
                "base64": base64.b64encode(page.data).decode("ascii"),
                "mime_type": page.mime_type,
            },
        ],
    }


class CloudBenchmarkExtractor:
    """One-request, provider-neutral benchmark extractor with no raw retention."""

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
        provider: ProviderName,
    ) -> CloudBenchmarkResult:
        config = self._settings.provider_config(provider)
        model_provider = "google_genai" if provider == "gemini" else "openai"
        try:
            model = self._model_factory(
                config.model,
                model_provider=model_provider,
                api_key=config.api_key.get_secret_value(),
                max_tokens=self._settings.model_max_tokens,
            )
            structured = model.with_structured_output(
                BenchmarkPrediction.model_json_schema(),
                include_raw=True,
            )
            response = structured.invoke([build_benchmark_message(document)])
        except Exception as exc:
            raise RuntimeError(f"{provider} benchmark 呼叫失敗（{type(exc).__name__}）。") from None

        if not isinstance(response, Mapping):
            raise RuntimeError("benchmark structured output 容器無效。")
        parsing_error = response.get("parsing_error")
        parsed = response.get("parsed")
        if parsing_error is not None or parsed is None:
            error_type = type(parsing_error).__name__ if parsing_error is not None else "MissingParsedValue"
            raise RuntimeError(f"benchmark structured output 解析失敗（{error_type}）。")
        try:
            prediction = BenchmarkPrediction.model_validate(parsed)
        except (ValidationError, TypeError, ValueError):
            raise RuntimeError("benchmark prediction 未通過 schema 驗證。") from None
        return CloudBenchmarkResult(
            provider=provider,
            model=config.model,
            prediction=prediction,
            usage=extract_token_usage(response.get("raw")),
        )
