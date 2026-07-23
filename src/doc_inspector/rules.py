"""Pure deterministic validation rules for extracted document fields."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re
import unicodedata

from doc_inspector.schemas import (
    DocumentExtraction,
    DocumentPerson,
    LocatedValue,
    Receipt,
    ReviewReport,
    RuleLevel,
    RuleResult,
    SubsidyApplication,
)

AMOUNT_TOLERANCE = Decimal("0.01")
_GREGORIAN_DATE = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$")
_ROC_TEXT_DATE = re.compile(r"^民國\s*(\d{1,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日$")
_ROC_SLASH_DATE = re.compile(r"^(\d{3})/(\d{1,2})/(\d{1,2})$")
_CITIZEN_ID = re.compile(r"^[A-Z][12]\d{8}$")
_AMOUNT_NUMBER = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?$")
_CURRENCY_PREFIX = re.compile(r"^(?:NT\$|TWD|USD|US\$|新臺幣|新台幣|[$€¥￥])", re.IGNORECASE)
_CURRENCY_SUFFIX = re.compile(r"(?:元|圓)$")

_LETTER_CODES = {
    "A": 10, "B": 11, "C": 12, "D": 13, "E": 14, "F": 15, "G": 16,
    "H": 17, "I": 34, "J": 18, "K": 19, "L": 20, "M": 21, "N": 22,
    "O": 35, "P": 23, "Q": 24, "R": 25, "S": 26, "T": 27, "U": 28,
    "V": 29, "W": 32, "X": 30, "Y": 31, "Z": 33,
}


def _normalized_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def _located_text(located: LocatedValue | None) -> str | None:
    if located is None or located.value is None:
        return None
    normalized = _normalized_text(located.value)
    return normalized or None


def _result(
    rule_id: str,
    level: RuleLevel,
    message: str,
    *field_paths: str,
    observed: str | None = None,
    expected: str | None = None,
) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        level=level,
        message=message,
        field_paths=list(field_paths),
        observed=observed,
        expected=expected,
    )


def _required_value(path: str, value: LocatedValue) -> RuleResult:
    observed = _located_text(value)
    if observed is None:
        return _result("required.value", "red", f"必要欄位 {path} 缺漏。", path, expected="非空值")
    return _result("required.value", "green", f"必要欄位 {path} 已提供。", path, observed=observed)


def run_required_rules(extraction: DocumentExtraction) -> list[RuleResult]:
    """Check preset-specific required values, nested records, and empty lists."""

    checks: list[RuleResult] = []
    if isinstance(extraction, SubsidyApplication):
        for path, value in (
            ("program_name", extraction.program_name),
            ("application_date", extraction.application_date),
            ("requested_amount", extraction.requested_amount),
            ("declared_total", extraction.declared_total),
        ):
            checks.append(_required_value(path, value))
        if not extraction.applicants:
            checks.append(_result("required.list", "red", "至少需要一位申請人。", "applicants", expected="至少 1 筆"))
        else:
            checks.append(_result("required.list", "green", "申請人清單已提供。", "applicants", observed=str(len(extraction.applicants))))
            for index, person in enumerate(extraction.applicants):
                checks.append(_required_value(f"applicants.{index}.name", person.name))
                checks.append(_required_value(f"applicants.{index}.id_number", person.id_number))
        if not extraction.line_items:
            checks.append(_result("required.list", "red", "補助明細不可為空。", "line_items", expected="至少 1 筆"))
        else:
            checks.append(_result("required.list", "green", "補助明細已提供。", "line_items", observed=str(len(extraction.line_items))))
            for index, item in enumerate(extraction.line_items):
                checks.append(_required_value(f"line_items.{index}.description", item.description))
                checks.append(_required_value(f"line_items.{index}.amount", item.amount))
    else:
        for path, value in (
            ("merchant_name", extraction.merchant_name),
            ("receipt_date", extraction.receipt_date),
            ("total", extraction.total),
        ):
            checks.append(_required_value(path, value))
        if not extraction.line_items:
            checks.append(_result("required.list", "red", "收據品項不可為空。", "line_items", expected="至少 1 筆"))
        else:
            checks.append(_result("required.list", "green", "收據品項已提供。", "line_items", observed=str(len(extraction.line_items))))
            for index, item in enumerate(extraction.line_items):
                checks.append(_required_value(f"line_items.{index}.description", item.description))
                checks.append(_required_value(f"line_items.{index}.line_total", item.line_total))
    return checks


def parse_document_date(value: str) -> date:
    """Parse supported Gregorian and explicit ROC calendar formats."""

    normalized = _normalized_text(value)
    match = _GREGORIAN_DATE.fullmatch(normalized)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return date(year, month, day)
    match = _ROC_TEXT_DATE.fullmatch(normalized) or _ROC_SLASH_DATE.fullmatch(normalized)
    if match:
        roc_year, month, day = (int(part) for part in match.groups())
        if roc_year < 1:
            raise ValueError("民國年份必須大於 0")
        return date(roc_year + 1911, month, day)
    raise ValueError("不支援的日期格式")


def _date_value_check(path: str, value: LocatedValue) -> tuple[RuleResult, date | None]:
    raw = _located_text(value)
    if raw is None:
        return _result("date.parse", "yellow", f"{path} 缺漏，無法檢查日期。", path, expected="有效日期"), None
    try:
        parsed = parse_document_date(raw)
    except ValueError:
        return _result("date.parse", "red", f"{path} 日期格式或日期值無效。", path, observed=raw, expected="YYYY-MM-DD、YYYY/MM/DD 或明確民國日期"), None
    return _result("date.parse", "green", f"{path} 日期有效。", path, observed=parsed.isoformat()), parsed


def _people(extraction: SubsidyApplication) -> list[tuple[str, DocumentPerson]]:
    return [
        *((f"applicants.{index}", person) for index, person in enumerate(extraction.applicants)),
        *((f"beneficiaries.{index}", person) for index, person in enumerate(extraction.beneficiaries)),
    ]


def run_date_rules(extraction: DocumentExtraction) -> list[RuleResult]:
    """Validate document dates and birth-date ordering dependencies."""

    if isinstance(extraction, Receipt):
        return [_date_value_check("receipt_date", extraction.receipt_date)[0]]

    application_check, application_date = _date_value_check("application_date", extraction.application_date)
    checks = [application_check]
    for path, person in _people(extraction):
        birth_path = f"{path}.birth_date"
        birth_check, birth_date = _date_value_check(birth_path, person.birth_date)
        checks.append(birth_check)
        if birth_date is None or application_date is None:
            checks.append(_result("date.birth_before_application", "yellow", "缺少有效出生日期或申請日期，無法比較先後。", birth_path, "application_date", expected="出生日期不得晚於申請日期"))
        elif birth_date > application_date:
            checks.append(_result("date.birth_before_application", "red", "出生日期晚於申請日期。", birth_path, "application_date", observed=f"{birth_date.isoformat()} > {application_date.isoformat()}", expected="出生日期 <= 申請日期"))
        else:
            checks.append(_result("date.birth_before_application", "green", "出生日期不晚於申請日期。", birth_path, "application_date", observed=f"{birth_date.isoformat()} <= {application_date.isoformat()}"))
    return checks


def validate_taiwan_citizen_id(value: str) -> bool:
    """Validate a Taiwan national identification number and checksum."""

    normalized = _normalized_text(value).upper()
    if not _CITIZEN_ID.fullmatch(normalized):
        return False
    code = _LETTER_CODES[normalized[0]]
    digits = [int(character) for character in normalized[1:]]
    checksum = code // 10 + (code % 10) * 9
    checksum += sum(digit * weight for digit, weight in zip(digits[:-1], range(8, 0, -1), strict=True))
    checksum += digits[-1]
    return checksum % 10 == 0


def run_identity_rules(extraction: DocumentExtraction) -> list[RuleResult]:
    """Apply citizen-ID checksum only where the declared document type permits it."""

    if not isinstance(extraction, SubsidyApplication):
        return []
    checks: list[RuleResult] = []
    for path, person in _people(extraction):
        id_path = f"{path}.id_number"
        value = _located_text(person.id_number)
        id_type = person.id_type.value or "unknown"
        if value is None:
            checks.append(_result("identity.document", "yellow", "證件號碼缺漏，無法檢核。", id_path, f"{path}.id_type", expected="可辨識的證件號碼"))
            continue
        normalized = _normalized_text(value).upper()
        should_validate = id_type == "citizen_id" or (id_type == "unknown" and bool(_CITIZEN_ID.fullmatch(normalized)))
        if should_validate:
            valid = validate_taiwan_citizen_id(normalized)
            checks.append(_result("identity.citizen_id", "green" if valid else "red", "台灣身分證字號與檢查碼有效。" if valid else "台灣身分證字號格式或檢查碼無效。", id_path, f"{path}.id_type", observed=normalized, expected="有效台灣國民身分證字號"))
        else:
            checks.append(_result("identity.manual_review", "yellow", f"證件種類 {id_type} 不套用國民身分證檢查碼，需人工確認。", id_path, f"{path}.id_type", observed=normalized, expected="人工核對原始文件"))
    return checks


def parse_amount(value: str) -> Decimal:
    """Parse common currency notation while rejecting ambiguous characters."""

    normalized = _normalized_text(value)
    negative_parentheses = normalized.startswith("(") and normalized.endswith(")")
    if negative_parentheses:
        normalized = normalized[1:-1].strip()
    elif normalized.startswith("(") or normalized.endswith(")"):
        raise ValueError("金額括號不完整")
    normalized = re.sub(r"\s+", "", normalized)
    normalized = _CURRENCY_PREFIX.sub("", normalized, count=1)
    normalized = _CURRENCY_SUFFIX.sub("", normalized, count=1)
    if not _AMOUNT_NUMBER.fullmatch(normalized):
        raise ValueError("金額格式無效")
    try:
        parsed = Decimal(normalized.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("金額無法解析") from exc
    if negative_parentheses:
        parsed = -parsed
    return parsed


def _amount_value(path: str, value: LocatedValue, *, missing_is_yellow: bool = True) -> tuple[RuleResult | None, Decimal | None]:
    raw = _located_text(value)
    if raw is None:
        if not missing_is_yellow:
            return None, None
        return _result("amount.parse", "yellow", f"{path} 缺漏，無法計算。", path, expected="可解析金額"), None
    try:
        parsed = parse_amount(raw)
    except ValueError:
        return _result("amount.parse", "red", f"{path} 金額格式無效。", path, observed=raw, expected="有效十進位金額"), None
    return _result("amount.parse", "green", f"{path} 金額可解析。", path, observed=format(parsed, "f")), parsed


def _comparison(rule_id: str, message: str, paths: tuple[str, ...], observed: Decimal, expected: Decimal) -> RuleResult:
    difference = abs(observed - expected)
    if difference <= AMOUNT_TOLERANCE:
        return _result(rule_id, "green", f"{message}一致。", *paths, observed=format(observed, "f"), expected=format(expected, "f"))
    return _result(rule_id, "red", f"{message}不一致。", *paths, observed=format(observed, "f"), expected=format(expected, "f"))


def _subsidy_amount_rules(extraction: SubsidyApplication) -> list[RuleResult]:
    checks: list[RuleResult] = []
    requested_check, requested = _amount_value("requested_amount", extraction.requested_amount)
    declared_check, declared = _amount_value("declared_total", extraction.declared_total)
    checks.extend(check for check in (requested_check, declared_check) if check is not None)
    line_amounts: list[Decimal] = []
    line_complete = bool(extraction.line_items)
    for index, item in enumerate(extraction.line_items):
        check, amount = _amount_value(f"line_items.{index}.amount", item.amount)
        if check is not None:
            checks.append(check)
        if amount is None:
            line_complete = False
        else:
            line_amounts.append(amount)
    if line_complete and declared is not None:
        checks.append(_comparison("amount.subsidy_line_total", "補助明細總和與申報總額", ("line_items", "declared_total"), sum(line_amounts, Decimal("0")), declared))
    else:
        checks.append(_result("amount.subsidy_line_total", "yellow", "缺少可解析的補助明細或申報總額，無法核對。", "line_items", "declared_total", expected="明細總和與申報總額差額 <= 0.01"))
    if requested is not None and declared is not None:
        checks.append(_comparison("amount.requested_vs_declared", "申請金額與申報總額", ("requested_amount", "declared_total"), requested, declared))
    else:
        checks.append(_result("amount.requested_vs_declared", "yellow", "缺少可解析的申請金額或申報總額，無法核對。", "requested_amount", "declared_total"))
    return checks


def _receipt_amount_rules(extraction: Receipt) -> list[RuleResult]:
    checks: list[RuleResult] = []
    line_totals: list[Decimal] = []
    lines_complete = bool(extraction.line_items)
    for index, item in enumerate(extraction.line_items):
        total_check, line_total = _amount_value(f"line_items.{index}.line_total", item.line_total)
        quantity_check, quantity = _amount_value(f"line_items.{index}.quantity", item.quantity)
        unit_check, unit_price = _amount_value(f"line_items.{index}.unit_price", item.unit_price)
        checks.extend(check for check in (total_check, quantity_check, unit_check) if check is not None)
        if line_total is None:
            lines_complete = False
        else:
            line_totals.append(line_total)
        if quantity is not None and unit_price is not None and line_total is not None:
            checks.append(_comparison("amount.receipt_line", "品項數量乘單價與品項金額", (f"line_items.{index}.quantity", f"line_items.{index}.unit_price", f"line_items.{index}.line_total"), quantity * unit_price, line_total))
        else:
            checks.append(_result("amount.receipt_line", "yellow", "缺少可解析的數量、單價或品項金額，無法核對。", f"line_items.{index}.quantity", f"line_items.{index}.unit_price", f"line_items.{index}.line_total"))

    subtotal_check, subtotal = _amount_value("subtotal", extraction.subtotal)
    total_check, total = _amount_value("total", extraction.total)
    checks.extend(check for check in (subtotal_check, total_check) if check is not None)
    optional_values: dict[str, Decimal] = {}
    optional_valid = True
    for path, value in (("tax", extraction.tax), ("discount", extraction.discount), ("fees", extraction.fees)):
        check, parsed = _amount_value(path, value, missing_is_yellow=False)
        if check is not None:
            checks.append(check)
        if _located_text(value) is not None and parsed is None:
            optional_valid = False
        optional_values[path] = parsed or Decimal("0")

    if lines_complete and subtotal is not None:
        checks.append(_comparison("amount.receipt_subtotal", "品項總和與小計", ("line_items", "subtotal"), sum(line_totals, Decimal("0")), subtotal))
    else:
        checks.append(_result("amount.receipt_subtotal", "yellow", "缺少可解析的品項金額或小計，無法核對。", "line_items", "subtotal"))
    if subtotal is not None and total is not None and optional_valid:
        expected_total = subtotal + optional_values["tax"] - optional_values["discount"] + optional_values["fees"]
        checks.append(_comparison("amount.receipt_total", "小計加稅額、扣折扣、加其他費用與總額", ("subtotal", "tax", "discount", "fees", "total"), expected_total, total))
    else:
        checks.append(_result("amount.receipt_total", "yellow", "缺少可解析的總額計算要件，無法核對。", "subtotal", "tax", "discount", "fees", "total"))
    return checks


def run_amount_rules(extraction: DocumentExtraction) -> list[RuleResult]:
    """Validate amount syntax and preset-specific arithmetic consistency."""

    if isinstance(extraction, SubsidyApplication):
        return _subsidy_amount_rules(extraction)
    return _receipt_amount_rules(extraction)


def aggregate_review(checks: list[RuleResult]) -> ReviewReport:
    """Aggregate checks using strict red > yellow > green precedence."""

    precedence = {"red": 3, "yellow": 2, "green": 1}
    overall: RuleLevel = max((check.level for check in checks), key=precedence.get, default="green")
    counts = {level: sum(check.level == level for check in checks) for level in ("red", "yellow", "green")}
    return ReviewReport(
        overall_level=overall,
        message=f"檢核完成：紅 {counts['red']}、黃 {counts['yellow']}、綠 {counts['green']}。",
        checks=checks,
    )


def inspect_extraction(extraction: DocumentExtraction) -> ReviewReport:
    """Run every Phase 2 rule without I/O or external services."""

    checks = [
        *run_required_rules(extraction),
        *run_date_rules(extraction),
        *run_identity_rules(extraction),
        *run_amount_rules(extraction),
    ]
    return aggregate_review(checks)
