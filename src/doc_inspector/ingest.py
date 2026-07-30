"""Document validation and privacy-preserving page normalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Literal
import warnings

import pymupdf
from PIL import Image, ImageOps, UnidentifiedImageError

from doc_inspector.errors import (
    DocumentDecodeError,
    DocumentInputError,
    EncryptedPdfError,
    FileSizeLimitError,
    PageLimitError,
    UnsupportedFileTypeError,
)
from doc_inspector.schemas import BBOX_SCALE, NormalizedBBox

SUPPORTED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
SUPPORTED_IMAGE_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})
SUPPORTED_SUFFIXES = SUPPORTED_IMAGE_SUFFIXES | {".pdf"}

TextLayerSource = Literal["native_pdf_text", "optional_local_ocr", "unavailable"]

_MIN_BBOX_EXTENT = 1e-6


@dataclass(frozen=True, slots=True)
class PageWord:
    """One positioned token of a page's local text layer."""

    text: str
    bbox: NormalizedBBox
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class PageTextLayer:
    """Positioned tokens for one page, or an explicit absence of them."""

    page_number: int
    source: TextLayerSource = "unavailable"
    words: tuple[PageWord, ...] = ()

    @property
    def has_text(self) -> bool:
        return bool(self.words)


@dataclass(frozen=True, slots=True)
class DocumentTextLayer:
    """Ordered per-page text layers used to verify provider evidence claims."""

    pages: tuple[PageTextLayer, ...] = ()

    @property
    def has_text(self) -> bool:
        return any(page.has_text for page in self.pages)

    def page(self, page_number: int) -> PageTextLayer | None:
        """Return the layer for a one-based page number, or ``None``."""

        for candidate in self.pages:
            if candidate.page_number == page_number:
                return candidate
        return None


@dataclass(frozen=True, slots=True)
class NormalizedPage:
    """One normalized PNG page ready for a multimodal request."""

    page_number: int
    data: bytes
    width: int
    height: int
    mime_type: str = "image/png"


@dataclass(frozen=True, slots=True)
class NormalizedDocument:
    """A document represented only by basename and in-memory normalized pages."""

    source_file_name: str
    pages: tuple[NormalizedPage, ...]
    text_layer: DocumentTextLayer = field(default_factory=DocumentTextLayer)


def normalized_bbox_from_rect(
    rect: pymupdf.Rect,
    page_rect: pymupdf.Rect,
) -> NormalizedBBox | None:
    """Map a display-space PDF rectangle into the normalized bbox space.

    ``page_rect`` is ``Page.rect``, which already accounts for the crop box and
    page rotation, so the result is independent of render DPI and of any later
    image downscaling. Rectangles that clip away to nothing return ``None``.
    """

    if page_rect.width <= 0 or page_rect.height <= 0:
        return None

    def _scale(value: float, origin: float, extent: float) -> float:
        return min(BBOX_SCALE, max(0.0, (value - origin) / extent * BBOX_SCALE))

    x0 = _scale(min(rect.x0, rect.x1), page_rect.x0, page_rect.width)
    x1 = _scale(max(rect.x0, rect.x1), page_rect.x0, page_rect.width)
    y0 = _scale(min(rect.y0, rect.y1), page_rect.y0, page_rect.height)
    y1 = _scale(max(rect.y0, rect.y1), page_rect.y0, page_rect.height)
    if x1 - x0 < _MIN_BBOX_EXTENT or y1 - y0 < _MIN_BBOX_EXTENT:
        return None
    return NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1)


def extract_page_text_layer(page: pymupdf.Page, page_number: int) -> PageTextLayer:
    """Read one PDF page's native words without rasterizing or storing the page."""

    page_rect = page.rect
    rotation_matrix = page.rotation_matrix
    words: list[PageWord] = []
    try:
        raw_words = page.get_text("words", sort=True)
    except (RuntimeError, ValueError):
        return PageTextLayer(page_number=page_number)

    for raw in raw_words:
        text = str(raw[4])
        if not text.strip():
            continue
        rotated = pymupdf.Rect(raw[0], raw[1], raw[2], raw[3]) * rotation_matrix
        bbox = normalized_bbox_from_rect(rotated, page_rect)
        if bbox is None:
            continue
        words.append(PageWord(text=text, bbox=bbox))

    if not words:
        return PageTextLayer(page_number=page_number)
    return PageTextLayer(
        page_number=page_number,
        source="native_pdf_text",
        words=tuple(words),
    )


def _validate_path(path: Path, max_file_bytes: int) -> Path:
    if max_file_bytes <= 0:
        raise ValueError("max_file_bytes 必須大於 0。")

    candidate = Path(path)
    if not candidate.exists():
        raise DocumentInputError("找不到指定文件。")
    if not candidate.is_file():
        raise DocumentInputError("指定路徑不是檔案。")
    if candidate.suffix.lower() not in SUPPORTED_SUFFIXES:
        allowed = "、".join(sorted(SUPPORTED_SUFFIXES))
        raise UnsupportedFileTypeError(f"不支援此檔案類型；允許：{allowed}。")

    try:
        file_size = candidate.stat().st_size
    except OSError as exc:
        raise DocumentInputError("無法讀取文件資訊。") from exc
    if file_size == 0:
        raise DocumentDecodeError("文件是空檔案。")
    if file_size > max_file_bytes:
        limit_mb = max_file_bytes / (1024 * 1024)
        raise FileSizeLimitError(f"文件超過 {limit_mb:g} MB 上限。")
    return candidate


def _encode_normalized_image(image: Image.Image, max_long_edge: int) -> tuple[bytes, int, int]:
    if max_long_edge <= 0:
        raise ValueError("max_long_edge 必須大於 0。")

    transposed = ImageOps.exif_transpose(image)
    if transposed.mode in {"RGBA", "LA"} or "transparency" in transposed.info:
        rgba = transposed.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        background.alpha_composite(rgba)
        normalized = background.convert("RGB")
    else:
        normalized = transposed.convert("RGB")

    if max(normalized.size) > max_long_edge:
        normalized.thumbnail((max_long_edge, max_long_edge), Image.Resampling.LANCZOS)

    output = BytesIO()
    normalized.save(output, format="PNG", optimize=True)
    width, height = normalized.size
    return output.getvalue(), width, height


def _normalize_image(path: Path, max_long_edge: int) -> NormalizedDocument:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                detected_format = image.format
                image.load()
                if detected_format not in SUPPORTED_IMAGE_FORMATS:
                    raise UnsupportedFileTypeError("解碼後的圖片格式不受支援。")
                data, width, height = _encode_normalized_image(image, max_long_edge)
    except UnsupportedFileTypeError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise DocumentDecodeError("圖片損毀、過大或無法解碼。") from exc
    except Image.DecompressionBombWarning as exc:
        raise DocumentDecodeError("圖片像素數異常，已拒絕處理。") from exc

    return NormalizedDocument(
        source_file_name=path.name,
        pages=(NormalizedPage(page_number=1, data=data, width=width, height=height),),
        text_layer=DocumentTextLayer(pages=(PageTextLayer(page_number=1),)),
    )


def _normalize_pdf(
    path: Path,
    *,
    max_pdf_pages: int,
    render_dpi: int,
    max_long_edge: int,
) -> NormalizedDocument:
    if max_pdf_pages <= 0:
        raise ValueError("max_pdf_pages 必須大於 0。")
    if render_dpi <= 0:
        raise ValueError("render_dpi 必須大於 0。")

    try:
        with pymupdf.open(path) as document:
            if not document.is_pdf:
                raise DocumentDecodeError("副檔名為 PDF，但內容不是 PDF。")
            if document.needs_pass:
                raise EncryptedPdfError("PDF 受到密碼保護，核心版不處理加密文件。")
            if document.page_count < 1:
                raise DocumentDecodeError("PDF 沒有可處理的頁面。")
            if document.page_count > max_pdf_pages:
                raise PageLimitError(f"PDF 超過 {max_pdf_pages} 頁上限。")

            pages: list[NormalizedPage] = []
            text_layers: list[PageTextLayer] = []
            for index, page in enumerate(document):
                page_number = index + 1
                pixmap = page.get_pixmap(dpi=render_dpi, alpha=False)
                png_bytes = pixmap.tobytes("png")
                with Image.open(BytesIO(png_bytes)) as image:
                    image.load()
                    data, width, height = _encode_normalized_image(image, max_long_edge)
                pages.append(
                    NormalizedPage(
                        page_number=page_number,
                        data=data,
                        width=width,
                        height=height,
                    )
                )
                text_layers.append(extract_page_text_layer(page, page_number))
    except (EncryptedPdfError, PageLimitError, DocumentDecodeError):
        raise
    except (pymupdf.EmptyFileError, pymupdf.FileDataError, RuntimeError, ValueError, OSError) as exc:
        raise DocumentDecodeError("PDF 損毀或無法解碼。") from exc

    return NormalizedDocument(
        source_file_name=path.name,
        pages=tuple(pages),
        text_layer=DocumentTextLayer(pages=tuple(text_layers)),
    )


def normalize_document(
    path: Path,
    *,
    max_file_bytes: int = 25 * 1024 * 1024,
    max_pdf_pages: int = 10,
    render_dpi: int = 200,
    max_long_edge: int = 2400,
) -> NormalizedDocument:
    """Validate a local document and return ordered in-memory PNG pages."""

    candidate = _validate_path(path, max_file_bytes)
    if candidate.suffix.lower() == ".pdf":
        return _normalize_pdf(
            candidate,
            max_pdf_pages=max_pdf_pages,
            render_dpi=render_dpi,
            max_long_edge=max_long_edge,
        )
    return _normalize_image(candidate, max_long_edge)
