"""
IntentOS file_agent — Thin router (LLM Planner + Dumb Primitives)

If the action is a known primitive → execute it directly.
If the action is unknown → use the LLM planner to decompose it into primitives.

The agent never needs new actions added — it grows through LLM reasoning.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .primitives import PRIMITIVES, _error
from .planner import generate_plan, execute_plan
from . import audit

# Max files per LLM planning call.  Keeps output tokens under 16 384.
_BATCH_SIZE = 80

# ---------------------------------------------------------------------------
# Sensitive file patterns — files IntentOS will never touch automatically
# ---------------------------------------------------------------------------
SENSITIVE_PATTERNS = [
    r"(?i)secret",
    r"(?i)credential",
    r"(?i)password",
    r"(?i)token",
    r"(?i)accesskey",
    r"(?i)access_key",
    r"(?i)\.env$",
    r"(?i)\.env\.",
    r"(?i)\.pem$",
    r"(?i)\.p12$",
    r"(?i)\.key$",
    r"(?i)\.csv$.*(?i)(key|access)",   # .csv containing 'key' or 'access'
]

# Pre-compiled for performance
_SENSITIVE_RE = [re.compile(p) for p in SENSITIVE_PATTERNS]


def _check_sensitive_files(paths: list[str]) -> list[str]:
    """Return filenames that match any sensitive pattern."""
    flagged = []
    for path in paths:
        name = Path(path).name
        # Special case: .csv files — only flag if name contains 'key' or 'access'
        if name.lower().endswith(".csv"):
            if re.search(r"(?i)(key|access)", name):
                flagged.append(name)
            continue
        # General patterns (skip the csv-specific composite pattern)
        for pattern in _SENSITIVE_RE[:-1]:
            if pattern.search(name):
                flagged.append(name)
                break
    return list(dict.fromkeys(flagged))  # dedupe, preserve order


# ---------------------------------------------------------------------------
# Batched plan generation — split large file lists into manageable chunks
# ---------------------------------------------------------------------------

def _generate_batched_plan(
    action: str,
    params: dict,
    context: dict,
    llm_client,
    file_context: list[dict],
) -> dict:
    """
    Split file_context into batches, generate a plan per batch, and merge.

    create_folder steps are deduplicated across batches; move/rename/copy
    steps are concatenated in order.
    """
    all_steps: list[dict] = []
    seen_folders: set[str] = set()

    for batch_start in range(0, len(file_context), _BATCH_SIZE):
        batch = file_context[batch_start : batch_start + _BATCH_SIZE]
        batch_num = batch_start // _BATCH_SIZE + 1
        total_batches = (len(file_context) + _BATCH_SIZE - 1) // _BATCH_SIZE

        print(f"  Planning batch {batch_num}/{total_batches} ({len(batch)} files)...")

        plan = generate_plan(
            goal_action=action,
            goal_params=params,
            context=context,
            llm_client=llm_client,
            file_context=batch,
        )

        if plan.get("status") == "error":
            # If a batch fails but we already have steps, continue with what we have
            if all_steps:
                print(f"  Batch {batch_num} failed, continuing with {len(all_steps)} steps from previous batches")
                continue
            return plan

        for step in plan.get("steps", []):
            # Deduplicate create_folder steps across batches
            if step.get("tool") == "create_folder":
                folder_path = step.get("params", {}).get("path", "")
                if folder_path in seen_folders:
                    continue
                seen_folders.add(folder_path)
            all_steps.append(step)

    if not all_steps:
        return _error("PLAN_EMPTY", "Could not generate any plan steps")

    summary = f"Organized {len(file_context)} files ({len(seen_folders)} folders, {len(all_steps) - len(seen_folders)} moves)"
    return {"steps": all_steps, "summary": summary}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(input: dict) -> dict:
    action = input.get("action")
    params = input.get("params", {})
    context = input.get("context", {})

    # ---------------------------------------------------------------
    # Direct primitive path — fast, no LLM needed
    # ---------------------------------------------------------------
    if action in PRIMITIVES:
        task_id = context.get("task_id", "unknown")
        try:
            result = PRIMITIVES[action](params, context)
        except Exception:
            result = _error("AGENT_CRASH", "Something went wrong running that operation")
        audit.log_step(task_id, 0, action, params, result.get("status", "error"), f"Direct: {action}")
        return result

    # ---------------------------------------------------------------
    # LLM planning path — decompose unknown action into primitives
    # ---------------------------------------------------------------

    # Pre-fetch file listing if a directory param exists
    file_context = None
    directory = params.get("path") or params.get("directory")
    if directory:
        listing = PRIMITIVES["list_files"]({"path": directory}, context)
        if listing.get("status") == "success" and isinstance(listing.get("result"), list):
            file_context = listing["result"]

    # --- Sensitive file check — block before anything else ---
    if file_context:
        all_paths = [f.get("path", "") for f in file_context]
        flagged = _check_sensitive_files(all_paths)
        if flagged:
            return {
                "status": "error",
                "error": {
                    "code": "SENSITIVE_FILES_DETECTED",
                    "message": "Sensitive files detected — task blocked for safety",
                },
                "sensitive_files": flagged,
                "metadata": {"files_affected": 0, "bytes_affected": 0, "duration_ms": 0, "paths_accessed": []},
            }

    llm_client = context.get("llm_client")
    if llm_client is None:
        return _error(
            "UNKNOWN_ACTION",
            f"I don't know how to do '{action}' and LLM planning is not available",
        )

    # Add home dir to context for the planner
    plan_context = {**context, "home": os.path.expanduser("~")}

    # Generate the plan — batch if file list is large
    if file_context and len(file_context) > _BATCH_SIZE:
        print(f"  {len(file_context)} files — splitting into batches of {_BATCH_SIZE}...")
        plan = _generate_batched_plan(
            action=action,
            params=params,
            context=plan_context,
            llm_client=llm_client,
            file_context=file_context,
        )
    else:
        plan = generate_plan(
            goal_action=action,
            goal_params=params,
            context=plan_context,
            llm_client=llm_client,
            file_context=file_context,
        )

    # If generate_plan returned an error, pass it through
    if plan.get("status") == "error":
        return plan

    # Handle confirmed re-execution of a plan with deletes
    if params.get("confirmed") or params.get("_plan_confirmed"):
        plan_context = {**plan_context, "_plan_confirmed": True}

    # Execute the plan
    return execute_plan(plan, plan_context)
