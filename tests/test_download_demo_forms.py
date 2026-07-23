from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from scripts_support import load_script_module

download_demo_forms = load_script_module("download_demo_forms")


def test_validate_pdf_reports_page_count(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    document = pymupdf.open()
    document.new_page()
    document.new_page()
    document.save(path)
    document.close()

    assert download_demo_forms.validate_pdf(path) == {"page_count": 2, "encrypted": False}


def test_validate_pdf_rejects_non_pdf(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"not a pdf")

    with pytest.raises(RuntimeError, match="不是 PDF"):
        download_demo_forms.validate_pdf(path)
