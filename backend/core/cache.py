"""Cache facade: Redis in production, process memory for local development."""
from __future__ import annotations

import json
import time
from typing import Any


class TTLCache:
    def __init__(self) -> None:
        self._values: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        value = self._values.get(key)
        if not value or value[0] < time.time():
            self._values.pop(key, None)
            return None
        return value[1]

    def set(self, key: str, value: Any, ttl: int) -> None:
        self._values[key] = (time.time() + ttl, value)


cache = TTLCache()
