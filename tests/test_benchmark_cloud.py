from __future__ import annotations

import base64
from decimal import Decimal

from doc_inspector.benchmark_cloud import (
    build_benchmark_message,
    conservative_request_cost_usd,
    usage_cost_usd,
)
from doc_inspector.ingest import NormalizedDocument, NormalizedPage
from doc_inspector.schemas import TokenUsage


def test_usage_cost_uses_current_documented_rates() -> None:
    usage = TokenUsage(input_tokens=50_000, output_tokens=4_096)

    assert usage_cost_usd("gemini", usage) == Decimal("0.025240")
    assert usage_cost_usd("openai", usage) == Decimal("0.020692")
    assert conservative_request_cost_usd("gemini") == Decimal("0.025240")


def test_usage_cost_is_unknown_when_provider_omits_tokens() -> None:
    assert usage_cost_usd("gemini", TokenUsage()) is None


def test_benchmark_message_contains_one_standard_image_block() -> None:
    document = NormalizedDocument(
        source_file_name="sample.jpg",
        pages=(NormalizedPage(page_number=1, data=b"image", width=10, height=10),),
    )

    message = build_benchmark_message(document)

    assert message["role"] == "user"
    assert [block["type"] for block in message["content"]] == ["text", "image"]
    assert base64.b64decode(message["content"][1]["base64"]) == b"image"
