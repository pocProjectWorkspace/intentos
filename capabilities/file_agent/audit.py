"""
IntentOS — Audit logging

Two entry types:
  - log_step(): per-primitive step entries (used by file_agent planner)
  - log_task(): per-task summary entries (used by the Intent Kernel)

Appends structured JSONL to ~/.intentos/logs/audit.jsonl.
Never crashes the caller — silently catches all write errors.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

_LOG_DIR = Path.home() / ".intentos" / "logs"
_LOG_FILE = _LOG_DIR / "audit.jsonl"

# Truncation limits for sanitization
_MAX_STRING_LEN = 500
_MAX_LIST_LEN = 20


def _sanitize(value):
    """Truncate oversized strings and lists to keep log entries reasonable."""
    if isinstance(value, str) and len(value) > _MAX_STRING_LEN:
        return value[:_MAX_STRING_LEN] + f"... ({len(value)} chars total)"
    if isinstance(value, list) and len(value) > _MAX_LIST_LEN:
        return value[:_MAX_LIST_LEN] + [f"... ({len(value)} items total)"]
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    return value


def log_step(
    task_id: str,
    step_index: int,
    tool: str,
    params: dict,
    result_status: str,
    description: str = "",
) -> None:
    """Append one audit entry. Never raises."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "task_id": task_id,
            "step": step_index,
            "tool": tool,
            "params": _sanitize(params),
            "result_status": result_status,
            "description": description,
        }

        with open(_LOG_FILE, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        pass  # Never crash the caller


def log_task(
    raw_input: str,
    intent: str,
    agents_used: list[str],
    files_affected: int,
    result: str,
    duration_ms: int,
    cancelled: bool = False,
) -> None:
    """Append one task-level audit entry. Never raises."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "raw_input": raw_input,
            "intent": intent,
            "agents_used": agents_used,
            "files_affected": files_affected,
            "result": result,
            "duration_ms": duration_ms,
            "cancelled": cancelled,
        }

        with open(_LOG_FILE, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        pass  # Never crash the caller
