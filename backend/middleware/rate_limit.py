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
        bucket_name, limit = self._route_limit(request, settings)
        if limit <= 0:
            return await call_next(request)

        now = time.time()
        client_key = request.client.host if request.client else "unknown"
        key = f"{client_key}:{bucket_name}"
        if self.redis:
            redis_key = f"rate:{key}:{int(now // 60)}"
            count = self.redis.incr(redis_key)
            if count == 1:
                self.redis.expire(redis_key, 90)
            if count > limit:
                return Response('{"detail":"Rate limit reached. Please try again later."}', status_code=429, media_type="application/json")
            return await call_next(request)

        bucket = self.requests[key]

        while bucket and bucket[0] <= now - 60:
            bucket.popleft()

        if len(bucket) >= limit:
            return Response('{"detail":"Rate limit reached. Please try again later."}', status_code=429, media_type="application/json")

        bucket.append(now)
        return await call_next(request)

    @staticmethod
    def _route_limit(request: Request, settings) -> tuple[str, int]:
        path = request.url.path.rstrip("/")
        method = request.method.upper()
        if path.endswith("/signup") and method == "POST":
            return "auth-signup", settings.auth_signup_per_minute
        if path.endswith("/login") and method == "POST":
            return "auth-login", settings.auth_login_per_minute
        if "/requirement-platform" not in path:
            return "global", settings.rate_limit_per_minute
        if method == "POST" and path.endswith("/requirements"):
            return "rp-requirement-create", settings.rp_requirement_create_per_minute
        if method == "POST" and path.endswith("/source-request"):
            return "rp-source-request", settings.rp_source_request_per_minute
        if method == "POST" and path.endswith("/invitations"):
            return "rp-invite", settings.rp_invite_per_minute
        if method == "POST" and "/candidates" in path:
            return "rp-candidate-submit", settings.rp_candidate_submit_per_minute
        if method == "GET" and ("/requirements" in path or "/professionals" in path):
            return "rp-search", settings.rp_search_per_minute
        return "rp-global", settings.rate_limit_per_minute
