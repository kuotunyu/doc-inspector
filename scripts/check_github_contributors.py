"""Read-only verification of the public GitHub contributor identity.

The check uses GitHub's public REST endpoint without authentication. It does
not inspect local Git history, read dotenv secrets, or write to the repository.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPOSITORY = "kuotunyu/doc-inspector"
EXPECTED_LOGIN = "kuotunyu"
API_ROOT = f"https://api.github.com/repos/{REPOSITORY}/contributors"
API_VERSION = "2026-03-10"
PER_PAGE = 100
MAX_PAGES = 10


def _request_url(page: int) -> str:
    query = urlencode({"anon": "1", "per_page": PER_PAGE, "page": page})
    return f"{API_ROOT}?{query}"


def fetch_contributor_report(
    *,
    opener: Callable[..., Any] = urlopen,
    timeout_seconds: float = 20,
) -> dict[str, object]:
    """Fetch all contributor pages and return a privacy-minimized report."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds 必須大於 0。")

    entries: list[dict[str, object]] = []
    pages_checked = 0
    for page in range(1, MAX_PAGES + 1):
        request = Request(
            _request_url(page),
            headers={
                "Accept": "application/vnd.github+json",
                "Accept-Encoding": "identity",
                "User-Agent": "doc-inspector-contributor-check/1.0",
                "X-GitHub-Api-Version": API_VERSION,
            },
            method="GET",
        )
        with opener(request, timeout=timeout_seconds) as response:
            status = int(response.getcode())
            payload = response.read()
        if status != 200:
            raise RuntimeError(f"GitHub Contributors API 回傳 HTTP {status}。")

        decoded = json.loads(payload.decode("utf-8"))
        if not isinstance(decoded, list):
            raise ValueError("GitHub Contributors API 回應不是清單。")
        if any(not isinstance(item, dict) for item in decoded):
            raise ValueError("GitHub Contributors API 清單含有無效項目。")

        page_entries = list(decoded)
        entries.extend(page_entries)
        pages_checked = page
        if len(page_entries) < PER_PAGE:
            break
    else:
        raise RuntimeError("GitHub Contributors API 分頁超過安全上限。")

    logins = sorted(
        {
            login.strip()
            for item in entries
            if isinstance((login := item.get("login")), str) and login.strip()
        },
        key=str.casefold,
    )
    anonymous_count = sum(
        1
        for item in entries
        if not isinstance(item.get("login"), str) or not item["login"].strip()
    )
    sole_contributor = logins == [EXPECTED_LOGIN] and anonymous_count == 0

    return {
        "verified": True,
        "repository": REPOSITORY,
        "expected_login": EXPECTED_LOGIN,
        "logins": logins,
        "anonymous_contributor_count": anonymous_count,
        "contributor_entry_count": len(entries),
        "pages_checked": pages_checked,
        "sole_contributor": sole_contributor,
        "data_may_be_cached_for_hours": True,
        "uses_authentication": False,
        "reads_env_truth": False,
        "performs_writes": False,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        report = fetch_contributor_report()
    except (OSError, RuntimeError, ValueError, UnicodeDecodeError) as exc:
        report = {
            "verified": False,
            "repository": REPOSITORY,
            "expected_login": EXPECTED_LOGIN,
            "sole_contributor": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "data_may_be_cached_for_hours": True,
            "uses_authentication": False,
            "reads_env_truth": False,
            "performs_writes": False,
        }
        print(json.dumps(report, ensure_ascii=False))
        return 2

    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["sole_contributor"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
