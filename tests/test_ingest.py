from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from doc_inspector.errors import (
    DocumentDecodeError,
    EncryptedPdfError,
    FileSizeLimitError,
    PageLimitError,
    UnsupportedFileTypeError,
)
from doc_inspector.ingest import normalize_document


def save_test_image(path: Path, *, size: tuple[int, int] = (64, 32)) -> None:
    Image.new("RGB", size, "white").save(path)


def save_pdf(path: Path, page_count: int) -> None:
    document = pymupdf.open()
    for index in range(page_count):
        page = document.new_page(width=200, height=100)
        page.insert_text((20, 50), f"page {index + 1}")
    document.save(path)
    document.close()


def test_image_applies_exif_orientation_and_outputs_png(tmp_path: Path) -> None:
    path = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (20, 10), "white").save(path, exif=exif)

    document = normalize_document(path)

    page = document.pages[0]
    assert (page.width, page.height) == (10, 20)
    assert page.data.startswith(b"\x89PNG")
    assert page.page_number == 1


def test_image_long_edge_is_limited_without_upscaling(tmp_path: Path) -> None:
    path = tmp_path / "large.png"
    save_test_image(path, size=(300, 150))

    document = normalize_document(path, max_long_edge=100)

    assert (document.pages[0].width, document.pages[0].height) == (100, 50)


def test_multipage_pdf_preserves_page_order(tmp_path: Path) -> None:
    path = tmp_path / "two-pages.pdf"
    save_pdf(path, 2)

    document = normalize_document(path, render_dpi=72, max_long_edge=500)

    assert [page.page_number for page in document.pages] == [1, 2]
    assert all(page.data.startswith(b"\x89PNG") for page in document.pages)


def test_pdf_page_limit_is_enforced_before_rendering(tmp_path: Path) -> None:
    path = tmp_path / "three-pages.pdf"
    save_pdf(path, 3)

    with pytest.raises(PageLimitError, match="2"):
        normalize_document(path, max_pdf_pages=2)


def test_encrypted_pdf_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "encrypted.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(
        path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner-password",
        user_pw="user-password",
    )
    document.close()

    with pytest.raises(EncryptedPdfError):
        normalize_document(path)


@pytest.mark.parametrize("suffix", [".png", ".pdf"])
def test_corrupt_supported_files_are_rejected(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"corrupt{suffix}"
    path.write_bytes(b"not a valid document")

    with pytest.raises(DocumentDecodeError):
        normalize_document(path)


def test_file_size_limit_is_enforced(tmp_path: Path) -> None:
    path = tmp_path / "image.png"
    save_test_image(path)

    with pytest.raises(FileSizeLimitError):
        normalize_document(path, max_file_bytes=1)


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "document.txt"
    path.write_text("text", encoding="utf-8")

    with pytest.raises(UnsupportedFileTypeError):
        normalize_document(path)


def test_decoded_image_format_must_be_supported(tmp_path: Path) -> None:
    path = tmp_path / "renamed.png"
    image = Image.new("RGB", (10, 10), "white")
    data = BytesIO()
    image.save(data, format="BMP")
    path.write_bytes(data.getvalue())

    with pytest.raises(UnsupportedFileTypeError):
        normalize_document(path)
