from __future__ import annotations

import time
from collections import Counter, defaultdict

REQUEST_COUNT = Counter()
REQUEST_LATENCY = defaultdict(list)
AI_LATENCY = defaultdict(list)


def record_request(path: str, method: str, status_code: int, elapsed_ms: float) -> None:
    REQUEST_COUNT[(method, path, status_code)] += 1
    REQUEST_LATENCY[(method, path)].append(elapsed_ms)


def record_ai_latency(operation: str, elapsed_ms: float) -> None:
    AI_LATENCY[operation].append(elapsed_ms)


def timed_ai(operation: str):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                record_ai_latency(operation, (time.perf_counter() - started) * 1000)

        return wrapper

    return decorator


def prometheus_text() -> str:
    lines = [
        "# HELP ats_http_requests_total Total HTTP requests.",
        "# TYPE ats_http_requests_total counter",
    ]
    for (method, path, status), count in REQUEST_COUNT.items():
        lines.append(f'ats_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')

    lines.extend(
        [
            "# HELP ats_http_request_latency_ms_avg Average request latency in milliseconds.",
            "# TYPE ats_http_request_latency_ms_avg gauge",
        ]
    )
    for (method, path), values in REQUEST_LATENCY.items():
        if values:
            lines.append(f'ats_http_request_latency_ms_avg{{method="{method}",path="{path}"}} {sum(values) / len(values):.2f}')

    lines.extend(
        [
            "# HELP ats_ai_latency_ms_avg Average AI operation latency in milliseconds.",
            "# TYPE ats_ai_latency_ms_avg gauge",
        ]
    )
    for operation, values in AI_LATENCY.items():
        if values:
            lines.append(f'ats_ai_latency_ms_avg{{operation="{operation}"}} {sum(values) / len(values):.2f}')
    return "\n".join(lines) + "\n"
