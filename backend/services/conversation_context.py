from __future__ import annotations

from typing import Any


CONTEXT_FIELDS = {
    "current_screen",
    "current_route",
    "active_filters",
    "job_id",
    "current_job_id",
    "job_title",
    "current_job_title",
    "candidate_ids",
    "candidate_id",
    "selected_candidate_ids",
    "candidate_name",
    "stage",
    "limit",
    "date_time",
    "meeting_url",
    "selected_items",
}
MAX_HISTORY_MESSAGES = 8
MAX_HISTORY_CONTENT = 500


def build_conversation_context(current_context: dict[str, Any] | None, history: list[dict] | None) -> dict[str, Any]:
    """Return bounded ATS state only; arbitrary client keys never enter the planner prompt."""
    source = current_context if isinstance(current_context, dict) else {}
    context = {key: source[key] for key in CONTEXT_FIELDS if key in source}

    for key in ("candidate_ids", "selected_candidate_ids"):
        values = context.get(key)
        if isinstance(values, list):
            context[key] = [str(value).strip() for value in values[:25] if str(value).strip()]
        elif values is not None:
            context.pop(key, None)

    if isinstance(context.get("selected_items"), list):
        context["selected_items"] = [str(value).strip() for value in context["selected_items"][:25] if str(value).strip()]
    elif context.get("selected_items") is not None:
        context.pop("selected_items", None)

    filters = context.get("active_filters")
    if isinstance(filters, dict):
        context["active_filters"] = {
            str(key)[:60]: str(value)[:160]
            for key, value in list(filters.items())[:12]
            if value is not None and str(value).strip()
        }
    elif filters is not None:
        context.pop("active_filters", None)

    if "limit" in context:
        try:
            context["limit"] = min(max(int(context["limit"]), 1), 100)
        except (TypeError, ValueError):
            context.pop("limit", None)

    compact_history = []
    for item in (history or [])[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user").lower()
        if role not in {"user", "assistant"}:
            continue
        content = " ".join(str(item.get("content") or "").split())[:MAX_HISTORY_CONTENT]
        if content:
            compact_history.append({"role": role, "content": content})
    context["conversation_history"] = compact_history
    return context
