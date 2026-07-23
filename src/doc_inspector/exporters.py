"""Safe JSON and styled Excel exporters shared by CLI and Gradio."""

from __future__ import annotations

from math import ceil
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel
import xlsxwriter

from doc_inspector.schemas import InspectionBundle, LocatedIdType, LocatedValue


def export_bundle_json(bundle: InspectionBundle, destination: Path) -> Path:
    """Write a UTF-8, indented bundle without introducing extra fields."""

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(bundle.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return destination


def _located_row(path: str, value: LocatedValue | LocatedIdType) -> tuple[str, Any, int | None, str | None]:
    return path, value.value, value.page_number, value.evidence_text


def _walk_located(value: Any, path: str = "") -> Iterable[tuple[str, Any, int | None, str | None]]:
    if isinstance(value, (LocatedValue, LocatedIdType)):
        yield _located_row(path, value)
    elif isinstance(value, BaseModel):
        for field_name in type(value).model_fields:
            if field_name in {"schema_name", "line_items", "extraction_warnings"}:
                continue
            child_path = f"{path}.{field_name}" if path else field_name
            yield from _walk_located(getattr(value, field_name), child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_path = f"{path}.{index}" if path else str(index)
            yield from _walk_located(item, child_path)


def _line_item_rows(bundle: InspectionBundle) -> list[tuple[str, int, str, Any, int | None, str | None]]:
    rows = []
    for index, item in enumerate(bundle.extraction.line_items):
        for field_name in type(item).model_fields:
            value = getattr(item, field_name)
            if isinstance(value, (LocatedValue, LocatedIdType)):
                rows.append(
                    (
                        bundle.extraction.schema_name,
                        index + 1,
                        field_name,
                        value.value,
                        value.page_number,
                        value.evidence_text,
                    )
                )
    return rows


def extraction_table_rows(bundle: InspectionBundle) -> list[tuple[str, Any, int | None, str | None]]:
    """Return UI-ready extraction rows without exposing local paths."""

    return list(_walk_located(bundle.extraction))


def check_table_rows(bundle: InspectionBundle) -> list[tuple[str, str, str, str, str | None, str | None]]:
    """Return UI-ready deterministic check rows."""

    return [
        (
            check.rule_id,
            check.level,
            check.message,
            ", ".join(check.field_paths),
            check.observed,
            check.expected,
        )
        for check in bundle.review_report.checks
    ]


def _write_table_sheet(
    workbook: xlsxwriter.Workbook,
    name: str,
    headers: list[str],
    rows: list[tuple[Any, ...]],
    widths: list[int],
) -> None:
    sheet = workbook.add_worksheet(name)
    sheet.hide_gridlines(2)
    sheet.freeze_panes(1, 0)
    header = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFDF7",
            "bg_color": "#17324D",
            "bottom": 2,
            "bottom_color": "#D14B36",
            "align": "left",
            "valign": "vcenter",
        }
    )
    body = workbook.add_format({"font_color": "#25313C", "valign": "top"})
    wrapped = workbook.add_format({"font_color": "#25313C", "valign": "top", "text_wrap": True})
    sheet.set_row(0, 26)
    sheet.write_row(0, 0, headers, header)
    for row_index, row in enumerate(rows, start=1):
        estimated_lines = max(
            (
                ceil(len(str(value)) / max(widths[column_index] - 2, 1))
                for column_index, value in enumerate(row)
                if value is not None
            ),
            default=1,
        )
        sheet.set_row(row_index, min(72, max(20, estimated_lines * 18)))
        for column_index, value in enumerate(row):
            selected_format = wrapped if isinstance(value, str) else body
            sheet.write(row_index, column_index, value, selected_format)
    for column, width in enumerate(widths):
        sheet.set_column(column, column, width)
    if rows:
        sheet.autofilter(0, 0, len(rows), len(headers) - 1)


def export_bundle_excel(bundle: InspectionBundle, destination: Path) -> Path:
    """Write the fixed four-sheet workbook with formula injection disabled."""

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(
        destination,
        {"strings_to_formulas": False, "strings_to_urls": False},
    )
    try:
        extraction_rows = extraction_table_rows(bundle)
        _write_table_sheet(
            workbook,
            "extraction",
            ["field_path", "value", "page_number", "evidence_text"],
            extraction_rows,
            [34, 28, 14, 52],
        )
        _write_table_sheet(
            workbook,
            "line_items",
            ["schema", "item_index", "field", "value", "page_number", "evidence_text"],
            _line_item_rows(bundle),
            [22, 12, 22, 24, 14, 48],
        )
        check_rows = check_table_rows(bundle)
        _write_table_sheet(
            workbook,
            "checks",
            ["rule_id", "level", "message", "field_paths", "observed", "expected"],
            check_rows,
            [30, 12, 48, 38, 28, 32],
        )
        checks_sheet = workbook.get_worksheet_by_name("checks")
        if checks_sheet is not None and check_rows:
            colors = {
                "red": ("#FDE8E5", "#9B2C1F"),
                "yellow": ("#FFF3CD", "#7A5A00"),
                "green": ("#E5F4EA", "#216E39"),
            }
            for level, (background, foreground) in colors.items():
                status_format = workbook.add_format({"bg_color": background, "font_color": foreground, "bold": True})
                checks_sheet.conditional_format(
                    1,
                    1,
                    len(check_rows),
                    1,
                    {"type": "text", "criteria": "containing", "value": level, "format": status_format},
                )

        metadata = [
            ("schema_version", bundle.schema_version),
            ("rules_version", bundle.rules_version),
            ("provider", bundle.provider),
            ("model", bundle.model),
            ("source_file_name", bundle.source_file_name),
            ("page_count", bundle.page_count),
            ("elapsed_ms", bundle.elapsed_ms),
            ("input_tokens", bundle.usage.input_tokens),
            ("output_tokens", bundle.usage.output_tokens),
            ("total_tokens", bundle.usage.total_tokens),
            ("overall_level", bundle.review_report.overall_level),
            ("warning_count", len(bundle.warnings)),
        ]
        _write_table_sheet(workbook, "metadata", ["key", "value"], metadata, [28, 54])
    finally:
        workbook.close()
    return destination
