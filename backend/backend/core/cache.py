from __future__ import annotations

import json
from functools import lru_cache

from backend.core.config import get_settings


@lru_cache(maxsize=1)
def redis_client():
    try:
        import redis

        client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def cache_get_json(key: str):
    client = redis_client()
    if not client:
        return None
    value = client.get(key)
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def cache_set_json(key: str, value, ttl_seconds: int = 300) -> None:
    client = redis_client()
    if client:
        client.setex(key, ttl_seconds, json.dumps(value, default=str))
