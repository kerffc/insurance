"""Simple in-memory rate limiter for FastAPI endpoints."""

import time
import threading
from collections import defaultdict

from fastapi import HTTPException, Request


class RateLimiter:
    """Token-bucket rate limiter keyed by client IP."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def check(self, request: Request) -> None:
        ip = self._client_ip(request)
        now = time.monotonic()
        with self._lock:
            hits = self._hits[ip]
            cutoff = now - self.window
            self._hits[ip] = [t for t in hits if t > cutoff]
            hits = self._hits[ip]
            if len(hits) >= self.max_requests:
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many requests. Try again in {self.window} seconds.",
                )
            hits.append(now)


login_limiter = RateLimiter(max_requests=10, window_seconds=60)
api_limiter = RateLimiter(max_requests=30, window_seconds=60)
