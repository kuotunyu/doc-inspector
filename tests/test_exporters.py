from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

from doc_inspector.exporters import export_bundle_excel, export_bundle_json
from doc_inspector.rules import inspect_extraction
from doc_inspector.schemas import (
    InspectionBundle,
    LocatedValue,
    Receipt,
    ReceiptLineItem,
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

    for sheet_name in ("extraction", "line_items", "checks", "metadata"):
        assert f'name="{sheet_name}"' in workbook_xml
    assert "=NOT_A_FORMULA" in shared_strings
    assert "<f>NOT_A_FORMULA</f>" not in sheet_xml
