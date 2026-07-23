"""Pure helpers for enforcing explicit paid-API cost approvals."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def parse_positive_usd(value: str) -> Decimal:
    """Parse a finite, positive US-dollar amount without float rounding."""

    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("必須是有效的十進位金額。") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("必須是大於 0 的有限金額。")
    return parsed


def require_approved_budget(*, approved_usd: Decimal, estimated_usd: Decimal) -> None:
    """Reject a paid operation whose conservative estimate exceeds approval."""

    if not estimated_usd.is_finite() or estimated_usd < 0:
        raise ValueError("成本估算必須是大於或等於 0 的有限金額。")
    if not approved_usd.is_finite() or approved_usd <= 0:
        raise ValueError("核准上限必須是大於 0 的有限金額。")
    if approved_usd < estimated_usd:
        raise ValueError(
            f"核准上限 US${approved_usd} 低於保守估算 US${estimated_usd}。"
        )
