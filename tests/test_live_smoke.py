from __future__ import annotations

from decimal import Decimal

import pytest

from doc_inspector.costs import parse_positive_usd, require_approved_budget

SMOKE_ESTIMATED_COST_USD = Decimal("0.045932")


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "not-a-number"])
def test_positive_decimal_rejects_non_positive_or_non_finite_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_positive_usd(value)


def test_smoke_budget_rejects_ceiling_below_estimate() -> None:
    with pytest.raises(ValueError, match="低於保守估算"):
        require_approved_budget(
            approved_usd=SMOKE_ESTIMATED_COST_USD - Decimal("0.000001"),
            estimated_usd=SMOKE_ESTIMATED_COST_USD,
        )


def test_smoke_budget_accepts_exact_estimate() -> None:
    require_approved_budget(
        approved_usd=SMOKE_ESTIMATED_COST_USD,
        estimated_usd=SMOKE_ESTIMATED_COST_USD,
    )
