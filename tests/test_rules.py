from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from doc_inspector.rules import (
    aggregate_review,
    inspect_extraction,
    parse_amount,
    parse_document_date,
    run_amount_rules,
    run_date_rules,
    run_identity_rules,
    run_required_rules,
    validate_taiwan_citizen_id,
)
from doc_inspector.schemas import (
    ApplicationLineItem,
    DocumentPerson,
    LocatedIdType,
    LocatedValue,
    Receipt,
    ReceiptLineItem,
    RuleResult,
    SubsidyApplication,
)


def located(value: str | None) -> LocatedValue:
    return LocatedValue(value=value, page_number=1 if value is not None else None)


def valid_person(*, id_type: str = "citizen_id", id_number: str = "A123456789") -> DocumentPerson:
    return DocumentPerson(
        role=located("申請人"),
        name=located("測試者"),
        id_type=LocatedIdType(value=id_type, page_number=1),  # type: ignore[arg-type]
        id_number=located(id_number),
        birth_date=located("民國80年1月2日"),
    )


def valid_subsidy() -> SubsidyApplication:
    return SubsidyApplication(
        program_name=located("測試補助"),
        application_date=located("2026-07-23"),
        applicants=[valid_person()],
        requested_amount=located("NT$3,000"),
        line_items=[
            ApplicationLineItem(description=located("項目一"), amount=located("1,000")),
            ApplicationLineItem(description=located("項目二"), amount=located("2,000")),
        ],
        declared_total=located("3000.00"),
    )


def valid_receipt() -> Receipt:
    return Receipt(
        merchant_name=located("測試商店"),
        receipt_date=located("2026/07/23"),
        line_items=[
            ReceiptLineItem(
                description=located("文件夾"),
                quantity=located("2"),
                unit_price=located("50"),
                line_total=located("100"),
            )
        ],
        subtotal=located("100"),
        tax=located("5"),
        discount=located("0"),
        fees=located("0"),
        total=located("105"),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024-02-29", date(2024, 2, 29)),
        ("2024/2/29", date(2024, 2, 29)),
        ("民國113年2月29日", date(2024, 2, 29)),
        ("113/2/29", date(2024, 2, 29)),
    ],
)
def test_parse_document_date_accepts_supported_formats(raw: str, expected: date) -> None:
    assert parse_document_date(raw) == expected


@pytest.mark.parametrize("raw", ["2023-02-29", "112/2/29", "23/1/1", "民國0年1月1日"])
def test_parse_document_date_rejects_invalid_or_ambiguous_values(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_document_date(raw)


def test_birth_date_after_application_is_red() -> None:
    extraction = valid_subsidy()
    extraction.applicants[0].birth_date = located("2027-01-01")

    checks = run_date_rules(extraction)

    assert any(check.rule_id == "date.birth_before_application" and check.level == "red" for check in checks)


def test_missing_date_dependency_is_yellow() -> None:
    extraction = valid_subsidy()
    extraction.application_date = LocatedValue()

    checks = run_date_rules(extraction)

    assert any(check.rule_id == "date.birth_before_application" and check.level == "yellow" for check in checks)


def test_taiwan_citizen_id_normalizes_width_case_but_not_punctuation() -> None:
    assert validate_taiwan_citizen_id("ａ１２３４５６７８９") is True
    assert validate_taiwan_citizen_id("A123-456-789") is False
    assert validate_taiwan_citizen_id("A123456788") is False


def test_declared_non_citizen_document_requires_manual_review() -> None:
    extraction = valid_subsidy()
    extraction.applicants[0] = valid_person(id_type="passport", id_number="P1234567")

    checks = run_identity_rules(extraction)

    assert checks[0].level == "yellow"
    assert checks[0].rule_id == "identity.manual_review"


def test_unknown_citizen_shaped_id_uses_checksum() -> None:
    extraction = valid_subsidy()
    extraction.applicants[0] = valid_person(id_type="unknown", id_number="A123456789")

    assert run_identity_rules(extraction)[0].level == "green"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("NT$ 1,234.50", Decimal("1234.50")),
        ("新臺幣 3000 元", Decimal("3000")),
        ("(1,200.25)", Decimal("-1200.25")),
        ("＋５０", Decimal("50")),
    ],
)
def test_parse_amount_accepts_common_currency_formats(raw: str, expected: Decimal) -> None:
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("raw", ["1,23", "12-3", "(100", "100.123", "免費"])
def test_parse_amount_rejects_ambiguous_values(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_amount(raw)


def test_subsidy_amounts_allow_one_cent_tolerance() -> None:
    extraction = valid_subsidy()
    extraction.declared_total = located("3000.01")
    extraction.requested_amount = located("3000")

    checks = run_amount_rules(extraction)

    assert next(check for check in checks if check.rule_id == "amount.subsidy_line_total").level == "green"
    assert next(check for check in checks if check.rule_id == "amount.requested_vs_declared").level == "green"


def test_receipt_inconsistent_total_is_red() -> None:
    extraction = valid_receipt()
    extraction.total = located("999")

    checks = run_amount_rules(extraction)

    assert next(check for check in checks if check.rule_id == "amount.receipt_total").level == "red"


def test_receipt_missing_calculation_dependency_is_yellow() -> None:
    extraction = valid_receipt()
    extraction.subtotal = LocatedValue()

    checks = run_amount_rules(extraction)

    assert next(check for check in checks if check.rule_id == "amount.receipt_subtotal").level == "yellow"
    assert next(check for check in checks if check.rule_id == "amount.receipt_total").level == "yellow"


def test_required_rules_detect_whitespace_and_empty_lists() -> None:
    extraction = SubsidyApplication(program_name=located("   "))

    checks = run_required_rules(extraction)

    assert any(check.field_paths == ["program_name"] and check.level == "red" for check in checks)
    assert any(check.field_paths == ["applicants"] and check.level == "red" for check in checks)
    assert any(check.field_paths == ["line_items"] and check.level == "red" for check in checks)


def test_aggregate_review_uses_strictest_level() -> None:
    checks = [
        RuleResult(rule_id="g", level="green", message="green"),
        RuleResult(rule_id="y", level="yellow", message="yellow"),
        RuleResult(rule_id="r", level="red", message="red"),
    ]

    report = aggregate_review(checks)

    assert report.overall_level == "red"
    assert report.message == "檢核完成：紅 1、黃 1、綠 1。"


def test_complete_valid_presets_are_green() -> None:
    assert inspect_extraction(valid_subsidy()).overall_level == "green"
    assert inspect_extraction(valid_receipt()).overall_level == "green"
