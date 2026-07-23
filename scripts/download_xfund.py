"""Download and verify the official XFUND v1.0 Chinese assets without Git."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

RELEASE_URL = "https://github.com/doc-analysis/XFUND/releases/tag/v1.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
ASSETS = {
    "zh.train.json": 4_674_754,
    "zh.val.json": 1_711_142,
    "zh.train.zip": 206_389_536,
    "zh.val.zip": 69_217_820,
}
ASSET_BASE_URL = "https://github.com/doc-analysis/XFUND/releases/download/v1.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "doc-inspector/0.1"})
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            shutil.copyfileobj(response, output, length=1024 * 1024)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _safe_extract(archive_path: Path, output_dir: Path) -> int:
    output_root = output_dir.resolve()
    extracted = 0
    try:
        with ZipFile(archive_path) as archive:
            for member in archive.infolist():
                target = (output_dir / member.filename).resolve()
                if output_root not in target.parents and target != output_root:
                    raise RuntimeError(f"ZIP 含不安全路徑：{member.filename!r}")
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if target.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                    raise RuntimeError(f"ZIP 含非預期檔案：{member.filename!r}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                extracted += 1
    except BadZipFile as exc:
        raise RuntimeError(f"ZIP 損毀：{archive_path.name}") from exc
    return extracted


def _validate_json(path: Path, expected_documents: int) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = payload.get("documents")
    if not isinstance(documents, list) or len(documents) != expected_documents:
        raise RuntimeError(
            f"{path.name} 文件數不符：預期 {expected_documents}，實際 "
            f"{len(documents) if isinstance(documents, list) else 'invalid'}。"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="下載並驗證 XFUND v1.0 中文資料。")
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/xfund"))
    parser.add_argument("--manifest", type=Path, default=Path("data/raw/xfund/manifest.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for name, expected_size in ASSETS.items():
        destination = output_dir / name
        url = f"{ASSET_BASE_URL}/{name}"
        if not destination.exists() or destination.stat().st_size != expected_size:
            print(f"下載 {name}（{expected_size / 1024 / 1024:.1f} MiB）…")
            _download(url, destination)
        actual_size = destination.stat().st_size
        if actual_size != expected_size:
            raise SystemExit(f"{name} 大小不符：預期 {expected_size}，實際 {actual_size}。")
        records.append(
            {
                "name": name,
                "url": url,
                "size_bytes": actual_size,
                "sha256": sha256_file(destination),
            }
        )

    _validate_json(output_dir / "zh.train.json", 149)
    _validate_json(output_dir / "zh.val.json", 50)
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)
    extracted = {
        name: _safe_extract(output_dir / name, images_dir)
        for name in ("zh.train.zip", "zh.val.zip")
    }

    manifest = {
        "dataset": "XFUND",
        "version": "v1.0",
        "language": "zh",
        "release_url": RELEASE_URL,
        "license": "CC BY-NC-SA 4.0",
        "license_url": LICENSE_URL,
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "assets": records,
        "document_counts": {"train": 149, "val": 50},
        "extracted_image_counts": extracted,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"verified": True, "images": extracted}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
