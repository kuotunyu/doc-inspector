"""Optional local OCR: coordinate conversion and safe absence of the extra."""

from __future__ import annotations

from io import BytesIO
import sys
from types import SimpleNamespace

from PIL import Image
import pytest

from doc_inspector.ingest import NormalizedPage
from doc_inspector.ocr import (
    DEFAULT_OCR_LANGUAGES,
    TesseractEvidenceOcr,
    _tokens_from_tesseract,
    load_evidence_ocr_provider,
)


def tesseract_payload() -> dict[str, list[object]]:
    return {
        "text": ["應付總額", "452", "", "  ", "雜訊"],
        "conf": [96.0, 91.5, 0.0, -1, 12.0],
        "left": [50, 200, 0, 0, 10],
        "top": [100, 100, 0, 0, 300],
        "width": [120, 60, 0, 0, 40],
        "height": [40, 40, 0, 0, 30],
    }


def page_image(width: int = 400, height: int = 800) -> NormalizedPage:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return NormalizedPage(
        page_number=1,
        data=buffer.getvalue(),
        width=width,
        height=height,
    )


class TestTokenConversion:
    def test_pixel_boxes_become_normalized_coordinates(self) -> None:
        tokens = _tokens_from_tesseract(tesseract_payload(), 400, 800, 30.0)

        assert [token.text for token in tokens] == ["應付總額", "452"]
        first = tokens[0]
        assert first.bbox.x0 == pytest.approx(125.0)
        assert first.bbox.x1 == pytest.approx(425.0)
        assert first.bbox.y0 == pytest.approx(125.0)
        assert first.bbox.y1 == pytest.approx(175.0)
        assert first.confidence == pytest.approx(96.0)

    def test_low_confidence_blank_and_degenerate_boxes_are_dropped(self) -> None:
        tokens = _tokens_from_tesseract(tesseract_payload(), 400, 800, 95.0)

        assert [token.text for token in tokens] == ["應付總額"]

    def test_malformed_rows_are_skipped_without_raising(self) -> None:
        payload = tesseract_payload()
        payload["conf"] = ["not-a-number", 91.5, 0.0, -1, 12.0]

        tokens = _tokens_from_tesseract(payload, 400, 800, 30.0)

        assert [token.text for token in tokens] == ["452"]

    def test_coordinates_are_clamped_to_the_page(self) -> None:
        payload = {
            "text": ["邊界"],
            "conf": [90.0],
            "left": [-40],
            "top": [-20],
            "width": [10_000],
            "height": [10_000],
        }

        tokens = _tokens_from_tesseract(payload, 400, 800, 30.0)

        assert tokens[0].bbox.x0 == 0.0
        assert tokens[0].bbox.y0 == 0.0
        assert tokens[0].bbox.x1 == 1000.0
        assert tokens[0].bbox.y1 == 1000.0


class TestProviderLoading:
    def test_disabled_configuration_never_imports_the_extra(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setitem(sys.modules, "pytesseract", None)

        assert load_evidence_ocr_provider(enabled=False) is None

    def test_a_missing_extra_degrades_to_no_provider(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setitem(sys.modules, "pytesseract", None)

        assert load_evidence_ocr_provider(enabled=True) is None

    def test_a_missing_binary_degrades_to_no_provider(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def missing_binary() -> str:
            raise RuntimeError("tesseract is not installed")

        monkeypatch.setitem(
            sys.modules,
            "pytesseract",
            SimpleNamespace(get_tesseract_version=missing_binary),
        )

        assert load_evidence_ocr_provider(enabled=True) is None

    def test_an_available_extra_produces_a_configured_provider(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setitem(
            sys.modules,
            "pytesseract",
            SimpleNamespace(get_tesseract_version=lambda: "5.4.0"),
        )

        provider = load_evidence_ocr_provider(enabled=True, languages="chi_tra")

        assert isinstance(provider, TesseractEvidenceOcr)
        assert provider.languages == "chi_tra"
        assert TesseractEvidenceOcr().languages == DEFAULT_OCR_LANGUAGES


class TestPageTokens:
    def test_page_tokens_pass_the_configured_language_to_the_extra(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        seen: dict[str, object] = {}

        def image_to_data(image, lang, output_type):
            seen["lang"] = lang
            seen["size"] = image.size
            seen["output_type"] = output_type
            return tesseract_payload()

        monkeypatch.setitem(
            sys.modules,
            "pytesseract",
            SimpleNamespace(
                image_to_data=image_to_data,
                Output=SimpleNamespace(DICT="dict"),
            ),
        )

        tokens = TesseractEvidenceOcr(languages="chi_tra").page_tokens(page_image())

        assert seen["lang"] == "chi_tra"
        assert seen["size"] == (400, 800)
        assert seen["output_type"] == "dict"
        assert [token.text for token in tokens] == ["應付總額", "452"]

    def test_a_degenerate_page_is_skipped_before_touching_the_extra(self) -> None:
        empty = NormalizedPage(page_number=1, data=b"", width=0, height=0)

        assert TesseractEvidenceOcr().page_tokens(empty) == ()
