"""Explicit two-request paid API smoke test for Phase 1.

This script is intentionally excluded from the default pytest path. It creates
synthetic documents in a temporary directory, prints metadata only, and deletes
the inputs on exit.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf
from PIL import Image, ImageDraw

from doc_inspector import inspect_document
from doc_inspector.config import load_settings
from doc_inspector.costs import parse_positive_usd, require_approved_budget
from doc_inspector.schemas import InspectionBundle

SMOKE_MAX_OUTPUT_TOKENS = 4096
SMOKE_ESTIMATED_COST_USD = Decimal("0.045932")


def positive_decimal(value: str) -> Decimal:
    """Parse a finite positive decimal for an explicit cost approval."""

    try:
        return parse_positive_usd(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def validate_approved_budget(approved_max_cost_usd: Decimal) -> None:
    """Refuse calls when the approved ceiling is below the documented estimate."""

    try:
        require_approved_budget(
            approved_usd=approved_max_cost_usd,
            estimated_usd=SMOKE_ESTIMATED_COST_USD,
        )
    except ValueError as exc:
        raise SystemExit(f"拒絕執行：{exc}") from None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="執行兩次會產生成本的 Phase 1 API smoke test。")
    parser.add_argument(
        "--confirm-paid-api",
        action="store_true",
        help="確認已取得作者對本次兩個 API 請求的成本批准。",
    )
    parser.add_argument(
        "--approved-max-cost-usd",
        type=positive_decimal,
        default=None,
        help=(
            "作者核准的本次美元成本上限，必須大於或等於保守估算 "
            f"US${SMOKE_ESTIMATED_COST_USD}。"
        ),
    )
    parser.add_argument(
        "--approved-gemini-model",
        default=None,
        help="作者核准且必須與 GEMINI_MODEL 完全相同的模型 ID。",
    )
    parser.add_argument(
        "--approved-openai-model",
        default=None,
        help="作者核准且必須與 OPENAI_MODEL 完全相同的模型 ID。",
    )
    return parser.parse_args()


def create_synthetic_receipt(path: Path) -> None:
    image = Image.new("RGB", (900, 700), "white")
    draw = ImageDraw.Draw(image)
    lines = (
        "SYNTHETIC TEST RECEIPT - NOT REAL",
        "Merchant: Civic Demo Shop",
        "Receipt No: TEST-20260723-001",
        "Date: 2026-07-23",
        "Item: Document folder  Qty: 2  Unit: 50  Amount: 100",
        "Subtotal: 100",
        "Tax: 5",
        "Total: 105 TWD",
    )
    for index, line in enumerate(lines):
        draw.text((40, 40 + index * 65), line, fill="black")
    image.save(path, format="PNG")


def create_synthetic_application(path: Path) -> None:
    document = pymupdf.open()
    first = document.new_page(width=595, height=842)
    first.insert_text((50, 70), "SYNTHETIC TEST APPLICATION - NOT REAL", fontsize=14)
    first.insert_text((50, 120), "Program: Community Accessibility Demo", fontsize=12)
    first.insert_text((50, 160), "Application date: 2026-07-23", fontsize=12)
    first.insert_text((50, 200), "Applicant: Test Person", fontsize=12)
    first.insert_text((50, 240), "Requested amount: TWD 3000", fontsize=12)

    second = document.new_page(width=595, height=842)
    second.insert_text((50, 70), "SYNTHETIC LINE ITEMS - NOT REAL", fontsize=14)
    second.insert_text((50, 120), "Accessible sign: TWD 1000", fontsize=12)
    second.insert_text((50, 160), "Portable ramp: TWD 2000", fontsize=12)
    second.insert_text((50, 210), "Declared total: TWD 3000", fontsize=12)
    document.save(path)
    document.close()


def metadata_only(bundle: InspectionBundle) -> dict[str, object]:
    return {
        "provider": bundle.provider,
        "model": bundle.model,
        "schema": bundle.extraction.schema_name,
        "page_count": bundle.page_count,
        "usage": bundle.usage.model_dump(),
        "warning_count": len(bundle.warnings),
    }


def main() -> int:
    args = parse_args()
    if (
        not args.confirm_paid_api
        or args.approved_max_cost_usd is None
        or args.approved_gemini_model is None
        or args.approved_openai_model is None
    ):
        raise SystemExit(
            "拒絕執行：必須提供 --confirm-paid-api、--approved-max-cost-usd、"
            "--approved-gemini-model 與 --approved-openai-model。"
        )
    validate_approved_budget(args.approved_max_cost_usd)

    settings = load_settings()
    if settings.model_max_tokens > SMOKE_MAX_OUTPUT_TOKENS:
        raise SystemExit(
            "拒絕執行：本次成本估算要求 MODEL_MAX_TOKENS 不得超過 4096。"
        )
    if settings.render_dpi > 200 or settings.max_image_long_edge > 2400:
        raise SystemExit("拒絕執行：本次成本估算要求渲染上限不得高於 200 DPI／2400 px。")

    gemini_config = settings.provider_config("gemini")
    openai_config = settings.provider_config("openai")
    if gemini_config.model != args.approved_gemini_model:
        raise SystemExit("拒絕執行：GEMINI_MODEL 與作者核准的模型 ID 不一致。")
    if openai_config.model != args.approved_openai_model:
        raise SystemExit("拒絕執行：OPENAI_MODEL 與作者核准的模型 ID 不一致。")

    print(
        "已確認兩次請求的保守估算／核准上限："
        f"US${SMOKE_ESTIMATED_COST_USD}／US${args.approved_max_cost_usd}"
    )
    with TemporaryDirectory(prefix="doc-inspector-smoke-") as temporary:
        temporary_path = Path(temporary)
        receipt_path = temporary_path / "synthetic-receipt.png"
        application_path = temporary_path / "synthetic-application.pdf"
        create_synthetic_receipt(receipt_path)
        create_synthetic_application(application_path)

        application = inspect_document(application_path, "subsidy_application", "gemini")
        print(metadata_only(application))
        receipt = inspect_document(receipt_path, "receipt", "openai")
        print(metadata_only(receipt))

    print("smoke test 完成；合成暫存文件已清除。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
