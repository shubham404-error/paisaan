"""Process-local refresh protection for Streamlit's shared runtime cache."""
from __future__ import annotations

from threading import Lock
from time import monotonic


class RefreshGate:
    """Allow one explicit upstream refresh per cooldown window per app process."""

    def __init__(self, cooldown_seconds: int = 60) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._last_refresh = 0.0
        self._lock = Lock()

    def request(self) -> tuple[bool, int]:
        with self._lock:
            elapsed = monotonic() - self._last_refresh
            remaining = max(0, self.cooldown_seconds - int(elapsed))
            if self._last_refresh and remaining:
                return False, remaining
            self._last_refresh = monotonic()
            return True, 0
