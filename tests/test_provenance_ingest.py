"""PDF geometry tests: the stored bbox must match the rendered page, always."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
import pymupdf
import pytest

from doc_inspector.ingest import (
    extract_page_text_layer,
    normalize_document,
    normalized_bbox_from_rect,
)
from doc_inspector.provenance import build_match_index, normalize_match_text, search_evidence
from doc_inspector.schemas import BBOX_SCALE, NormalizedBBox

UNIQUE_TOKEN = "ALPHA-UNIQUE-9931"
FONT_NAME = "china-t"


def build_pdf(
    path: Path,
    *,
    rotation: int = 0,
    cropbox: tuple[float, float, float, float] | None = None,
    width: float = 595.0,
    height: float = 842.0,
) -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page(width=width, height=height)
        font = pymupdf.Font(FONT_NAME)
        writer = pymupdf.TextWriter(page.rect)
        writer.append((72, 140), "申請人姓名：測試申請人甲", font=font, fontsize=14)
        writer.append((300, height - 140), UNIQUE_TOKEN, font=font, fontsize=14)
        writer.write_text(page)
        if cropbox is not None:
            page.set_cropbox(pymupdf.Rect(*cropbox))
        if rotation:
            page.set_rotation(rotation)
        document.subset_fonts(verbose=False)
        document.set_metadata({})
        document.save(str(path), garbage=4, deflate=True, no_new_id=True)
    finally:
        document.close()
    return path


def ink_ratio_inside(page_png: bytes, bbox: NormalizedBBox) -> float:
    """Return the share of the page's dark pixels that fall inside the bbox."""

    with Image.open(BytesIO(page_png)) as image:
        image.load()
        grayscale = image.convert("L")
    width, height = grayscale.size
    box = (
        max(0, int(bbox.x0 / BBOX_SCALE * width) - 2),
        max(0, int(bbox.y0 / BBOX_SCALE * height) - 2),
        min(width, int(bbox.x1 / BBOX_SCALE * width) + 2),
        min(height, int(bbox.y1 / BBOX_SCALE * height) + 2),
    )
    total_dark = sum(1 for pixel in grayscale.tobytes() if pixel < 128)
    inside_dark = sum(1 for pixel in grayscale.crop(box).tobytes() if pixel < 128)
    return inside_dark / total_dark if total_dark else 0.0


def locate(document, token: str) -> tuple[int, NormalizedBBox]:
    result = search_evidence(
        build_match_index(document.text_layer), normalize_match_text(token)
    )
    assert len(result.candidates) == 1, f"expected one candidate for {token!r}"
    candidate = result.candidates[0]
    return candidate.page_number, candidate.bbox


class TestNormalizedBBoxFromRect:
    def test_maps_the_page_rectangle_onto_the_full_coordinate_space(self) -> None:
        page_rect = pymupdf.Rect(0, 0, 200, 400)

        box = normalized_bbox_from_rect(pymupdf.Rect(50, 100, 150, 300), page_rect)

        assert box is not None
        assert box.x0 == pytest.approx(250.0)
        assert box.x1 == pytest.approx(750.0)
        assert box.y0 == pytest.approx(250.0)
        assert box.y1 == pytest.approx(750.0)

    def test_clips_to_the_page_and_drops_fully_outside_rectangles(self) -> None:
        page_rect = pymupdf.Rect(0, 0, 200, 400)

        clipped = normalized_bbox_from_rect(pymupdf.Rect(-50, -50, 100, 100), page_rect)
        outside = normalized_bbox_from_rect(pymupdf.Rect(-80, -80, -10, -10), page_rect)

        assert clipped is not None
        assert clipped.x0 == 0.0
        assert clipped.y0 == 0.0
        assert outside is None

    def test_rejects_a_degenerate_page(self) -> None:
        assert normalized_bbox_from_rect(
            pymupdf.Rect(0, 0, 10, 10), pymupdf.Rect(0, 0, 0, 100)
        ) is None


class TestRenderedGeometry:
    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_bbox_lands_on_the_ink_for_every_page_rotation(
        self,
        tmp_path: Path,
        rotation: int,
    ) -> None:
        document = normalize_document(build_pdf(tmp_path / f"rot{rotation}.pdf", rotation=rotation))
        page_number, bbox = locate(document, UNIQUE_TOKEN)

        assert page_number == 1
        page = document.pages[0]
        assert ink_ratio_inside(page.data, bbox) > 0.2
        assert bbox.x1 <= BBOX_SCALE
        assert bbox.y1 <= BBOX_SCALE

    @pytest.mark.parametrize("rotation", [0, 90])
    def test_a_crop_box_does_not_shift_the_stored_coordinates(
        self,
        tmp_path: Path,
        rotation: int,
    ) -> None:
        document = normalize_document(
            build_pdf(
                tmp_path / f"crop{rotation}.pdf",
                rotation=rotation,
                cropbox=(40, 50, 520, 780),
            )
        )
        _, bbox = locate(document, UNIQUE_TOKEN)

        assert ink_ratio_inside(document.pages[0].data, bbox) > 0.2

    @pytest.mark.parametrize("render_dpi", [72, 150, 300])
    def test_coordinates_are_independent_of_render_dpi(
        self,
        tmp_path: Path,
        render_dpi: int,
    ) -> None:
        source = build_pdf(tmp_path / "dpi.pdf")

        baseline = locate(normalize_document(source, render_dpi=96), UNIQUE_TOKEN)[1]
        rendered = normalize_document(source, render_dpi=render_dpi)
        candidate = locate(rendered, UNIQUE_TOKEN)[1]

        assert candidate.iou(baseline) > 0.999
        assert ink_ratio_inside(rendered.pages[0].data, candidate) > 0.2

    def test_downscaling_a_large_page_keeps_the_bbox_aligned(self, tmp_path: Path) -> None:
        source = build_pdf(tmp_path / "big.pdf", width=1224.0, height=1584.0)

        document = normalize_document(source, render_dpi=200, max_long_edge=900)
        page = document.pages[0]
        _, bbox = locate(document, UNIQUE_TOKEN)

        assert max(page.width, page.height) == 900
        assert ink_ratio_inside(page.data, bbox) > 0.2


class TestTextLayerAvailability:
    def test_glyph_level_tokens_keep_evidence_highlights_tight(self, tmp_path: Path) -> None:
        document = normalize_document(build_pdf(tmp_path / "tight.pdf"))
        _, token_box = locate(document, UNIQUE_TOKEN)
        _, name_box = locate(document, "測試申請人甲")

        assert token_box.iou(name_box) == 0.0
        assert name_box.width < 400.0

    def test_an_image_only_page_reports_no_text_layer(self, tmp_path: Path) -> None:
        source = pymupdf.open()
        try:
            page = source.new_page(width=300, height=300)
            writer = pymupdf.TextWriter(page.rect)
            writer.append((30, 60), "掃描頁內容", font=pymupdf.Font(FONT_NAME), fontsize=14)
            writer.write_text(page)
            pixmap = page.get_pixmap(dpi=96, alpha=False)
        finally:
            source.close()

        target = pymupdf.open()
        try:
            image_page = target.new_page(width=300, height=300)
            image_page.insert_image(image_page.rect, stream=pixmap.tobytes("png"))
            target.set_metadata({})
            path = tmp_path / "scan.pdf"
            target.save(str(path), garbage=4, deflate=True, no_new_id=True)
        finally:
            target.close()

        document = normalize_document(path)

        assert document.text_layer.pages[0].source == "unavailable"
        assert document.text_layer.pages[0].has_text is False
        assert document.text_layer.has_text is False

    def test_images_expose_an_explicit_empty_text_layer(self, tmp_path: Path) -> None:
        path = tmp_path / "photo.png"
        Image.new("RGB", (48, 32), "white").save(path)

        document = normalize_document(path)

        assert len(document.text_layer.pages) == 1
        assert document.text_layer.pages[0].source == "unavailable"

    def test_extraction_survives_a_page_that_cannot_be_parsed(self, tmp_path: Path) -> None:
        class BrokenPage:
            rect = pymupdf.Rect(0, 0, 100, 100)
            rotation_matrix = pymupdf.Matrix(1, 0, 0, 1, 0, 0)

            def get_text(self, _kind: str) -> dict:
                raise RuntimeError("corrupt content stream")

        layer = extract_page_text_layer(BrokenPage(), 3)

        assert layer.page_number == 3
        assert layer.source == "unavailable"
        assert layer.tokens == ()
