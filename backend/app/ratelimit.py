import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import settings

_hits = defaultdict(deque)


def check(key, limit, window_sec):
    if not settings.rate_limit_enabled:
        return

    now = time.monotonic()
    q = _hits[key]

    while q and now - q[0] > window_sec:
        q.popleft()

    if len(q) >= limit:
        raise HTTPException(429, "Too many requests")

    q.append(now)


def reset():
    _hits.clear()
