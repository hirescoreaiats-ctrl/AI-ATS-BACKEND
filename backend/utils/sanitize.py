import html


def sanitize_text(value: str | None, max_length: int = 5000) -> str:
    clean = html.escape((value or "").strip(), quote=True)
    return clean[:max_length]
