"""Read-only verification that CI passed for an exact public GitHub commit."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
import re
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPOSITORY = "kuotunyu/doc-inspector"
WORKFLOW_FILE = "ci.yml"
BRANCH = "main"
API_VERSION = "2026-03-10"
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


def normalize_sha(value: str) -> str:
    candidate = value.strip()
    if not SHA_PATTERN.fullmatch(candidate):
        raise ValueError("expected SHA 必須是完整的 40 位十六進位 Git commit SHA。")
    return candidate.lower()


def fetch_ci_report(
    expected_sha: str,
    *,
    opener: Callable[..., Any] = urlopen,
    timeout_seconds: float = 20,
) -> dict[str, object]:
    """Return whether the push workflow succeeded for exactly expected_sha."""

    sha = normalize_sha(expected_sha)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds 必須大於 0。")

    query = urlencode(
        {
            "branch": BRANCH,
            "event": "push",
            "head_sha": sha,
            "per_page": 1,
        }
    )
    request = Request(
        (
            f"https://api.github.com/repos/{REPOSITORY}/actions/workflows/"
            f"{WORKFLOW_FILE}/runs?{query}"
        ),
        headers={
            "Accept": "application/vnd.github+json",
            "Accept-Encoding": "identity",
            "User-Agent": "doc-inspector-ci-check/1.0",
            "X-GitHub-Api-Version": API_VERSION,
        },
        method="GET",
    )
    with opener(request, timeout=timeout_seconds) as response:
        status_code = int(response.getcode())
        payload = response.read()
    if status_code != 200:
        raise RuntimeError(f"GitHub Actions API 回傳 HTTP {status_code}。")

    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("GitHub Actions API 回應不是物件。")
    runs = decoded.get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError("GitHub Actions API 回應缺少 workflow_runs 清單。")
    if any(not isinstance(run, dict) for run in runs):
        raise ValueError("GitHub Actions API 的 workflow_runs 含有無效項目。")

    run = runs[0] if runs else None
    returned_sha = run.get("head_sha") if run else None
    sha_matches = (
        isinstance(returned_sha, str) and returned_sha.casefold() == sha.casefold()
    )
    run_status = run.get("status") if run else None
    conclusion = run.get("conclusion") if run else None
    ci_passed = (
        sha_matches and run_status == "completed" and conclusion == "success"
    )

    return {
        "verified": True,
        "repository": REPOSITORY,
        "workflow_file": WORKFLOW_FILE,
        "branch": BRANCH,
        "expected_sha": sha,
        "run_found": run is not None,
        "sha_matches": sha_matches,
        "status": run_status,
        "conclusion": conclusion,
        "run_number": run.get("run_number") if run else None,
        "run_url": run.get("html_url") if run else None,
        "ci_passed": ci_passed,
        "uses_authentication": False,
        "reads_env_truth": False,
        "performs_writes": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="確認指定 GitHub commit 的 push CI 已完成且成功；不會寫入遠端。",
    )
    parser.add_argument(
        "--expected-sha",
        required=True,
        help="由維護者在推送後以 git rev-parse HEAD 取得的完整 commit SHA",
    )
    parser.add_argument("--timeout-seconds", type=float, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        report = fetch_ci_report(
            args.expected_sha,
            timeout_seconds=args.timeout_seconds,
        )
    except (OSError, RuntimeError, ValueError, UnicodeDecodeError) as exc:
        report = {
            "verified": False,
            "repository": REPOSITORY,
            "workflow_file": WORKFLOW_FILE,
            "ci_passed": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "uses_authentication": False,
            "reads_env_truth": False,
            "performs_writes": False,
        }
        print(json.dumps(report, ensure_ascii=False))
        return 2

    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ci_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
