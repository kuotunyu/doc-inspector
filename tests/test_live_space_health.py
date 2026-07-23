from __future__ import annotations

from email.message import Message
from io import BytesIO

import pytest

from scripts_support import load_script_module

check_live_space = load_script_module("check_live_space")


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
        url: str = "https://example.test/",
    ) -> None:
        self._body = BytesIO(body)
        self._status = status
        self._url = url
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def getcode(self) -> int:
        return self._status

    def geturl(self) -> str:
        return self._url

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)


def test_target_requires_https_without_credentials_or_query() -> None:
    assert (
        check_live_space.validate_target_url("https://example.test")
        == "https://example.test/"
    )

    with pytest.raises(ValueError, match="HTTPS"):
        check_live_space.validate_target_url("http://example.test")
    with pytest.raises(ValueError, match="帳號或密碼"):
        check_live_space.validate_target_url("https://user:secret@example.test/")
    with pytest.raises(ValueError, match="query"):
        check_live_space.validate_target_url("https://example.test/?token=secret")


def test_local_http_requires_explicit_flag() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        check_live_space.validate_target_url("http://127.0.0.1:7863/")

    assert (
        check_live_space.validate_target_url(
            "http://127.0.0.1:7863/",
            allow_http_localhost=True,
        )
        == "http://127.0.0.1:7863/"
    )


def test_health_check_accepts_expected_html_without_model_call() -> None:
    def opener(*_: object, **__: object) -> FakeResponse:
        return FakeResponse("<title>文件預檢所</title>".encode())

    report = check_live_space.run_health_check(
        "https://example.test",
        retries=1,
        opener=opener,
    )

    assert report["healthy"] is True
    assert report["attempts"] == 1
    assert report["http_status"] == 200
    assert report["uploads_document"] is False
    assert report["calls_model"] is False
    assert report["reads_env_truth"] is False


def test_health_check_retries_transient_failure() -> None:
    attempts = 0
    delays: list[float] = []

    def opener(*_: object, **__: object) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("temporary")
        return FakeResponse("<h1>文件預檢所</h1>".encode())

    report = check_live_space.run_health_check(
        "https://example.test/",
        retries=2,
        delay_seconds=3,
        opener=opener,
        sleep_fn=delays.append,
    )

    assert report["healthy"] is True
    assert report["attempts"] == 2
    assert report["previous_failures"][0]["error_type"] == "OSError"
    assert delays == [3]


@pytest.mark.parametrize(
    ("body", "content_type", "message"),
    [
        (b"<title>other</title>", "text/html", "應用程式標題"),
        ("文件預檢所".encode(), "application/json", "Content-Type"),
    ],
)
def test_health_check_rejects_wrong_shell(
    body: bytes,
    content_type: str,
    message: str,
) -> None:
    def opener(*_: object, **__: object) -> FakeResponse:
        return FakeResponse(body, content_type=content_type)

    report = check_live_space.run_health_check(
        "https://example.test/",
        retries=1,
        opener=opener,
    )

    assert report["healthy"] is False
    assert message in report["failures"][0]["message"]
