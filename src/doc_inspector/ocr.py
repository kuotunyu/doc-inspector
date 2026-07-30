"""Optional local OCR used only to locate evidence on pages without a text layer.

This module is intentionally isolated: nothing in the base installation imports
Tesseract, and a missing binary or missing Python binding degrades the affected
pages to ``page_only`` instead of failing the review.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from doc_inspector.ingest import NormalizedPage, PageToken
from doc_inspector.schemas import BBOX_SCALE, NormalizedBBox

DEFAULT_OCR_LANGUAGES = "chi_tra+chi_sim+eng"
MIN_WORD_CONFIDENCE = 30.0


@dataclass(frozen=True, slots=True)
class TesseractEvidenceOcr:
    """Word-level OCR provider backed by the optional ``local-ocr`` extra."""

    languages: str = DEFAULT_OCR_LANGUAGES
    min_confidence: float = MIN_WORD_CONFIDENCE

    def page_tokens(self, page: NormalizedPage) -> tuple[PageToken, ...]:
        """Return positioned OCR words in the normalized bbox space."""

        if page.width <= 0 or page.height <= 0:
            return ()

        import pytesseract  # noqa: PLC0415 - optional dependency, imported lazily
        from PIL import Image  # noqa: PLC0415

        with Image.open(BytesIO(page.data)) as image:
            image.load()
            data = pytesseract.image_to_data(
                image,
                lang=self.languages,
                output_type=pytesseract.Output.DICT,
            )
        return tuple(_tokens_from_tesseract(data, page.width, page.height, self.min_confidence))


def _tokens_from_tesseract(
    data: dict[str, list[object]],
    width: int,
    height: int,
    min_confidence: float,
) -> list[PageToken]:
    tokens: list[PageToken] = []
    count = len(data.get("text", []))
    for index in range(count):
        text = str(data["text"][index]).strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][index])
            left = float(data["left"][index])
            top = float(data["top"][index])
            box_width = float(data["width"][index])
            box_height = float(data["height"][index])
        except (TypeError, ValueError):
            continue
        if confidence < min_confidence or box_width <= 0 or box_height <= 0:
            continue
        x0 = max(0.0, min(BBOX_SCALE, left / width * BBOX_SCALE))
        x1 = max(0.0, min(BBOX_SCALE, (left + box_width) / width * BBOX_SCALE))
        y0 = max(0.0, min(BBOX_SCALE, top / height * BBOX_SCALE))
        y1 = max(0.0, min(BBOX_SCALE, (top + box_height) / height * BBOX_SCALE))
        if x1 <= x0 or y1 <= y0:
            continue
        tokens.append(
            PageToken(
                text=text,
                bbox=NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1),
                confidence=confidence,
            )
        )
    return tokens


def load_evidence_ocr_provider(
    *,
    enabled: bool,
    languages: str = DEFAULT_OCR_LANGUAGES,
) -> TesseractEvidenceOcr | None:
    """Return a usable OCR provider, or ``None`` when the extra is absent."""

    if not enabled:
        return None
    try:
        import pytesseract  # noqa: PLC0415

        pytesseract.get_tesseract_version()
    except Exception:  # noqa: BLE001 - any failure means "no local OCR available"
        return None
    return TesseractEvidenceOcr(languages=languages)
