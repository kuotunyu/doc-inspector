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
    assert report["contributor_policy_passed"] is True
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
    assert report["contributor_policy_passed"] is False
    assert report["unexpected_logins"] == ["automation-bot"]


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
    assert report["contributor_policy_passed"] is False
    assert private_email not in json.dumps(report)
    assert "Anonymous Author" not in json.dumps(report)


@pytest.mark.parametrize(
    ("logins", "allowed", "unexpected"),
    [
        (["kuotunyu", "dependabot[bot]"], True, []),
        (["dependabot[bot]"], False, []),
        ([], False, []),
        (["kuotunyu", "renovate[bot]"], False, ["renovate[bot]"]),
        (["kuotunyu", "dependabot[bot]", "other-user"], False, ["other-user"]),
    ],
)
def test_contributor_allowlist_requires_owner_and_rejects_unknown_accounts(
    logins: list[str], allowed: bool, unexpected: list[str]
) -> None:
    def opener(*_: object, **__: object) -> FakeResponse:
        return FakeResponse([{"login": login} for login in logins])

    report = check_github_contributors.fetch_contributor_report(opener=opener)

    assert report["contributor_policy_passed"] is allowed
    assert report["unexpected_logins"] == unexpected
    assert report["allowed_logins"] == ["dependabot[bot]", "kuotunyu"]
    assert report["sole_contributor"] is (logins == ["kuotunyu"])


def test_approved_bot_does_not_allow_an_anonymous_contributor() -> None:
    def opener(*_: object, **__: object) -> FakeResponse:
        return FakeResponse(
            [{"login": "kuotunyu"}, {"login": "dependabot[bot]"}, {"name": "Anonymous"}]
        )

    report = check_github_contributors.fetch_contributor_report(opener=opener)

    assert report["contributor_policy_passed"] is False
    assert report["anonymous_contributor_count"] == 1


def test_cli_accepts_owner_and_approved_bot_without_claiming_sole_contributor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def opener(*_: object, **__: object) -> FakeResponse:
        return FakeResponse([{"login": "kuotunyu"}, {"login": "dependabot[bot]"}])

    report = check_github_contributors.fetch_contributor_report(opener=opener)
    monkeypatch.setattr(check_github_contributors, "fetch_contributor_report", lambda: report)

    assert check_github_contributors.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["sole_contributor"] is False
    assert output["contributor_policy_passed"] is True


@pytest.mark.parametrize("payload", [{"message": "not a list"}, ["invalid item"]])
def test_malformed_api_payload_is_rejected(payload: object) -> None:
    def opener(*_: object, **__: object) -> FakeResponse:
        return FakeResponse(payload)

    with pytest.raises(ValueError, match="回應不是清單|無效項目"):
        check_github_contributors.fetch_contributor_report(opener=opener)
