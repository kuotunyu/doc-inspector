"""Document validation and privacy-preserving page normalization."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
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

SUPPORTED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
SUPPORTED_IMAGE_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})
SUPPORTED_SUFFIXES = SUPPORTED_IMAGE_SUFFIXES | {".pdf"}


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
            for index, page in enumerate(document):
                pixmap = page.get_pixmap(dpi=render_dpi, alpha=False)
                png_bytes = pixmap.tobytes("png")
                with Image.open(BytesIO(png_bytes)) as image:
                    image.load()
                    data, width, height = _encode_normalized_image(image, max_long_edge)
                pages.append(
                    NormalizedPage(
                        page_number=index + 1,
                        data=data,
                        width=width,
                        height=height,
                    )
                )
    except (EncryptedPdfError, PageLimitError, DocumentDecodeError):
        raise
    except (pymupdf.EmptyFileError, pymupdf.FileDataError, RuntimeError, ValueError, OSError) as exc:
        raise DocumentDecodeError("PDF 損毀或無法解碼。") from exc

    return NormalizedDocument(source_file_name=path.name, pages=tuple(pages))


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
