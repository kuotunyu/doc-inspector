"""Deterministic, visibly synthetic demo documents and expected extractions."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFont
import pymupdf

from doc_inspector.exporters import export_bundle_excel, export_bundle_json
from doc_inspector.rules import inspect_extraction
from doc_inspector.schemas import (
    AdditionalField,
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
PROVENANCE_DEMO_NAME = "subsidy_provenance"
PDF_FONT_NAME = "china-t"
"""MuPDF's bundled Traditional-Chinese face; no system font file is required."""


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


def provenance_demo_extraction() -> SubsidyApplication:
    """Return a green-light extraction whose claims exercise every provenance state.

    Evidence strings are written the way a model actually returns them—short
    quoted fragments—so the demo shows genuine verification rather than a
    hand-tuned happy path: one field claims the wrong page, one repeats twice in
    the document, one points at an image-only page, and one quotes text that is
    not in the document at all.
    """

    return SubsidyApplication(
        program_name=LocatedValue(
            value="安心生活測試補助",
            page_number=1,
            evidence_text="補助方案：安心生活測試補助",
        ),
        application_date=LocatedValue(
            value="2026-07-23",
            page_number=1,
            evidence_text="申請日期：2026-07-23",
        ),
        applicants=[
            DocumentPerson(
                role=LocatedValue(value="申請人", page_number=1, evidence_text="身分別：申請人本人"),
                name=LocatedValue(
                    value="測試申請人甲",
                    page_number=1,
                    evidence_text="申請人姓名：測試申請人甲",
                ),
                id_type=LocatedIdType(
                    value="citizen_id",
                    page_number=1,
                    evidence_text="證件種類：國民身分證",
                ),
                id_number=LocatedValue(
                    value="A123456789",
                    page_number=1,
                    evidence_text="證件號碼：A123456789",
                ),
                birth_date=LocatedValue(
                    value="1990-01-01",
                    page_number=1,
                    evidence_text="出生日期：1990-01-01",
                ),
            )
        ],
        contact_phone=LocatedValue(
            value="0900-000-000",
            page_number=1,
            evidence_text="聯絡電話：0900-000-000",
        ),
        contact_email=LocatedValue(
            value="demo@example.invalid",
            page_number=1,
            evidence_text="電子郵件：demo@example.invalid",
        ),
        address=LocatedValue(
            value="測試市示範區文件路 1 號",
            page_number=1,
            evidence_text="通訊地址：測試市示範區文件路 1 號",
        ),
        bank_account_display_name=LocatedValue(
            value="測試申請人甲專戶",
            page_number=2,
            evidence_text="撥款帳戶名稱：測試申請人甲專戶",
        ),
        requested_amount=LocatedValue(
            value="1200",
            page_number=1,
            evidence_text="申請金額：1,200",
        ),
        line_items=[
            ApplicationLineItem(
                description=LocatedValue(
                    value="生活支持費用",
                    page_number=2,
                    evidence_text="1. 生活支持費用",
                ),
                amount=LocatedValue(value="800", page_number=2, evidence_text="800 元"),
            ),
            ApplicationLineItem(
                description=LocatedValue(
                    value="交通支持費用",
                    page_number=2,
                    evidence_text="2. 交通支持費用",
                ),
                amount=LocatedValue(value="400", page_number=2, evidence_text="400 元"),
            ),
        ],
        declared_total=LocatedValue(value="1200", page_number=2, evidence_text="1,200"),
        additional_fields=[
            AdditionalField(
                label="附件金額",
                located_value=LocatedValue(
                    value="500",
                    page_number=3,
                    evidence_text="附件收據金額：500",
                ),
            ),
            AdditionalField(
                label="承辦註記",
                located_value=LocatedValue(
                    value="已完成初審",
                    page_number=1,
                    evidence_text="承辦註記：本件已完成初審並核章",
                ),
            ),
        ],
    )


_PROVENANCE_PAGE_ONE = (
    ("補助申請書（合成範例）", 22.0),
    ("合成測試資料／非真實文件，不得作為申請或身分證明使用。", 11.0),
    ("補助方案：安心生活測試補助", 14.0),
    ("申請日期：2026-07-23", 14.0),
    ("身分別：申請人本人", 14.0),
    ("申請人姓名：測試申請人甲", 14.0),
    ("證件種類：國民身分證", 14.0),
    ("證件號碼：A123456789", 14.0),
    ("出生日期：1990-01-01", 14.0),
    ("聯絡電話：0900-000-000", 14.0),
    ("電子郵件：demo@example.invalid", 14.0),
    ("通訊地址：測試市示範區文件路 1 號", 14.0),
)

_PROVENANCE_PAGE_TWO = (
    ("補助申請書（合成範例）　第 2 頁", 18.0),
    ("撥款帳戶名稱：測試申請人甲專戶", 14.0),
    ("補助明細", 14.0),
    ("1. 生活支持費用　　800 元", 14.0),
    ("2. 交通支持費用　　400 元", 14.0),
    ("申請金額：1,200", 14.0),
    ("申報總額：1,200", 14.0),
)

_PROVENANCE_PAGE_THREE = (
    ("附件：合成掃描頁", 20.0),
    ("這一頁以影像方式附上，沒有可用的文字層。", 12.0),
    ("附件收據金額：500", 14.0),
)


def _write_pdf_lines(
    page: pymupdf.Page,
    lines: tuple[tuple[str, float], ...],
    *,
    top: float = 90.0,
    left: float = 64.0,
    leading: float = 34.0,
) -> None:
    font = pymupdf.Font(PDF_FONT_NAME)
    writer = pymupdf.TextWriter(page.rect)
    baseline = top
    for text, size in lines:
        writer.append((left, baseline), text, font=font, fontsize=size)
        baseline += leading + max(0.0, size - 14.0)
    writer.write_text(page)


def render_provenance_demo_pdf(destination: Path) -> Path:
    """Write the fixed three-page provenance demo PDF.

    Pages one and two carry a real text layer so evidence can be verified
    locally; page three is deliberately rasterized so the interface has to admit
    that a page number came from the model and was never verified.
    """

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    try:
        _write_pdf_lines(document.new_page(width=595, height=842), _PROVENANCE_PAGE_ONE)
        _write_pdf_lines(document.new_page(width=595, height=842), _PROVENANCE_PAGE_TWO)

        scan_source = pymupdf.open()
        try:
            scan_page = scan_source.new_page(width=595, height=842)
            _write_pdf_lines(scan_page, _PROVENANCE_PAGE_THREE)
            pixmap = scan_page.get_pixmap(
                dpi=120, alpha=False, colorspace=pymupdf.csGRAY
            )
        finally:
            scan_source.close()
        image_page = document.new_page(width=595, height=842)
        image_page.insert_image(image_page.rect, stream=pixmap.tobytes("png"))

        document.subset_fonts(verbose=False)
        document.set_metadata({})
        document.save(str(destination), garbage=4, deflate=True, no_new_id=True)
    finally:
        document.close()
    return destination


@dataclass(frozen=True)
class DemoArtifact:
    name: str
    expected_level: str
    image_path: Path
    extraction_path: Path
    bundle_path: Path
    workbook_path: Path
    sha256: str


def _font_search_roots() -> tuple[Path, ...]:
    """Return supported Windows and Linux system font directories."""

    roots: list[Path] = []
    windir = os.environ.get("WINDIR")
    if windir:
        roots.append(Path(windir) / "Fonts")
    elif os.name == "nt":
        roots.append(Path(r"C:\Windows") / "Fonts")
    roots.extend(
        (
            Path("/usr/share/fonts/opentype/noto"),
            Path("/usr/share/fonts/truetype/noto"),
            Path("/usr/local/share/fonts"),
        )
    )
    return tuple(roots)


def _font_path(
    *,
    bold: bool = False,
    search_roots: tuple[Path, ...] | None = None,
) -> Path:
    names = (
        ("msjhbd.ttc", "NotoSansCJK-Bold.ttc", "arialbd.ttf")
        if bold
        else ("msjh.ttc", "NotoSansCJK-Regular.ttc", "arial.ttf")
    )
    roots = _font_search_roots() if search_roots is None else search_roots
    for root in roots:
        for name in names:
            candidate = root / name
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

    provenance_pdf = render_provenance_demo_pdf(
        destination / f"{PROVENANCE_DEMO_NAME}.pdf"
    )
    manifest = {
        "seed": DEMO_SEED,
        "watermark": WATERMARK,
        "contains_real_personal_data": False,
        "provenance_demo": {
            "name": PROVENANCE_DEMO_NAME,
            "document": provenance_pdf.name,
            "pdf_sha256": sha256(provenance_pdf.read_bytes()).hexdigest(),
            "pages_with_text_layer": [1, 2],
            "image_only_pages": [3],
        },
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
