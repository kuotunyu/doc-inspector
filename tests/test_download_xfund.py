from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts_support import load_script_module

download_xfund = load_script_module("download_xfund")


def test_validate_json_checks_expected_document_count(tmp_path: Path) -> None:
    path = tmp_path / "sample.json"
    path.write_text(json.dumps({"documents": [{"id": 1}]}), encoding="utf-8")

    download_xfund._validate_json(path, 1)
    with pytest.raises(RuntimeError, match="文件數不符"):
        download_xfund._validate_json(path, 2)


def test_safe_extract_rejects_zip_slip(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with ZipFile(archive, "w") as output:
        output.writestr("../outside.jpg", b"image")

    with pytest.raises(RuntimeError, match="不安全路徑"):
        download_xfund._safe_extract(archive, tmp_path / "images")


def test_safe_extract_accepts_only_images(tmp_path: Path) -> None:
    archive = tmp_path / "safe.zip"
    with ZipFile(archive, "w") as output:
        output.writestr("nested/page.jpg", b"image")

    count = download_xfund._safe_extract(archive, tmp_path / "images")

    assert count == 1
    assert (tmp_path / "images" / "nested" / "page.jpg").read_bytes() == b"image"
