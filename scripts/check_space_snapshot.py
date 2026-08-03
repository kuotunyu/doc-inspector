"""Compare runtime-critical files between an exact GitHub SHA and the Space."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from hashlib import sha256
import json
import re
import sys
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


GITHUB_REPOSITORY = "kuotunyu/doc-inspector"
SPACE_REPOSITORY = "steven0226/doc-inspector"
SPACE_REVISION = "main"
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
MAX_FILE_BYTES = 5 * 1024 * 1024
CRITICAL_FILES = (
    "README.md",
    "Dockerfile",
    "pyproject.toml",
    "uv.lock",
    "app.py",
    "src/doc_inspector/__init__.py",
    "src/doc_inspector/config.py",
    "src/doc_inspector/demo.py",
    "src/doc_inspector/errors.py",
    "src/doc_inspector/exporters.py",
    "src/doc_inspector/ingest.py",
    "src/doc_inspector/ocr.py",
    "src/doc_inspector/providers.py",
    "src/doc_inspector/provenance.py",
    "src/doc_inspector/rate_limit.py",
    "src/doc_inspector/rules.py",
    "src/doc_inspector/schemas.py",
    "src/doc_inspector/service.py",
    "src/doc_inspector/types.py",
    "src/doc_inspector/ui.py",
)


def normalize_sha(value: str) -> str:
    candidate = value.strip()
    if not SHA_PATTERN.fullmatch(candidate):
        raise ValueError("GitHub SHA 必須是完整的 40 位十六進位 commit SHA。")
    return candidate.lower()


def _read_url(
    url: str,
    *,
    opener: Callable[..., Any],
    timeout_seconds: float,
) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "Accept-Encoding": "identity",
            "User-Agent": "doc-inspector-space-snapshot-check/1.0",
        },
        method="GET",
    )
    with opener(request, timeout=timeout_seconds) as response:
        status_code = int(response.getcode())
        payload = response.read(MAX_FILE_BYTES + 1)
    if status_code != 200:
        raise RuntimeError(f"遠端檔案回傳 HTTP {status_code}。")
    if len(payload) > MAX_FILE_BYTES:
        raise RuntimeError("遠端關鍵檔案超過安全讀取上限。")
    return payload


def compare_critical_source(
    github_sha: str,
    *,
    opener: Callable[..., Any] = urlopen,
    timeout_seconds: float = 20,
) -> dict[str, object]:
    """Compare fixed runtime-critical files without downloading user data."""

    revision = normalize_sha(github_sha)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds 必須大於 0。")

    matched_files: list[str] = []
    mismatched_files: list[str] = []
    line_ending_only_mismatches: list[str] = []
    content_mismatches: list[str] = []
    for path in CRITICAL_FILES:
        encoded_path = quote(path, safe="/")
        github_url = (
            f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/"
            f"{revision}/{encoded_path}"
        )
        space_url = (
            f"https://huggingface.co/spaces/{SPACE_REPOSITORY}/resolve/"
            f"{SPACE_REVISION}/{encoded_path}"
        )
        github_payload = _read_url(
            github_url,
            opener=opener,
            timeout_seconds=timeout_seconds,
        )
        space_payload = _read_url(
            space_url,
            opener=opener,
            timeout_seconds=timeout_seconds,
        )
        if sha256(github_payload).digest() == sha256(space_payload).digest():
            matched_files.append(path)
        else:
            mismatched_files.append(path)
            if github_payload.replace(b"\r\n", b"\n") == space_payload.replace(
                b"\r\n",
                b"\n",
            ):
                line_ending_only_mismatches.append(path)
            else:
                content_mismatches.append(path)

    return {
        "verified": True,
        "github_repository": GITHUB_REPOSITORY,
        "github_sha": revision,
        "space_repository": SPACE_REPOSITORY,
        "space_revision": SPACE_REVISION,
        "comparison_scope": "runtime-critical files only",
        "critical_file_count": len(CRITICAL_FILES),
        "matched_file_count": len(matched_files),
        "mismatched_files": mismatched_files,
        "line_ending_only_mismatches": line_ending_only_mismatches,
        "content_mismatches": content_mismatches,
        "critical_source_match": not mismatched_files,
        "uses_authentication": False,
        "reads_env_truth": False,
        "uploads_documents": False,
        "calls_model": False,
        "performs_writes": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "比對指定 GitHub commit 與公開 Space 的 runtime 關鍵檔；"
            "不會上傳文件或寫入遠端。"
        ),
    )
    parser.add_argument(
        "--github-sha",
        required=True,
        help="已通過 GitHub CI 的完整 40 位 commit SHA",
    )
    parser.add_argument("--timeout-seconds", type=float, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        report = compare_critical_source(
            args.github_sha,
            timeout_seconds=args.timeout_seconds,
        )
    except (OSError, RuntimeError, ValueError, UnicodeDecodeError) as exc:
        report = {
            "verified": False,
            "github_repository": GITHUB_REPOSITORY,
            "space_repository": SPACE_REPOSITORY,
            "critical_source_match": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "uses_authentication": False,
            "reads_env_truth": False,
            "uploads_documents": False,
            "calls_model": False,
            "performs_writes": False,
        }
        print(json.dumps(report, ensure_ascii=False))
        return 2

    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["critical_source_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
