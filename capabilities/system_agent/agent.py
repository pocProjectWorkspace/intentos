"""
IntentOS system_agent — System information capability

Actions: get_current_date
"""

from __future__ import annotations

import time
from datetime import datetime


def _meta(
    files_affected: int = 0,
    bytes_affected: int = 0,
    duration_ms: int = 0,
    paths_accessed: list[str] | None = None,
) -> dict:
    return {
        "files_affected": files_affected,
        "bytes_affected": bytes_affected,
        "duration_ms": duration_ms,
        "paths_accessed": paths_accessed or [],
    }


def _error(code: str, message: str) -> dict:
    return {
        "status": "error",
        "error": {"code": code, "message": message},
        "metadata": _meta(),
    }


def _get_current_date(params: dict, context: dict) -> dict:
    """Return the current date in the requested format."""
    t0 = time.monotonic()
    fmt = params.get("format", "YYYY-MM-DD")

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would return today's date in {fmt} format",
            "result": {"preview": f"Current date in {fmt}"},
            "metadata": _meta(),
        }

    now = datetime.now()

    # Translate common format tokens to Python strftime
    py_fmt = (
        fmt.replace("YYYY", "%Y")
        .replace("YY", "%y")
        .replace("MM", "%m")
        .replace("DD", "%d")
        .replace("HH", "%H")
        .replace("mm", "%M")
        .replace("ss", "%S")
    )

    try:
        formatted = now.strftime(py_fmt)
    except ValueError:
        formatted = now.strftime("%Y-%m-%d")

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Retrieved current date: {formatted}",
        "result": formatted,
        "metadata": _meta(duration_ms=elapsed),
    }


_ACTIONS = {
    "get_current_date": _get_current_date,
}


def run(input: dict) -> dict:
    action = input.get("action")
    params = input.get("params", {})
    context = input.get("context", {})

    handler = _ACTIONS.get(action)
    if handler is None:
        return _error("UNKNOWN_ACTION", f"I don't know how to do '{action}'")

    return handler(params, context)
