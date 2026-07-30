from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

from doc_inspector.exporters import (
    export_bundle_excel,
    export_bundle_json,
    format_bbox,
    provenance_field_index,
    provenance_table_rows,
)
from doc_inspector.ingest import DocumentTextLayer, PageTextLayer, PageToken
from doc_inspector.provenance import resolve_provenance
from doc_inspector.rules import inspect_extraction
from doc_inspector.schemas import (
    InspectionBundle,
    LocatedValue,
    NormalizedBBox,
    Receipt,
    ReceiptLineItem,
)


def _tokens(text: str, row: int) -> tuple[PageToken, ...]:
    return tuple(
        PageToken(
            text=character,
            bbox=NormalizedBBox(
                x0=10.0 + column * 20.0,
                y0=40.0 * row,
                x1=28.0 + column * 20.0,
                y1=40.0 * row + 30.0,
            ),
        )
        for column, character in enumerate(text)
        if not character.isspace()
    )


def provenance_bundle() -> InspectionBundle:
    """A bundle whose claims cover a verified, an ambiguous, and a missing field."""

    receipt = Receipt(
        merchant_name=LocatedValue(
            value="示範商店", page_number=1, evidence_text="店家名稱：示範商店"
        ),
        receipt_date=LocatedValue(
            value="2026-07-23", page_number=1, evidence_text="重複片語QQ"
        ),
        total=LocatedValue(value="105", page_number=1, evidence_text="不存在的證據"),
    )
    text_layer = DocumentTextLayer(
        pages=(
            PageTextLayer(
                page_number=1,
                source="native_pdf_text",
                tokens=(
                    *_tokens("店家名稱：示範商店", 1),
                    *_tokens("重複片語QQ", 2),
                    *_tokens("重複片語QQ", 3),
                ),
            ),
        )
    )
    return InspectionBundle(
        provider="gemini",
        model="configured-model",
        source_file_name="receipt.pdf",
        page_count=1,
        elapsed_ms=7,
        extraction=receipt,
        review_report=inspect_extraction(receipt),
        provenance=resolve_provenance(receipt, text_layer),
    )


def sample_bundle() -> InspectionBundle:
    receipt = Receipt(
        merchant_name=LocatedValue(value="=NOT_A_FORMULA", page_number=1, evidence_text="測試商店"),
        receipt_date=LocatedValue(value="2026-07-23", page_number=1),
        line_items=[
            ReceiptLineItem(
                description=LocatedValue(value="文件夾", page_number=1),
                quantity=LocatedValue(value="2", page_number=1),
                unit_price=LocatedValue(value="50", page_number=1),
                line_total=LocatedValue(value="100", page_number=1),
            )
        ],
        subtotal=LocatedValue(value="100", page_number=1),
        tax=LocatedValue(value="5", page_number=1),
        total=LocatedValue(value="105", page_number=1),
    )
    return InspectionBundle(
        provider="openai",
        model="configured-model",
        source_file_name="receipt.png",
        page_count=1,
        elapsed_ms=20,
        extraction=receipt,
        review_report=inspect_extraction(receipt),
    )


def test_json_export_round_trips_safe_bundle(tmp_path: Path) -> None:
    path = export_bundle_json(sample_bundle(), tmp_path / "bundle.json")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["source_file_name"] == "receipt.png"
    assert payload["review_report"]["status"] == "completed"
    assert str(tmp_path) not in path.read_text(encoding="utf-8")


def test_excel_export_has_fixed_sheets_and_disables_formula_injection(tmp_path: Path) -> None:
    path = export_bundle_excel(sample_bundle(), tmp_path / "bundle.xlsx")

    with ZipFile(path) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        shared_strings = archive.read("xl/sharedStrings.xml").decode("utf-8")
        sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")

    for sheet_name in ("extraction", "line_items", "checks", "provenance", "metadata"):
        assert f'name="{sheet_name}"' in workbook_xml
    assert "=NOT_A_FORMULA" in shared_strings
    assert "<f>NOT_A_FORMULA</f>" not in sheet_xml


def test_format_bbox_is_locale_independent() -> None:
    box = NormalizedBBox(x0=12.345, y0=0.0, x1=678.9, y1=1000.0)

    assert format_bbox(box) == "12.3,0.0,678.9,1000.0"
    assert format_bbox(None) is None


def test_provenance_rows_carry_the_full_machine_readable_contract() -> None:
    rows = provenance_table_rows(provenance_bundle())
    by_path = {row[0]: row for row in rows}

    assert by_path["merchant_name"][1] == "示範商店"
    assert by_path["merchant_name"][2] == "店家名稱：示範商店"
    assert by_path["merchant_name"][3] == 1
    assert by_path["merchant_name"][4] == 1
    assert by_path["merchant_name"][5] == "verified"
    assert by_path["merchant_name"][6] == "native_pdf_text"
    assert by_path["merchant_name"][7] is not None
    assert by_path["merchant_name"][8] == 1.0
    assert by_path["receipt_date"][5] == "ambiguous"
    assert by_path["receipt_date"][7] is None
    assert "無法唯一定位" in by_path["receipt_date"][9]
    assert by_path["total"][5] == "unresolved"
    assert by_path["total"][4] is None


def test_provenance_rows_are_empty_for_a_v1_0_bundle() -> None:
    assert provenance_table_rows(sample_bundle()) == []
    assert provenance_field_index(sample_bundle()) == {}


def test_provenance_index_is_keyed_by_stable_field_path() -> None:
    index = provenance_field_index(provenance_bundle())

    assert index["merchant_name"].verification_status == "verified"
    assert index["total"].verification_status == "unresolved"


def test_provenance_export_leaks_neither_paths_nor_page_dumps(tmp_path: Path) -> None:
    bundle = provenance_bundle()

    json_path = export_bundle_json(bundle, tmp_path / "bundle.json")
    excel_path = export_bundle_excel(bundle, tmp_path / "bundle.xlsx")
    payload = json_path.read_text(encoding="utf-8")
    with ZipFile(excel_path) as archive:
        shared_strings = archive.read("xl/sharedStrings.xml").decode("utf-8")

    for leaked in (str(tmp_path), "C:\\Users\\", "/home/", "/Users/"):
        assert leaked not in payload
        assert leaked not in shared_strings
    assert "店家名稱：示範商店" in payload
    assert "重複片語QQ重複片語QQ" not in payload
    assert "重複片語QQ重複片語QQ" not in shared_strings
    assert len(payload) < 20_000


def test_excel_metadata_sheet_reports_the_provenance_summary(tmp_path: Path) -> None:
    path = export_bundle_excel(provenance_bundle(), tmp_path / "bundle.xlsx")

    with ZipFile(path) as archive:
        shared_strings = archive.read("xl/sharedStrings.xml").decode("utf-8")

    for key in (
        "provenance_version",
        "provenance_coordinate_space",
        "provenance_verified",
        "provenance_ambiguous",
        "provenance_unresolved",
    ):
        assert key in shared_strings
