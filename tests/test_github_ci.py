from __future__ import annotations

from io import BytesIO
import json

import pytest

from scripts_support import load_script_module

check_github_ci = load_script_module("check_github_ci")
EXPECTED_SHA = "a" * 40


class FakeResponse:
    def __init__(self, payload: object, *, status: int = 200) -> None:
        self._body = BytesIO(json.dumps(payload).encode("utf-8"))
        self._status = status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._body.read()


def _run_payload(
    *,
    sha: str = EXPECTED_SHA,
    status: str = "completed",
    conclusion: str | None = "success",
) -> dict[str, object]:
    return {
        "total_count": 1,
        "workflow_runs": [
            {
                "head_sha": sha,
                "status": status,
                "conclusion": conclusion,
                "run_number": 9,
                "html_url": "https://github.com/example/actions/runs/9",
            }
        ],
    }


def test_exact_push_ci_success_is_accepted() -> None:
    requests: list[object] = []

    def opener(request: object, **_: object) -> FakeResponse:
        requests.append(request)
        return FakeResponse(_run_payload())

    report = check_github_ci.fetch_ci_report(EXPECTED_SHA.upper(), opener=opener)

    assert report["ci_passed"] is True
    assert report["expected_sha"] == EXPECTED_SHA
    assert report["sha_matches"] is True
    assert report["status"] == "completed"
    assert report["conclusion"] == "success"
    assert f"head_sha={EXPECTED_SHA}" in requests[0].full_url
    assert "branch=main" in requests[0].full_url
    assert "event=push" in requests[0].full_url
    assert report["uses_authentication"] is False
    assert report["reads_env_truth"] is False
    assert report["performs_writes"] is False


@pytest.mark.parametrize(
    ("payload", "expected_status", "expected_conclusion"),
    [
        (_run_payload(status="in_progress", conclusion=None), "in_progress", None),
        ({"total_count": 0, "workflow_runs": []}, None, None),
        (_run_payload(sha="b" * 40), "completed", "success"),
    ],
)
def test_incomplete_missing_or_wrong_sha_run_does_not_pass(
    payload: object,
    expected_status: str | None,
    expected_conclusion: str | None,
) -> None:
    def opener(*_: object, **__: object) -> FakeResponse:
        return FakeResponse(payload)

    report = check_github_ci.fetch_ci_report(EXPECTED_SHA, opener=opener)

    assert report["ci_passed"] is False
    assert report["status"] == expected_status
    assert report["conclusion"] == expected_conclusion


@pytest.mark.parametrize("value", ["abc123", "g" * 40, "a" * 39])
def test_expected_sha_must_be_full_hex(value: str) -> None:
    with pytest.raises(ValueError, match="40 位"):
        check_github_ci.normalize_sha(value)


@pytest.mark.parametrize("payload", [[], {"workflow_runs": "invalid"}])
def test_malformed_api_payload_is_rejected(payload: object) -> None:
    def opener(*_: object, **__: object) -> FakeResponse:
        return FakeResponse(payload)

    with pytest.raises(ValueError, match="回應不是物件|workflow_runs"):
        check_github_ci.fetch_ci_report(EXPECTED_SHA, opener=opener)
