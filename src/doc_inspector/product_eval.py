"""Reproducible offline evaluation for the deterministic decision layer."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Self

from pydantic import Field, model_validator

from doc_inspector.demo import demo_extractions
from doc_inspector.rules import inspect_extraction
from doc_inspector.schemas import RULES_VERSION, RuleLevel, SchemaRegistry, StrictSchemaModel


class IssueSignature(StrictSchemaModel):
    """Stable identity for one non-green rule result."""

    rule_id: str
    level: RuleLevel
    field_paths: list[str] = Field(default_factory=list)

    def key(self) -> tuple[str, str, tuple[str, ...]]:
        return self.rule_id, self.level, tuple(self.field_paths)


class DecisionCase(StrictSchemaModel):
    """One auditable mutation of a fixed synthetic base document."""

    case_id: str
    description: str
    base: str
    mutations: dict[str, Any] = Field(default_factory=dict)
    expected_overall_level: RuleLevel
    expected_issues: list[IssueSignature] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_expected_contract(self) -> Self:
        issue_keys = [issue.key() for issue in self.expected_issues]
        if len(issue_keys) != len(set(issue_keys)):
            raise ValueError("expected_issues 不得包含重複 issue")
        if any(issue.level == "green" for issue in self.expected_issues):
            raise ValueError("expected_issues 只能列出 red 或 yellow issue")

        expected_level = "green"
        if any(issue.level == "red" for issue in self.expected_issues):
            expected_level = "red"
        elif self.expected_issues:
            expected_level = "yellow"
        if self.expected_overall_level != expected_level:
            raise ValueError(
                "expected_overall_level 必須由 expected_issues 的最嚴重等級推導"
            )
        return self


class DecisionSuite(StrictSchemaModel):
    """Versioned collection of product-level regression cases."""

    benchmark_name: str
    version: str
    scope: str
    oracle_method: str
    cases: list[DecisionCase]

    @model_validator(mode="after")
    def validate_case_identity(self) -> Self:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_id 不得重複")

        definitions = [
            json.dumps(
                {"base": case.base, "mutations": case.mutations},
                ensure_ascii=False,
                sort_keys=True,
            )
            for case in self.cases
        ]
        if len(definitions) != len(set(definitions)):
            raise ValueError("base 與 mutations 組合不得重複")
        return self


class CaseEvaluation(StrictSchemaModel):
    """Comparison between expected and observed product behavior."""

    case_id: str
    description: str
    schema_name: str
    expected_overall_level: RuleLevel
    predicted_overall_level: RuleLevel
    expected_issues: list[IssueSignature]
    predicted_issues: list[IssueSignature]
    missing_issues: list[IssueSignature]
    unexpected_issues: list[IssueSignature]
    passed: bool


class EvaluationMetrics(StrictSchemaModel):
    """Aggregate metrics chosen for the decision-layer contract."""

    case_count: int
    exact_case_matches: int
    overall_status_correct: int
    expected_issue_count: int
    predicted_issue_count: int
    matched_issue_count: int
    expected_red_issue_count: int
    matched_red_issue_count: int
    expected_yellow_issue_count: int
    matched_yellow_issue_count: int
    exact_case_match_rate: float
    overall_status_accuracy: float
    issue_precision: float
    issue_recall: float
    red_issue_recall: float
    yellow_issue_recall: float


class DecisionEvaluationReport(StrictSchemaModel):
    """Serializable evaluation report with explicit scope boundaries."""

    benchmark_name: str
    benchmark_version: str
    rules_version: str
    scope: str
    oracle_method: str
    uses_network: bool = False
    uses_api_keys: bool = False
    passed: bool
    metrics: EvaluationMetrics
    by_expected_level: dict[str, dict[str, int]]
    per_rule: dict[str, dict[str, int]]
    cases: list[CaseEvaluation]


def load_decision_suite(path: Path) -> DecisionSuite:
    """Read and strictly validate a decision benchmark definition."""

    return DecisionSuite.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _set_mutation(payload: Any, path: str, value: Any) -> None:
    """Assign a dotted mutation path in a model-dumped JSON-compatible value."""

    parts = path.split(".")
    current = payload
    for part in parts[:-1]:
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"無效的陣列 mutation path：{path}") from exc
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise ValueError(f"找不到 mutation path：{path}")

    final = parts[-1]
    if isinstance(current, list):
        try:
            if current[int(final)] == value:
                raise ValueError(f"mutation 沒有改變資料：{path}")
            current[int(final)] = value
        except (ValueError, IndexError) as exc:
            if isinstance(exc, ValueError) and str(exc).startswith("mutation"):
                raise
            raise ValueError(f"無效的陣列 mutation path：{path}") from exc
    elif isinstance(current, dict) and final in current:
        if current[final] == value:
            raise ValueError(f"mutation 沒有改變資料：{path}")
        current[final] = value
    else:
        raise ValueError(f"找不到 mutation path：{path}")


def _issue_sort_key(issue: IssueSignature) -> tuple[str, str, tuple[str, ...]]:
    return issue.key()


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def _materialize_case(case: DecisionCase):
    bases = demo_extractions()
    try:
        base = bases[case.base]
    except KeyError as exc:
        raise ValueError(f"未知的 synthetic base：{case.base}") from exc

    payload = base.model_dump(mode="json")
    for path, value in case.mutations.items():
        _set_mutation(payload, path, value)
    model = SchemaRegistry.get(base.schema_name)
    return model.model_validate(payload)


def evaluate_decision_suite(suite: DecisionSuite) -> DecisionEvaluationReport:
    """Evaluate all cases without network, model inference, or environment secrets."""

    results: list[CaseEvaluation] = []
    for case in suite.cases:
        extraction = _materialize_case(case)
        review = inspect_extraction(extraction)
        predicted = [
            IssueSignature(
                rule_id=check.rule_id,
                level=check.level,
                field_paths=check.field_paths,
            )
            for check in review.checks
            if check.level != "green"
        ]
        expected_by_key = {issue.key(): issue for issue in case.expected_issues}
        predicted_by_key = {issue.key(): issue for issue in predicted}
        missing = sorted(
            (expected_by_key[key] for key in expected_by_key.keys() - predicted_by_key.keys()),
            key=_issue_sort_key,
        )
        unexpected = sorted(
            (predicted_by_key[key] for key in predicted_by_key.keys() - expected_by_key.keys()),
            key=_issue_sort_key,
        )
        exact = (
            review.overall_level == case.expected_overall_level
            and not missing
            and not unexpected
        )
        results.append(
            CaseEvaluation(
                case_id=case.case_id,
                description=case.description,
                schema_name=extraction.schema_name,
                expected_overall_level=case.expected_overall_level,
                predicted_overall_level=review.overall_level,
                expected_issues=sorted(case.expected_issues, key=_issue_sort_key),
                predicted_issues=sorted(predicted, key=_issue_sort_key),
                missing_issues=missing,
                unexpected_issues=unexpected,
                passed=exact,
            )
        )

    expected_keys = [
        issue.key()
        for result in results
        for issue in result.expected_issues
    ]
    predicted_keys = [
        issue.key()
        for result in results
        for issue in result.predicted_issues
    ]
    matched_keys = [
        issue.key()
        for result in results
        for issue in result.expected_issues
        if issue.key() in {predicted.key() for predicted in result.predicted_issues}
    ]
    expected_red = sum(key[1] == "red" for key in expected_keys)
    matched_red = sum(key[1] == "red" for key in matched_keys)
    expected_yellow = sum(key[1] == "yellow" for key in expected_keys)
    matched_yellow = sum(key[1] == "yellow" for key in matched_keys)
    exact_matches = sum(result.passed for result in results)
    status_correct = sum(
        result.expected_overall_level == result.predicted_overall_level
        for result in results
    )

    by_level: dict[str, dict[str, int]] = {}
    for level in ("green", "yellow", "red"):
        selected = [result for result in results if result.expected_overall_level == level]
        by_level[level] = {
            "cases": len(selected),
            "passed": sum(result.passed for result in selected),
        }

    expected_rule_counts = Counter(key[0] for key in expected_keys)
    predicted_rule_counts = Counter(key[0] for key in predicted_keys)
    matched_rule_counts = Counter(key[0] for key in matched_keys)
    per_rule = {
        rule_id: {
            "expected": expected_rule_counts[rule_id],
            "predicted": predicted_rule_counts[rule_id],
            "matched": matched_rule_counts[rule_id],
        }
        for rule_id in sorted(expected_rule_counts.keys() | predicted_rule_counts.keys())
    }

    metrics = EvaluationMetrics(
        case_count=len(results),
        exact_case_matches=exact_matches,
        overall_status_correct=status_correct,
        expected_issue_count=len(expected_keys),
        predicted_issue_count=len(predicted_keys),
        matched_issue_count=len(matched_keys),
        expected_red_issue_count=expected_red,
        matched_red_issue_count=matched_red,
        expected_yellow_issue_count=expected_yellow,
        matched_yellow_issue_count=matched_yellow,
        exact_case_match_rate=_rate(exact_matches, len(results)),
        overall_status_accuracy=_rate(status_correct, len(results)),
        issue_precision=_rate(len(matched_keys), len(predicted_keys)),
        issue_recall=_rate(len(matched_keys), len(expected_keys)),
        red_issue_recall=_rate(matched_red, expected_red),
        yellow_issue_recall=_rate(matched_yellow, expected_yellow),
    )
    return DecisionEvaluationReport(
        benchmark_name=suite.benchmark_name,
        benchmark_version=suite.version,
        rules_version=RULES_VERSION,
        scope=suite.scope,
        oracle_method=suite.oracle_method,
        passed=exact_matches == len(results),
        metrics=metrics,
        by_expected_level=by_level,
        per_rule=per_rule,
        cases=results,
    )


def write_decision_report(report: DecisionEvaluationReport, path: Path) -> None:
    """Write stable UTF-8 JSON for review and CI artifacts."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
