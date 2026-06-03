from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.config import get_settings


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.requests: dict[str, deque[float]] = defaultdict(deque)
        self.redis = None
        try:
            import redis

            self.redis = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
            self.redis.ping()
        except Exception:
            self.redis = None

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        now = time.time()
        key = request.client.host if request.client else "unknown"
        if self.redis:
            redis_key = f"rate:{key}:{int(now // 60)}"
            count = self.redis.incr(redis_key)
            if count == 1:
                self.redis.expire(redis_key, 90)
            if count > settings.rate_limit_per_minute:
                return Response("Rate limit exceeded", status_code=429)
            return await call_next(request)

        bucket = self.requests[key]

        while bucket and bucket[0] <= now - 60:
            bucket.popleft()

        if len(bucket) >= settings.rate_limit_per_minute:
            return Response("Rate limit exceeded", status_code=429)

        bucket.append(now)
        return await call_next(request)
