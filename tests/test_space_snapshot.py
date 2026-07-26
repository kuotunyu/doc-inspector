from __future__ import annotations

from io import BytesIO

import pytest

from scripts_support import load_script_module

check_space_snapshot = load_script_module("check_space_snapshot")
EXPECTED_SHA = "a" * 40


class FakeResponse:
    def __init__(self, payload: bytes, *, status: int = 200) -> None:
        self._body = BytesIO(payload)
        self._status = status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def getcode(self) -> int:
        return self._status

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)


def test_matching_runtime_files_pass_without_authentication_or_writes() -> None:
    requests: list[object] = []

    def opener(request: object, **_: object) -> FakeResponse:
        requests.append(request)
        return FakeResponse(b"same source")

    report = check_space_snapshot.compare_critical_source(
        EXPECTED_SHA,
        opener=opener,
    )

    assert report["critical_source_match"] is True
    assert report["matched_file_count"] == len(check_space_snapshot.CRITICAL_FILES)
    assert report["mismatched_files"] == []
    assert report["line_ending_only_mismatches"] == []
    assert report["content_mismatches"] == []
    assert len(requests) == len(check_space_snapshot.CRITICAL_FILES) * 2
    assert all(request.full_url.startswith("https://") for request in requests)
    assert report["uses_authentication"] is False
    assert report["reads_env_truth"] is False
    assert report["uploads_documents"] is False
    assert report["calls_model"] is False
    assert report["performs_writes"] is False


def test_mismatched_file_is_reported_by_path_only() -> None:
    mismatched_path = "src/doc_inspector/ui.py"
    github_payload = b"private-github-file-payload"
    space_payload = b"private-space-file-payload"

    def opener(request: object, **_: object) -> FakeResponse:
        payload = github_payload
        if (
            "huggingface.co" in request.full_url
            and request.full_url.endswith(mismatched_path)
        ):
            payload = space_payload
        return FakeResponse(payload)

    report = check_space_snapshot.compare_critical_source(
        EXPECTED_SHA,
        opener=opener,
    )

    assert report["critical_source_match"] is False
    assert report["mismatched_files"] == [mismatched_path]
    assert report["line_ending_only_mismatches"] == []
    assert report["content_mismatches"] == [mismatched_path]
    assert github_payload.decode() not in str(report)
    assert space_payload.decode() not in str(report)


def test_line_ending_only_mismatch_is_diagnosed_without_payloads() -> None:
    mismatched_path = "src/doc_inspector/ui.py"
    github_payload = b"first line\nsecond line\n"
    space_payload = b"first line\r\nsecond line\r\n"

    def opener(request: object, **_: object) -> FakeResponse:
        payload = github_payload
        if (
            "huggingface.co" in request.full_url
            and request.full_url.endswith(mismatched_path)
        ):
            payload = space_payload
        return FakeResponse(payload)

    report = check_space_snapshot.compare_critical_source(
        EXPECTED_SHA,
        opener=opener,
    )

    assert report["critical_source_match"] is False
    assert report["mismatched_files"] == [mismatched_path]
    assert report["line_ending_only_mismatches"] == [mismatched_path]
    assert report["content_mismatches"] == []
    assert github_payload.decode() not in str(report)
    assert space_payload.decode() not in str(report)


@pytest.mark.parametrize("value", ["abc123", "g" * 40, "a" * 39])
def test_github_sha_must_be_full_hex(value: str) -> None:
    with pytest.raises(ValueError, match="40 位"):
        check_space_snapshot.normalize_sha(value)


def test_oversized_remote_file_is_rejected() -> None:
    def opener(*_: object, **__: object) -> FakeResponse:
        return FakeResponse(b"x" * (check_space_snapshot.MAX_FILE_BYTES + 1))

    with pytest.raises(RuntimeError, match="安全讀取上限"):
        check_space_snapshot.compare_critical_source(EXPECTED_SHA, opener=opener)


def test_non_200_remote_file_is_rejected() -> None:
    def opener(*_: object, **__: object) -> FakeResponse:
        return FakeResponse(b"missing", status=404)

    with pytest.raises(RuntimeError, match="HTTP 404"):
        check_space_snapshot.compare_critical_source(EXPECTED_SHA, opener=opener)
