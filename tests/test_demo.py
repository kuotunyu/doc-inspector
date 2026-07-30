from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
import pymupdf

from doc_inspector.demo import (
    DEMO_SEED,
    PDF_FONT_NAME,
    PROVENANCE_DEMO_NAME,
    WATERMARK,
    _font_path,
    demo_extractions,
    generate_demo_artifacts,
    provenance_demo_extraction,
    render_provenance_demo_pdf,
)
from doc_inspector.ingest import normalize_document
from doc_inspector.provenance import resolve_provenance
from doc_inspector.rules import inspect_extraction


def test_demo_scenarios_cover_expected_levels() -> None:
    levels = {
        name: inspect_extraction(extraction).overall_level
        for name, extraction in demo_extractions().items()
    }

    assert levels == {
        "subsidy_green": "green",
        "subsidy_yellow": "yellow",
        "subsidy_red": "red",
        "receipt_green": "green",
    }


def test_generate_demo_artifacts_writes_safe_manifest_and_exports(tmp_path: Path) -> None:
    artifacts = generate_demo_artifacts(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["seed"] == DEMO_SEED
    assert manifest["watermark"] == WATERMARK
    assert manifest["contains_real_personal_data"] is False
    assert len(artifacts) == 4
    for artifact in artifacts:
        assert artifact.image_path.is_file()
        assert artifact.extraction_path.is_file()
        assert artifact.bundle_path.is_file()
        assert artifact.workbook_path.is_file()
        with Image.open(artifact.image_path) as image:
            assert image.size == (1600, 2200)


def test_pdf_demo_font_is_bundled_and_covers_traditional_chinese() -> None:
    font = pymupdf.Font(PDF_FONT_NAME)

    for character in "補助申請人金額頁證":
        assert font.has_glyph(ord(character)), f"缺少字符：{character}"
    assert font.text_length("補助方案", 12) > 0


def test_provenance_demo_pdf_is_deterministic_and_small(tmp_path: Path) -> None:
    first = render_provenance_demo_pdf(tmp_path / "a.pdf").read_bytes()
    second = render_provenance_demo_pdf(tmp_path / "b.pdf").read_bytes()

    assert first == second
    assert len(first) < 200_000


def test_provenance_demo_stays_green_while_showing_every_source_state(
    tmp_path: Path,
) -> None:
    pdf = render_provenance_demo_pdf(tmp_path / f"{PROVENANCE_DEMO_NAME}.pdf")
    extraction = provenance_demo_extraction()
    document = normalize_document(pdf)

    review = inspect_extraction(extraction)
    collection = resolve_provenance(
        extraction, document.text_layer, pages=document.pages
    )

    assert review.overall_level == "green"
    assert len(document.pages) == 3
    assert [layer.source for layer in document.text_layer.pages] == [
        "native_pdf_text",
        "native_pdf_text",
        "unavailable",
    ]
    assert {field.verification_status for field in collection.fields} == {
        "verified",
        "approximate",
        "ambiguous",
        "page_only",
        "unresolved",
    }
    assert all(
        field.bbox is None
        for field in collection.fields
        if field.verification_status
        in {"ambiguous", "page_only", "unresolved"}
    )


def test_manifest_records_the_provenance_demo_document(tmp_path: Path) -> None:
    generate_demo_artifacts(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["provenance_demo"]

    assert entry["name"] == PROVENANCE_DEMO_NAME
    assert entry["document"] == f"{PROVENANCE_DEMO_NAME}.pdf"
    assert entry["pages_with_text_layer"] == [1, 2]
    assert entry["image_only_pages"] == [3]
    assert len(entry["pdf_sha256"]) == 64
    assert (tmp_path / entry["document"]).is_file()


def test_font_path_supports_debian_noto_cjk(tmp_path: Path) -> None:
    regular = tmp_path / "NotoSansCJK-Regular.ttc"
    bold = tmp_path / "NotoSansCJK-Bold.ttc"
    regular.write_bytes(b"test-font")
    bold.write_bytes(b"test-font")

    assert _font_path(search_roots=(tmp_path,)) == regular
    assert _font_path(bold=True, search_roots=(tmp_path,)) == bold
