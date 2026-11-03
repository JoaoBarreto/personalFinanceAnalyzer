import time
from collections import defaultdict, deque

from .config import LOGIN_MAX_FAILURES, LOGIN_WINDOW_SECONDS

_failures: dict[str, deque[float]] = defaultdict(deque)


def _prune(key: str, now: float) -> deque[float]:
    q = _failures[key]
    while q and now - q[0] > LOGIN_WINDOW_SECONDS:
        q.popleft()
    return q


def is_blocked(key: str) -> bool:
    return len(_prune(key, time.monotonic())) >= LOGIN_MAX_FAILURES


def record_failure(key: str) -> None:
    now = time.monotonic()
    _prune(key, now).append(now)


def reset(key: str | None = None) -> None:
    if key is None:
        _failures.clear()
    else:
        _failures.pop(key, None)
