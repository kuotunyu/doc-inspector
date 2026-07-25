from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from doc_inspector.product_eval import (
    DecisionCase,
    DecisionSuite,
    IssueSignature,
    evaluate_decision_suite,
    load_decision_suite,
)


CASES_PATH = Path("data/evaluation/decision_cases.json")


def test_decision_suite_covers_levels_and_schemas() -> None:
    suite = load_decision_suite(CASES_PATH)

    assert len(suite.cases) >= 20
    assert len({case.case_id for case in suite.cases}) == len(suite.cases)
    assert {case.expected_overall_level for case in suite.cases} == {
        "green",
        "yellow",
        "red",
    }
    assert {case.base.split("_", maxsplit=1)[0] for case in suite.cases} == {
        "subsidy",
        "receipt",
    }
    assert "人工" in suite.oracle_method
    assert "不從目前規則引擎輸出自動產生" in suite.oracle_method


def test_decision_suite_matches_the_product_contract() -> None:
    report = evaluate_decision_suite(load_decision_suite(CASES_PATH))

    assert report.passed is True
    assert report.metrics.case_count >= 20
    assert report.metrics.exact_case_match_rate == 1.0
    assert report.metrics.overall_status_accuracy == 1.0
    assert report.metrics.issue_precision == 1.0
    assert report.metrics.red_issue_recall == 1.0
    assert report.metrics.yellow_issue_recall == 1.0
    assert all(result.passed for result in report.cases)


def test_decision_suite_exposes_actionable_error_analysis() -> None:
    suite = deepcopy(load_decision_suite(CASES_PATH))
    case = suite.cases[0]
    case.expected_overall_level = "yellow"
    case.expected_issues = [
        IssueSignature(
            rule_id="identity.manual_review",
            level="yellow",
            field_paths=["applicants.0.id_number", "applicants.0.id_type"],
        )
    ]

    report = evaluate_decision_suite(suite)
    result = report.cases[0]

    assert report.passed is False
    assert result.passed is False
    assert result.missing_issues == case.expected_issues
    assert result.unexpected_issues == []


def test_decision_contract_rejects_tautological_or_inconsistent_oracles() -> None:
    issue = IssueSignature(
        rule_id="required.value",
        level="red",
        field_paths=["merchant_name"],
    )
    with pytest.raises(ValidationError, match="不得包含重複 issue"):
        DecisionCase(
            case_id="duplicate-issue",
            description="同一預期問題重複列出。",
            base="receipt_green",
            expected_overall_level="red",
            expected_issues=[issue, issue],
        )

    with pytest.raises(ValidationError, match="最嚴重等級"):
        DecisionCase(
            case_id="wrong-level",
            description="整體燈號與人工預期 issue 不一致。",
            base="receipt_green",
            expected_overall_level="yellow",
            expected_issues=[issue],
        )

    valid_case = DecisionCase(
        case_id="unique-case",
        description="唯一案例。",
        base="receipt_green",
        expected_overall_level="green",
    )
    with pytest.raises(ValidationError, match="case_id 不得重複"):
        DecisionSuite(
            benchmark_name="invalid-suite",
            version="1.0.0",
            scope="測試案例識別約束。",
            oracle_method="人工定義。",
            cases=[valid_case, valid_case],
        )


def test_decision_suite_rejects_no_op_mutations() -> None:
    suite = DecisionSuite(
        benchmark_name="no-op-suite",
        version="1.0.0",
        scope="測試 mutation 必須實際改變資料。",
        oracle_method="人工定義。",
        cases=[
            DecisionCase(
                case_id="no-op",
                description="把商家名稱設成原值不構成測試案例。",
                base="receipt_green",
                mutations={"merchant_name.value": "示範生活商店"},
                expected_overall_level="green",
            )
        ],
    )

    with pytest.raises(ValueError, match="mutation 沒有改變資料"):
        evaluate_decision_suite(suite)


def test_product_evaluation_cli_writes_machine_readable_report(tmp_path: Path) -> None:
    output = tmp_path / "decision-evaluation.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_product_evaluation.py",
            "--cases",
            str(CASES_PATH),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    assert completed.returncode == 0, completed.stderr
    assert "不代表端到端 OCR/VLM 準確率" in completed.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["uses_network"] is False
    assert payload["uses_api_keys"] is False

    checked = subprocess.run(
        [
            sys.executable,
            "scripts/run_product_evaluation.py",
            "--cases",
            str(CASES_PATH),
            "--output",
            str(output),
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert checked.returncode == 0, checked.stderr
