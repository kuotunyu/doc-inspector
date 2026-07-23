"""Small in-process request budget for public demo deployments."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from math import ceil
from threading import Lock
from time import monotonic

from doc_inspector.errors import RequestLimitError


class HourlyRequestLimiter:
    """Limit expensive requests in one app process over a rolling window.

    A limit of zero disables the guard. This is intentionally a deployment
    safety net, not a per-user identity system or a substitute for provider
    billing limits.
    """

    def __init__(
        self,
        max_requests: int,
        *,
        window_seconds: float = 3600,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_requests < 0:
            raise ValueError("max_requests 不可小於 0。")
        if window_seconds <= 0:
            raise ValueError("window_seconds 必須大於 0。")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._timestamps: deque[float] = deque()
        self._lock = Lock()

    def check_and_record(self) -> None:
        """Record one request or raise a user-facing limit error."""

        if self.max_requests == 0:
            return

        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.max_requests:
                retry_seconds = self._timestamps[0] + self.window_seconds - now
                retry_minutes = max(1, ceil(retry_seconds / 60))
                raise RequestLimitError(
                    "公開測試版目前已達"
                    f"每小時 {self.max_requests} 次的共用上限；"
                    f"請約 {retry_minutes} 分鐘後再試。"
                )
            self._timestamps.append(now)
