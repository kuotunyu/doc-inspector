from __future__ import annotations

import pytest

from doc_inspector.errors import RequestLimitError
from doc_inspector.rate_limit import HourlyRequestLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_zero_limit_disables_request_guard() -> None:
    limiter = HourlyRequestLimiter(0)

    for _ in range(100):
        limiter.check_and_record()


def test_limiter_reports_retry_and_resets_after_window() -> None:
    clock = FakeClock()
    limiter = HourlyRequestLimiter(2, window_seconds=120, clock=clock)

    limiter.check_and_record()
    clock.now = 30
    limiter.check_and_record()

    with pytest.raises(RequestLimitError, match="每小時 2 次.*約 2 分鐘"):
        limiter.check_and_record()

    clock.now = 121
    limiter.check_and_record()


def test_invalid_limiter_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="不可小於"):
        HourlyRequestLimiter(-1)
    with pytest.raises(ValueError, match="必須大於"):
        HourlyRequestLimiter(1, window_seconds=0)
