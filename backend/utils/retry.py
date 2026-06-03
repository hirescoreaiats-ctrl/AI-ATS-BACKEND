from __future__ import annotations

import time
from collections.abc import Callable


def retry(operation: Callable, *, attempts: int = 3, delay_seconds: float = 0.5, backoff: float = 2.0):
    last_error = None
    current_delay = delay_seconds
    for _ in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            time.sleep(current_delay)
            current_delay *= backoff
    raise last_error
