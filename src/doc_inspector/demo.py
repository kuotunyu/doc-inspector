"""Deterministic, visibly synthetic demo documents and expected extractions."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFont

from doc_inspector.exporters import export_bundle_excel, export_bundle_json
from doc_inspector.rules import inspect_extraction
from doc_inspector.schemas import (
    ApplicationLineItem,
    DocumentExtraction,
    DocumentPerson,
    InspectionBundle,
    LocatedIdType,
    LocatedValue,
    Receipt,
    ReceiptLineItem,
    SubsidyApplication,
)

DEMO_SEED = 20260723
WATERMARK = "合成測試資料／非真實文件"


def _value(value: str, evidence: str | None = None) -> LocatedValue:
    return LocatedValue(value=value, page_number=1, evidence_text=evidence or value)


def _person(*, id_type: str, id_number: str) -> DocumentPerson:
    return DocumentPerson(
        role=_value("申請人"),
        name=_value("測試申請人甲"),
        id_type=LocatedIdType(value=id_type, page_number=1, evidence_text=id_type),
        id_number=_value(id_number),
        birth_date=_value("1990-01-01"),
    )


def _subsidy(
    *,
    id_type: str,
    id_number: str,
    application_date: str,
    requested: str,
    items: tuple[tuple[str, str], ...],
    declared: str,
) -> SubsidyApplication:
    return SubsidyApplication(
        program_name=_value("安心生活測試補助"),
        application_date=_value(application_date),
        applicants=[_person(id_type=id_type, id_number=id_number)],
        contact_phone=_value("0900-000-000"),
        contact_email=_value("demo@example.invalid"),
        address=_value("測試市示範區文件路 1 號"),
        bank_account_display_name=_value("測試申請人甲"),
        requested_amount=_value(requested),
        line_items=[
            ApplicationLineItem(description=_value(description), amount=_value(amount))
            for description, amount in items
        ],
        declared_total=_value(declared),
    )


def demo_extractions() -> dict[str, DocumentExtraction]:
    """Return the fixed green/yellow/red/receipt demo scenarios."""

    receipt = Receipt(
        merchant_name=_value("示範生活商店"),
        receipt_number=_value("DEMO-20260723-001"),
        receipt_date=_value("2026-07-23"),
        currency=_value("TWD"),
        line_items=[
            ReceiptLineItem(
                description=_value("文件影印服務"),
                quantity=_value("2"),
                unit_price=_value("100"),
                line_total=_value("200"),
            ),
            ReceiptLineItem(
                description=_value("資料整理服務"),
                quantity=_value("1"),
                unit_price=_value("100"),
                line_total=_value("100"),
            ),
        ],
        subtotal=_value("300"),
        tax=_value("15"),
        discount=_value("0"),
        fees=_value("0"),
        total=_value("315"),
    )
    return {
        "subsidy_green": _subsidy(
            id_type="citizen_id",
            id_number="A123456789",
            application_date="2026-07-23",
            requested="1200",
            items=(("生活支持", "800"), ("交通支持", "400")),
            declared="1200",
        ),
        "subsidy_yellow": _subsidy(
            id_type="passport",
            id_number="DEMO-PASSPORT-001",
            application_date="2026-07-23",
            requested="1200",
            items=(("生活支持", "800"), ("交通支持", "400")),
            declared="1200",
        ),
        "subsidy_red": _subsidy(
            id_type="citizen_id",
            id_number="A123456780",
            application_date="2026-02-30",
            requested="1300",
            items=(("生活支持", "900"), ("交通支持", "400")),
            declared="1200",
        ),
        "receipt_green": receipt,
    }


@dataclass(frozen=True)
class DemoArtifact:
    name: str
    expected_level: str
    image_path: Path
    extraction_path: Path
    bundle_path: Path
    workbook_path: Path
    sha256: str


def _font_path(*, bold: bool = False) -> Path:
    fonts_root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    names = (
        ("msjhbd.ttc", "NotoSansCJK-Bold.ttc", "arialbd.ttf")
        if bold
        else ("msjh.ttc", "NotoSansCJK-Regular.ttc", "arial.ttf")
    )
    for name in names:
        candidate = fonts_root / name
        if candidate.is_file():
            return candidate
    raise RuntimeError("找不到可顯示正體中文的系統字型。")


def _display_rows(extraction: DocumentExtraction) -> list[tuple[str, str]]:
    if isinstance(extraction, SubsidyApplication):
        person = extraction.applicants[0]
        rows = [
            ("補助方案", extraction.program_name.value or ""),
            ("申請日期", extraction.application_date.value or ""),
            ("申請人", person.name.value or ""),
            ("證件類型", person.id_type.value or ""),
            ("證件號碼", person.id_number.value or ""),
            ("出生日期", person.birth_date.value or ""),
            ("聯絡電話", extraction.contact_phone.value or ""),
            ("申請金額", extraction.requested_amount.value or ""),
        ]
        rows.extend(
            (f"項目 {index + 1}｜{item.description.value}", item.amount.value or "")
            for index, item in enumerate(extraction.line_items)
        )
        rows.append(("申報合計", extraction.declared_total.value or ""))
        return rows
    rows = [
        ("商店", extraction.merchant_name.value or ""),
        ("單據號碼", extraction.receipt_number.value or ""),
        ("日期", extraction.receipt_date.value or ""),
    ]
    rows.extend(
        (
            f"{item.description.value}　{item.quantity.value} × {item.unit_price.value}",
            item.line_total.value or "",
        )
        for item in extraction.line_items
    )
    rows.extend(
        [
            ("小計", extraction.subtotal.value or ""),
            ("稅額", extraction.tax.value or ""),
            ("總計", extraction.total.value or ""),
        ]
    )
    return rows


def _render_document(name: str, extraction: DocumentExtraction, destination: Path) -> None:
    randomizer = random.Random(f"{DEMO_SEED}:{name}")
    canvas = Image.new("RGB", (1600, 2200), "#F7F1E4")
    draw = ImageDraw.Draw(canvas)
    title_font = ImageFont.truetype(str(_font_path(bold=True)), 82)
    heading_font = ImageFont.truetype(str(_font_path(bold=True)), 38)
    body_font = ImageFont.truetype(str(_font_path()), 34)
    small_font = ImageFont.truetype(str(_font_path()), 27)
    stamp_font = ImageFont.truetype(str(_font_path(bold=True)), 60)

    draw.rectangle((80, 70, 1520, 2130), fill="#FFFDF7", outline="#17324D", width=6)
    draw.rectangle((80, 70, 1520, 98), fill="#17324D")
    draw.text((130, 150), "文件預檢台", font=heading_font, fill="#D14B36")
    title = "補助申請書（合成）" if isinstance(extraction, SubsidyApplication) else "消費明細（合成）"
    draw.text((130, 225), title, font=title_font, fill="#17324D")
    draw.text((132, 335), f"案例代碼：{name}　固定種子：{DEMO_SEED}", font=small_font, fill="#66717C")
    draw.line((130, 395, 1470, 395), fill="#17324D", width=3)

    y = 450
    for index, (label, value) in enumerate(_display_rows(extraction)):
        shade = "#F2EBDD" if index % 2 == 0 else "#FFFDF7"
        draw.rectangle((130, y, 1470, y + 96), fill=shade)
        draw.text((165, y + 25), label, font=body_font, fill="#17324D")
        draw.text((845, y + 25), str(value), font=body_font, fill="#25313C")
        y += 102

    draw.line((130, 1885, 1470, 1885), fill="#17324D", width=2)
    draw.text(
        (130, 1920),
        "本頁所有姓名、聯絡資料、證件與金額均為程式產生的測試內容。",
        font=small_font,
        fill="#66717C",
    )
    draw.text((130, 1980), "不得作為申請、核銷或身分證明使用。", font=small_font, fill="#66717C")

    watermark = Image.new("RGBA", (1250, 180), (255, 255, 255, 0))
    watermark_draw = ImageDraw.Draw(watermark)
    watermark_draw.text((30, 40), WATERMARK, font=stamp_font, fill=(209, 75, 54, 88))
    rotated = watermark.rotate(-25 + randomizer.randint(-2, 2), expand=True, resample=Image.Resampling.BICUBIC)
    canvas.paste(rotated, (180, 880), rotated)
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="PNG", compress_level=9)


def generate_demo_artifacts(destination: Path) -> list[DemoArtifact]:
    """Generate images, sidecars, exports, and a deterministic manifest."""

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    artifacts: list[DemoArtifact] = []
    for name, extraction in demo_extractions().items():
        report = inspect_extraction(extraction)
        image_path = destination / f"{name}.png"
        extraction_path = destination / f"{name}.expected.json"
        bundle_path = destination / f"{name}.inspection.json"
        workbook_path = destination / f"{name}.inspection.xlsx"
        _render_document(name, extraction, image_path)
        extraction_path.write_text(
            extraction.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        bundle = InspectionBundle(
            provider="gemini",
            model="synthetic-ground-truth",
            source_file_name=image_path.name,
            page_count=1,
            elapsed_ms=0,
            extraction=extraction,
            review_report=report,
            warnings=["此結果由合成資料標準答案產生，未呼叫雲端模型。"],
        )
        export_bundle_json(bundle, bundle_path)
        export_bundle_excel(bundle, workbook_path)
        artifacts.append(
            DemoArtifact(
                name=name,
                expected_level=report.overall_level,
                image_path=image_path,
                extraction_path=extraction_path,
                bundle_path=bundle_path,
                workbook_path=workbook_path,
                sha256=sha256(image_path.read_bytes()).hexdigest(),
            )
        )

    manifest = {
        "seed": DEMO_SEED,
        "watermark": WATERMARK,
        "contains_real_personal_data": False,
        "artifacts": [
            {
                "name": artifact.name,
                "expected_level": artifact.expected_level,
                "image": artifact.image_path.name,
                "expected_extraction": artifact.extraction_path.name,
                "inspection_json": artifact.bundle_path.name,
                "inspection_excel": artifact.workbook_path.name,
                "image_sha256": artifact.sha256,
            }
            for artifact in artifacts
        ],
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return artifacts
