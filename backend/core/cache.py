"""Cache facade: Redis in production, process memory for local development."""
from __future__ import annotations

import json
import time
from typing import Any

import redis

from backend.core.config import get_settings


class TTLCache:
    def __init__(self) -> None:
        self._values: dict[str, tuple[float, Any]] = {}
        self._redis = redis.Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=0.25, socket_timeout=0.25)

    def get(self, key: str) -> Any | None:
        try:
            if value := self._redis.get(key):
                return json.loads(value)
        except redis.RedisError:
            pass
        value = self._values.get(key)
        if not value or value[0] < time.time():
            self._values.pop(key, None)
            return None
        return value[1]

    def set(self, key: str, value: Any, ttl: int) -> None:
        self._values[key] = (time.time() + ttl, value)
        try:
            self._redis.setex(key, ttl, json.dumps(value, default=str))
        except redis.RedisError:
            pass

    def delete(self, key: str) -> None:
        self._values.pop(key, None)
        try:
            self._redis.delete(key)
        except redis.RedisError:
            pass


cache = TTLCache()
