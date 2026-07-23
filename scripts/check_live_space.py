"""Read-only health check for the published web interface.

This script never uploads a document, calls a model endpoint, or reads dotenv
secrets. It only verifies that the public HTML shell is reachable.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
from time import perf_counter, sleep
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


DEFAULT_EXPECTED_TEXT = "文件預檢所"
LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def validate_target_url(url: str, *, allow_http_localhost: bool = False) -> str:
    """Validate and normalize a secret-free health-check target."""

    candidate = url.strip()
    parsed = urlsplit(candidate)
    if parsed.username or parsed.password:
        raise ValueError("健康檢查網址不可包含帳號或密碼。")
    if parsed.query or parsed.fragment:
        raise ValueError("健康檢查網址不可包含 query 或 fragment。")
    if not parsed.hostname:
        raise ValueError("健康檢查網址缺少主機名稱。")

    is_local_http = (
        parsed.scheme == "http"
        and allow_http_localhost
        and parsed.hostname.lower() in LOCAL_HOSTS
    )
    if parsed.scheme != "https" and not is_local_http:
        raise ValueError("遠端健康檢查只接受 HTTPS；HTTP 僅限明確允許的 localhost。")

    path = parsed.path or "/"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def check_once(
    url: str,
    *,
    expected_text: str = DEFAULT_EXPECTED_TEXT,
    timeout_seconds: float = 20,
    max_response_bytes: int = 2 * 1024 * 1024,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, object]:
    """Fetch one HTML shell and return non-sensitive health metadata."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds 必須大於 0。")
    if max_response_bytes <= 0:
        raise ValueError("max_response_bytes 必須大於 0。")
    if not expected_text:
        raise ValueError("expected_text 不可為空。")

    request = Request(
        url,
        headers={
            "Accept": "text/html",
            "Accept-Encoding": "identity",
            "User-Agent": "doc-inspector-release-check/1.0",
        },
        method="GET",
    )
    started = perf_counter()
    with opener(request, timeout=timeout_seconds) as response:
        status = int(response.getcode())
        content_type = response.headers.get_content_type()
        charset = response.headers.get_content_charset() or "utf-8"
        payload = response.read(max_response_bytes + 1)
        final_url = response.geturl()
    elapsed_ms = max(0, round((perf_counter() - started) * 1000))

    if status != 200:
        raise RuntimeError(f"介面回傳 HTTP {status}。")
    if content_type != "text/html":
        raise RuntimeError(f"介面回傳的 Content-Type 不是 text/html：{content_type}。")
    if len(payload) > max_response_bytes:
        raise RuntimeError("介面 HTML 超過健康檢查讀取上限。")
    try:
        html = payload.decode(charset)
    except (LookupError, UnicodeDecodeError) as exc:
        raise RuntimeError("介面 HTML 無法依宣告編碼解碼。") from exc
    if expected_text not in html:
        raise RuntimeError("介面可連線，但找不到預期的應用程式標題。")

    return {
        "healthy": True,
        "http_status": status,
        "content_type": content_type,
        "expected_text_found": True,
        "response_bytes": len(payload),
        "elapsed_ms": elapsed_ms,
        "final_url": final_url,
        "uploads_document": False,
        "calls_model": False,
        "reads_env_truth": False,
    }


def run_health_check(
    url: str,
    *,
    expected_text: str = DEFAULT_EXPECTED_TEXT,
    retries: int = 6,
    delay_seconds: float = 10,
    timeout_seconds: float = 20,
    allow_http_localhost: bool = False,
    opener: Callable[..., Any] = urlopen,
    sleep_fn: Callable[[float], None] = sleep,
) -> dict[str, object]:
    """Retry a sleeping deployment and return a stable JSON-ready report."""

    if retries < 1:
        raise ValueError("retries 必須至少為 1。")
    if delay_seconds < 0:
        raise ValueError("delay_seconds 不可小於 0。")

    target = validate_target_url(
        url,
        allow_http_localhost=allow_http_localhost,
    )
    failures: list[dict[str, object]] = []
    for attempt in range(1, retries + 1):
        try:
            result = check_once(
                target,
                expected_text=expected_text,
                timeout_seconds=timeout_seconds,
                opener=opener,
            )
            return {
                **result,
                "target_url": target,
                "attempts": attempt,
                "previous_failures": failures,
            }
        except Exception as exc:  # Network libraries expose several exception types.
            failures.append(
                {
                    "attempt": attempt,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            if attempt < retries:
                sleep_fn(delay_seconds)

    return {
        "healthy": False,
        "target_url": target,
        "attempts": retries,
        "failures": failures,
        "uploads_document": False,
        "calls_model": False,
        "reads_env_truth": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="檢查公開介面 HTML 是否可用；不會上傳文件或呼叫模型。",
    )
    parser.add_argument("--url", required=True, help="公開 HTTPS URL")
    parser.add_argument(
        "--expected-text",
        default=DEFAULT_EXPECTED_TEXT,
        help="HTML 中必須出現的文字",
    )
    parser.add_argument("--retries", type=int, default=6)
    parser.add_argument("--delay-seconds", type=float, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=20)
    parser.add_argument(
        "--allow-http-localhost",
        action="store_true",
        help="只供本機容器預檢使用",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_health_check(
            args.url,
            expected_text=args.expected_text,
            retries=args.retries,
            delay_seconds=args.delay_seconds,
            timeout_seconds=args.timeout_seconds,
            allow_http_localhost=args.allow_http_localhost,
        )
    except ValueError as exc:
        report = {
            "healthy": False,
            "configuration_error": str(exc),
            "uploads_document": False,
            "calls_model": False,
            "reads_env_truth": False,
        }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
