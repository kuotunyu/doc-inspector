"""Download and verify three official Taiwan government blank-form PDFs."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import quote
from urllib.request import Request, urlopen

import pymupdf

FORMS = (
    {
        "id": "rental_subsidy_115",
        "title": "115年中央擴大租金補貼申請書",
        "agency": "內政部國土管理署",
        "url": "https://pip.moi.gov.tw/Upload/HouSubsidy/File2/115Y_01_租金補貼申請書.pdf",
        "source_page": "https://pip.moi.gov.tw/Publicize/Info/B1020?n=E794B3E8AB8BE6A29DE4BBB6&y=115",
        "terms_status": "官方頁面提供下載；未找到明確再散布授權，僅供本機驗證，不納入版本控制。",
        "terms_url": None,
    },
    {
        "id": "childcare_allowance_under_2",
        "title": "育有未滿2歲兒童育兒津貼申請書",
        "agency": "連江縣北竿鄉公所",
        "url": "https://www.beigan.gov.tw/upload/pdf-20260107114330.pdf",
        "source_page": "https://www.beigan.gov.tw/Chhtml/download/2194",
        "terms_status": "網站頁尾標示 All rights reserved；僅供本機驗證，不再散布或納入版本控制。",
        "terms_url": "https://www.beigan.gov.tw/Chhtml/download/2194",
    },
    {
        "id": "assistive_device_subsidy_hualien",
        "title": "身心障礙者輔具費用補助申請表",
        "agency": "花蓮縣政府",
        "url": "https://ws.hl.gov.tw/Download.ashx?n=6Lqr5b%2BD6Zqc56SZ6ICF55Sf5rS76LyU5YW36LK755So6KOc5Yqp55Sz6KuL6KGoKOeZvSkucGRm&u=LzAwMS9VcGxvYWQvNDIwL3JlbGZpbGUvOTgxNy83NzExL2U0MGU5NjQ1LWM2YTAtNGMxZi1iOWE0LTkwNGRkMjNjMTE0OC5wZGY%3D",
        "source_page": "https://sa.hl.gov.tw/",
        "terms_status": "縣府有資料開放宣告，但社會處頁尾另要求授權；保守採僅本機驗證，不再散布。",
        "terms_url": "https://www.hl.gov.tw/en/cp.aspx?n=32892",
    },
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_pdf(path: Path) -> dict[str, int | bool]:
    if path.read_bytes()[:5] != b"%PDF-":
        raise RuntimeError(f"{path.name} 不是 PDF。")
    try:
        with pymupdf.open(path) as document:
            if not document.is_pdf or document.page_count < 1:
                raise RuntimeError(f"{path.name} 沒有有效 PDF 頁面。")
            if document.needs_pass:
                raise RuntimeError(f"{path.name} 是加密 PDF。")
            return {"page_count": document.page_count, "encrypted": False}
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
        raise RuntimeError(f"{path.name} PDF 損毀。") from exc


def download(url: str, destination: Path) -> str | None:
    encoded_url = quote(url, safe=":/?&=%")
    request = Request(encoded_url, headers={"User-Agent": "doc-inspector/0.1"})
    temporary = destination.with_suffix(".part")
    try:
        with urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            content_type = response.headers.get("Content-Type")
            shutil.copyfileobj(response, output, length=1024 * 1024)
        temporary.replace(destination)
        return content_type
    finally:
        temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="下載並驗證三份政府空白表單。")
    parser.add_argument("--output-dir", type=Path, default=Path("downloads/forms"))
    parser.add_argument("--manifest", type=Path, default=Path("data/demo/forms_manifest.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for form in FORMS:
        destination = output_dir / f"{form['id']}.pdf"
        content_type = download(str(form["url"]), destination)
        validation = validate_pdf(destination)
        records.append(
            {
                **form,
                "file_name": destination.name,
                "retrieved_at_utc": datetime.now(UTC).isoformat(),
                "content_type": content_type,
                "size_bytes": destination.stat().st_size,
                "sha256": sha256_file(destination),
                "validation": {"status": "verified", **validation},
            }
        )
        print(f"verified {destination.name}: {validation['page_count']} pages")

    manifest = {"forms": records}
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
