"""
IntentOS file_agent — LLM Planner

The core of the redesign. Two functions:
  - generate_plan(): sends goal + context to Claude, returns a plan of primitives
  - execute_plan(): runs the plan step-by-step with confirmation/dry_run logic

The agent never needs new actions added — it grows through LLM reasoning.
"""

from __future__ import annotations

import json
import re

from .primitives import PRIMITIVES, _error, _meta
from .schemas import format_schemas_for_prompt
from . import audit


# ---------------------------------------------------------------------------
# Planning prompt
# ---------------------------------------------------------------------------

_PLANNER_SYSTEM = """\
You are a file-operations planner inside IntentOS. Given a user's goal and \
the current file context, decompose the goal into a sequence of primitive \
filesystem operations.

You have these tools available:

{tool_docs}

Rules:
1. Only use tools listed above. Do not invent new tool names.
2. Use absolute paths. Expand ~ to the user's home directory if provided in context.
3. For organizing files: create folders first, then move files into them.
4. Be efficient — don't create empty folders, don't move files that are already in the right place.
5. The "description" field should be plain English, e.g. "Create Images folder", "Move photo.jpg to Images/".
6. Do NOT include "confirmed" in params — confirmation is handled by the executor.

Respond with a raw JSON object only. No markdown. No code blocks. No explanation. \
Start your response with {{ and end with }}.

Use this exact schema:
{{"steps": [...], "summary": "one-line description of the plan"}}

Each step must be:
{{"tool": "<primitive_name>", "params": {{...}}, "description": "short human-readable description"}}

Example output for organizing 3 files by type in /home/user/Downloads:

{{"steps": [{{"tool": "create_folder", "params": {{"path": "/home/user/Downloads/Images"}}, "description": "Create Images folder"}}, {{"tool": "create_folder", "params": {{"path": "/home/user/Downloads/Documents"}}, "description": "Create Documents folder"}}, {{"tool": "move_file", "params": {{"path": "/home/user/Downloads/photo.jpg", "destination": "/home/user/Downloads/Images/photo.jpg"}}, "description": "Move photo.jpg to Images/"}}, {{"tool": "move_file", "params": {{"path": "/home/user/Downloads/report.pdf", "destination": "/home/user/Downloads/Documents/report.pdf"}}, "description": "Move report.pdf to Documents/"}}, {{"tool": "move_file", "params": {{"path": "/home/user/Downloads/notes.txt", "destination": "/home/user/Downloads/Documents/notes.txt"}}, "description": "Move notes.txt to Documents/"}}], "summary": "Organized 3 files into 2 folders"}}
"""


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> str:
    """Strip markdown code fences and isolate the JSON object."""
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()
    # Find the outermost { ... } (plan is a dict)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return text[start : end + 1]
    return text


def _recover_truncated_json(raw: str) -> dict | None:
    """
    Attempt to recover a valid plan from a truncated JSON response.

    Finds the last complete step object (last '}' that closes a step before
    the truncation point), then closes the steps array and outer object.
    """
    # Find the start of the object
    obj_start = raw.find("{")
    if obj_start == -1:
        return None

    # Find the start of the steps array
    steps_start = raw.find('"steps"')
    if steps_start == -1:
        return None
    arr_start = raw.find("[", steps_start)
    if arr_start == -1:
        return None

    # Walk backwards from the end to find the last complete step object.
    # A complete step ends with }  possibly followed by , or whitespace.
    # We look for the pattern: "description": "..."}
    #
    # Strategy: find all } positions, try closing the array+object after each
    # one (from the end), and see if it parses.
    candidates = [m.end() for m in re.finditer(r"\}", raw)]
    for cut in reversed(candidates):
        # Must be past the array opening
        if cut <= arr_start + 1:
            continue
        fragment = raw[obj_start:cut]
        # Strip a trailing comma if present
        fragment = fragment.rstrip().rstrip(",")
        # Close the steps array and the outer object, inject a summary
        attempt = fragment + '], "summary": "partial plan (response was truncated)"}'
        try:
            plan = json.loads(attempt)
            if isinstance(plan, dict) and isinstance(plan.get("steps"), list) and len(plan["steps"]) > 0:
                return plan
        except json.JSONDecodeError:
            continue
    return None


def _parse_plan_json(raw: str, truncated: bool = False) -> dict | None:
    """Try to parse planner output as JSON. Returns dict or None."""
    # Fast path — already valid JSON
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fallback — strip fences / surrounding text
    cleaned = _extract_json(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Last resort for truncated responses — recover partial plan
    if truncated:
        return _recover_truncated_json(raw)
    return None


# ---------------------------------------------------------------------------
# generate_plan
# ---------------------------------------------------------------------------

def generate_plan(
    goal_action: str,
    goal_params: dict,
    context: dict,
    llm_client,
    file_context: list[dict] | None = None,
) -> dict:
    """
    Ask Claude to decompose a goal into primitive steps.

    Returns:
        {"steps": [...], "summary": "..."} on success
        {"status": "error", ...} on failure
    """
    if llm_client is None:
        return _error("NO_LLM_CLIENT", "LLM planning is not available — no API client in context")

    # Build the user message with goal and file context
    parts = [f"Goal action: {goal_action}"]
    if goal_params:
        parts.append(f"Parameters: {json.dumps(goal_params, default=str)}")

    if file_context:
        file_list = "\n".join(
            f"  - {f.get('name', '?')} ({f.get('size_bytes', '?')} bytes, modified {f.get('modified', '?')})"
            for f in file_context[:200]  # Cap at 200 files to avoid token overflow
        )
        parts.append(f"Files in the directory:\n{file_list}")

    home_dir = context.get("home", "")
    if home_dir:
        parts.append(f"User's home directory: {home_dir}")

    granted = context.get("granted_paths", [])
    if granted:
        parts.append(f"Granted paths: {', '.join(granted)}")

    user_message = "\n\n".join(parts)
    system_prompt = _PLANNER_SYSTEM.format(tool_docs=format_schemas_for_prompt())

    try:
        response = llm_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16384,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as e:
        return _error("LLM_ERROR", f"Could not generate plan: {type(e).__name__}")

    raw = response.content[0].text
    truncated = getattr(response, "stop_reason", None) == "max_tokens"

    if truncated:
        print(f"PLANNER WARNING: response truncated at max_tokens, attempting recovery...")

    # Parse the JSON response with fallback extraction
    plan = _parse_plan_json(raw, truncated=truncated)
    if plan is None:
        print(f"PLANNER RAW OUTPUT: {raw[:2000]}{'... (truncated)' if len(raw) > 2000 else ''}")
        return _error("PLAN_PARSE_ERROR", "The planner returned invalid JSON")

    # Validate plan structure
    if not isinstance(plan, dict) or "steps" not in plan:
        return _error("PLAN_INVALID", "The planner returned a plan without steps")

    steps = plan.get("steps", [])
    if not isinstance(steps, list) or len(steps) == 0:
        return _error("PLAN_EMPTY", "The planner returned an empty plan")

    # Validate every step uses a known primitive
    for i, step in enumerate(steps):
        tool_name = step.get("tool", "")
        if tool_name not in PRIMITIVES:
            return _error(
                "PLAN_UNKNOWN_TOOL",
                f"Step {i + 1} uses unknown tool '{tool_name}'",
            )

    return plan


# ---------------------------------------------------------------------------
# execute_plan
# ---------------------------------------------------------------------------

def execute_plan(plan: dict, context: dict) -> dict:
    """
    Execute a plan's steps sequentially.

    - dry_run: returns the plan as preview, no execution
    - delete_file: each delete pauses for individual confirmation (never batched)
    - Auto-confirms move_file/rename_file/copy_file within a plan
    - Stops on first error, returns partial success info
    """
    steps = plan.get("steps", [])
    summary = plan.get("summary", "")
    task_id = context.get("task_id", "unknown")

    # --- dry_run: return full plan without executing ---
    if context.get("dry_run"):
        preview = [
            {"step": i + 1, "tool": s.get("tool"), "description": s.get("description", "")}
            for i, s in enumerate(steps)
        ]
        return {
            "status": "success",
            "action_performed": f"Plan preview: {summary}" if summary else f"Plan with {len(steps)} step(s)",
            "result": {"plan": preview, "total_steps": len(steps)},
            "metadata": _meta(),
        }

    # --- Execute steps ---
    completed = []
    skipped_deletes = 0
    for i, step in enumerate(steps):
        tool_name = step.get("tool", "")
        params = step.get("params", {})
        description = step.get("description", "")

        fn = PRIMITIVES.get(tool_name)
        if fn is None:
            audit.log_step(task_id, i, tool_name, params, "error", f"Unknown tool: {tool_name}")
            return {
                "status": "error",
                "error": {"code": "UNKNOWN_TOOL", "message": f"Step {i + 1}: unknown tool '{tool_name}'"},
                "result": {"completed_steps": completed, "failed_step": i + 1},
                "metadata": _meta(files_affected=len(completed)),
            }

        # --- Per-delete confirmation (never batched) ---
        if tool_name == "delete_file":
            filepath = params.get("path", "unknown")
            filename = filepath.rsplit("/", 1)[-1] if "/" in filepath else filepath
            print(f"\n  \u26a0\ufe0f  About to delete: {filename}")
            print(f"      This cannot be undone.")
            try:
                confirm = input("      Confirm delete? (yes/no): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = "no"
            if confirm not in ("y", "yes"):
                print(f"      Skipped deletion of {filename}")
                skipped_deletes += 1
                audit.log_step(task_id, i, tool_name, params, "skipped", f"User declined: {description}")
                continue
            params = {**params, "confirmed": True}
        elif tool_name in ("move_file", "rename_file", "copy_file", "create_folder"):
            # Auto-confirm non-destructive actions within a plan
            params = {**params, "confirmed": True}

        try:
            result = fn(params, context)
        except Exception:
            audit.log_step(task_id, i, tool_name, params, "crash", description)
            return {
                "status": "error",
                "error": {"code": "STEP_CRASH", "message": f"Step {i + 1} ({tool_name}) crashed unexpectedly"},
                "result": {"completed_steps": completed, "failed_step": i + 1},
                "metadata": _meta(files_affected=len(completed)),
            }

        status = result.get("status", "error")
        audit.log_step(task_id, i, tool_name, params, status, description)

        if status == "error":
            err_msg = result.get("error", {}).get("message", "Unknown error")
            return {
                "status": "error",
                "error": {"code": "STEP_FAILED", "message": f"Step {i + 1} ({tool_name}): {err_msg}"},
                "result": {"completed_steps": completed, "failed_step": i + 1},
                "metadata": _meta(files_affected=len(completed)),
            }

        completed.append({
            "step": i + 1,
            "tool": tool_name,
            "description": description,
            "action_performed": result.get("action_performed", ""),
        })

    return {
        "status": "success",
        "action_performed": summary or f"Completed {len(completed)} step(s)",
        "result": {
            "completed_steps": completed,
            "total_steps": len(completed),
            "skipped_deletes": skipped_deletes,
        },
        "metadata": _meta(files_affected=len(completed)),
    }
