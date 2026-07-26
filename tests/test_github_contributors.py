from __future__ import annotations

from io import BytesIO
import json

import pytest

from scripts_support import load_script_module

check_github_contributors = load_script_module("check_github_contributors")


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


def test_expected_account_is_the_only_public_contributor() -> None:
    requests: list[object] = []

    def opener(request: object, **_: object) -> FakeResponse:
        requests.append(request)
        return FakeResponse([{"login": "kuotunyu", "contributions": 12}])

    report = check_github_contributors.fetch_contributor_report(opener=opener)

    assert report["verified"] is True
    assert report["sole_contributor"] is True
    assert report["logins"] == ["kuotunyu"]
    assert report["anonymous_contributor_count"] == 0
    assert report["pages_checked"] == 1
    assert "anon=1" in requests[0].full_url
    assert "per_page=100" in requests[0].full_url
    assert requests[0].get_header("X-github-api-version") == "2026-03-10"
    assert report["uses_authentication"] is False
    assert report["reads_env_truth"] is False
    assert report["performs_writes"] is False


def test_second_github_account_fails_the_sole_contributor_gate() -> None:
    def opener(*_: object, **__: object) -> FakeResponse:
        return FakeResponse(
            [
                {"login": "kuotunyu", "contributions": 12},
                {"login": "automation-bot", "contributions": 1},
            ]
        )

    report = check_github_contributors.fetch_contributor_report(opener=opener)

    assert report["sole_contributor"] is False
    assert report["logins"] == ["automation-bot", "kuotunyu"]


def test_anonymous_identity_fails_without_exposing_personal_fields() -> None:
    private_email = "someone@example.test"

    def opener(*_: object, **__: object) -> FakeResponse:
        return FakeResponse(
            [
                {"login": "kuotunyu", "contributions": 12},
                {"name": "Anonymous Author", "email": private_email, "contributions": 1},
            ]
        )

    report = check_github_contributors.fetch_contributor_report(opener=opener)

    assert report["sole_contributor"] is False
    assert report["anonymous_contributor_count"] == 1
    assert private_email not in json.dumps(report)
    assert "Anonymous Author" not in json.dumps(report)


@pytest.mark.parametrize("payload", [{"message": "not a list"}, ["invalid item"]])
def test_malformed_api_payload_is_rejected(payload: object) -> None:
    def opener(*_: object, **__: object) -> FakeResponse:
        return FakeResponse(payload)

    with pytest.raises(ValueError, match="回應不是清單|無效項目"):
        check_github_contributors.fetch_contributor_report(opener=opener)
