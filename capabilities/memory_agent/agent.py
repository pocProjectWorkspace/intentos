"""
IntentOS memory_agent — Persistent user context across sessions

Actions: remember, recall, forget, list_memories, get_context, clear_all

Memories are stored in {workspace}/memory.json and survive agent restarts.
Each memory has a key, value, and category (preference / fact / context).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Valid categories
# ---------------------------------------------------------------------------
VALID_CATEGORIES = {"preference", "fact", "context"}

# ---------------------------------------------------------------------------
# Module-level store cache (reset between tests via _store = None)
# ---------------------------------------------------------------------------
_store: dict | None = None


# ---------------------------------------------------------------------------
# Metadata helpers (ACP standard)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _memory_path(context: dict) -> str:
    workspace = context.get("workspace", ".")
    return os.path.join(workspace, "memory.json")


def _load(context: dict) -> dict:
    global _store
    if _store is not None:
        return _store
    fpath = _memory_path(context)
    if os.path.isfile(fpath):
        with open(fpath, "r") as f:
            _store = json.load(f)
    else:
        _store = {}
    return _store


def _save(context: dict) -> None:
    fpath = _memory_path(context)
    with open(fpath, "w") as f:
        json.dump(_store, f, indent=2)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _remember(params: dict, context: dict) -> dict:
    t0 = time.monotonic()
    key = params.get("key")
    value = params.get("value")
    category = params.get("category", "fact")

    if not key or value is None:
        return _error("INVALID_PARAMS", "Both 'key' and 'value' are required")

    if category not in VALID_CATEGORIES:
        return _error("INVALID_CATEGORY", f"Category must be one of {sorted(VALID_CATEGORIES)}")

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would remember '{key}' = '{value}' (category: {category})",
            "result": {"preview": f"Store {key}={value}"},
            "metadata": _meta(),
        }

    store = _load(context)
    store[key] = {"key": key, "value": value, "category": category}
    _save(context)

    elapsed = int((time.monotonic() - t0) * 1000)
    fpath = _memory_path(context)
    return {
        "status": "success",
        "action_performed": f"Remembered '{key}' = '{value}' (category: {category})",
        "result": {"key": key, "value": value, "category": category},
        "metadata": _meta(files_affected=1, duration_ms=elapsed, paths_accessed=[fpath]),
    }


def _recall(params: dict, context: dict) -> dict:
    t0 = time.monotonic()
    key = params.get("key")
    query = params.get("query")

    if not key and not query:
        return _error("INVALID_PARAMS", "Either 'key' or 'query' is required")

    if context.get("dry_run"):
        target = key or query
        return {
            "status": "success",
            "action_performed": f"Would recall memories matching '{target}'",
            "result": {"preview": f"Search for {target}"},
            "metadata": _meta(),
        }

    store = _load(context)
    fpath = _memory_path(context)

    # Exact key lookup
    if key:
        entry = store.get(key)
        if entry is None:
            return _error("NOT_FOUND", f"No memory found for key '{key}'")
        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "status": "success",
            "action_performed": f"Recalled memory for '{key}'",
            "result": entry,
            "metadata": _meta(duration_ms=elapsed, paths_accessed=[fpath]),
        }

    # Fuzzy search by query
    query_words = set(query.lower().replace("_", " ").split())
    matches = []
    for k, entry in store.items():
        # Build searchable text from key and value
        searchable = f"{k} {entry.get('value', '')}".lower().replace("_", " ")
        searchable_words = set(searchable.split())
        # Score = number of query words found in searchable text
        overlap = sum(1 for qw in query_words if any(qw in sw for sw in searchable_words))
        if overlap > 0:
            matches.append((overlap, entry))

    matches.sort(key=lambda x: x[0], reverse=True)
    results = [m[1] for m in matches]

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Searched memories for '{query}' — {len(results)} match(es)",
        "result": results,
        "metadata": _meta(duration_ms=elapsed, paths_accessed=[fpath]),
    }


def _forget(params: dict, context: dict) -> dict:
    t0 = time.monotonic()
    key = params.get("key")

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would forget memory '{key}'",
            "result": {"preview": f"Remove {key}"},
            "metadata": _meta(),
        }

    store = _load(context)
    removed = store.pop(key, None)
    _save(context)

    elapsed = int((time.monotonic() - t0) * 1000)
    fpath = _memory_path(context)
    action_msg = f"Forgot memory '{key}'" if removed else f"No memory '{key}' to forget (no-op)"
    return {
        "status": "success",
        "action_performed": action_msg,
        "result": {"key": key, "removed": removed is not None},
        "metadata": _meta(files_affected=1 if removed else 0, duration_ms=elapsed, paths_accessed=[fpath]),
    }


def _list_memories(params: dict, context: dict) -> dict:
    t0 = time.monotonic()
    category = params.get("category")

    if context.get("dry_run"):
        desc = "Would list all memories"
        if category:
            desc += f" in category '{category}'"
        return {
            "status": "success",
            "action_performed": desc,
            "result": {"preview": desc},
            "metadata": _meta(),
        }

    store = _load(context)
    entries = list(store.values())
    if category:
        entries = [e for e in entries if e.get("category") == category]

    elapsed = int((time.monotonic() - t0) * 1000)
    fpath = _memory_path(context)
    return {
        "status": "success",
        "action_performed": f"Listed {len(entries)} memories" + (f" (category: {category})" if category else ""),
        "result": entries,
        "metadata": _meta(duration_ms=elapsed, paths_accessed=[fpath]),
    }


def _get_context(params: dict, context: dict) -> dict:
    t0 = time.monotonic()

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": "Would return full user context summary",
            "result": {"preview": "User context summary"},
            "metadata": _meta(),
        }

    store = _load(context)
    entries = list(store.values())

    preferences = [e for e in entries if e.get("category") == "preference"]
    facts = [e for e in entries if e.get("category") == "fact"]
    ctx_items = [e for e in entries if e.get("category") == "context"]

    elapsed = int((time.monotonic() - t0) * 1000)
    fpath = _memory_path(context)
    return {
        "status": "success",
        "action_performed": "Retrieved full user context summary",
        "result": {
            "preferences": preferences,
            "facts": facts,
            "context": ctx_items,
            "total_memories": len(entries),
        },
        "metadata": _meta(duration_ms=elapsed, paths_accessed=[fpath]),
    }


def _clear_all(params: dict, context: dict) -> dict:
    global _store
    t0 = time.monotonic()

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": "Would clear all memories (requires confirmation)",
            "result": {"preview": "Clear all memories"},
            "metadata": _meta(),
        }

    # Confirmation-required pattern
    if not params.get("confirmed"):
        store = _load(context)
        count = len(store)
        return {
            "status": "confirmation_required",
            "confirmation_message": f"This will permanently clear all {count} memories. Confirm by setting confirmed=true.",
            "metadata": _meta(),
        }

    store = _load(context)
    count = len(store)
    _store = {}
    _save(context)

    elapsed = int((time.monotonic() - t0) * 1000)
    fpath = _memory_path(context)
    return {
        "status": "success",
        "action_performed": f"Cleared all {count} memories",
        "result": {"cleared": count},
        "metadata": _meta(files_affected=1, duration_ms=elapsed, paths_accessed=[fpath]),
    }


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

_ACTIONS = {
    "remember": _remember,
    "recall": _recall,
    "forget": _forget,
    "list_memories": _list_memories,
    "get_context": _get_context,
    "clear_all": _clear_all,
}


# ---------------------------------------------------------------------------
# Entry point (ACP compliant)
# ---------------------------------------------------------------------------

def run(input: dict) -> dict:
    action = input.get("action")
    params = input.get("params", {})
    context = input.get("context", {})

    handler = _ACTIONS.get(action)
    if handler is None:
        return _error("UNKNOWN_ACTION", f"I don't know how to do '{action}'")

    return handler(params, context)
