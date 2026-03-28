"""
IntentOS Intent Kernel (Phase 1 — CLI + Claude API)

The brain of IntentOS. Receives raw natural language, interprets the user's
goal, decomposes it into sub-tasks, routes each sub-task to the appropriate
agent, and returns the result.

Phase 1 features:
  - Dry-run preview before destructive/large operations
  - Sensitive file detection
  - Per-delete confirmation (in planner)
  - Task-level audit logging
  - Clean result display with --verbose
  - Workspace auto-setup on first run

Architecture ref: /capabilities/ARCHITECTURE.md — Layer 3 (Intent Kernel)
"""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
import time
import uuid

# Ensure project root is on sys.path so capabilities.* imports work
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import anthropic

from core.security.credential_provider import CredentialProvider, get_api_key

# ---------------------------------------------------------------------------
# CLI flags
# ---------------------------------------------------------------------------

VERBOSE = "--verbose" in sys.argv

# ---------------------------------------------------------------------------
# System prompt — the most critical piece of engineering in the entire OS
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the IntentOS Intent Kernel. Your sole job is to receive a natural \
language instruction from the user and return a structured intent object as JSON.

You must respond with ONLY valid JSON — no markdown, no explanation, no wrapping.

The intent object schema:

{
  "raw_input": "<the exact instruction the user typed>",
  "intent": "<category.action in dot notation, e.g. file.rename, image.background_remove, browser.search>",
  "subtasks": [
    {
      "id": "1",
      "agent": "<which agent handles this step, e.g. file_agent, browser_agent, image_agent, media_agent, system_agent, document_agent>",
      "action": "<the specific action the agent should perform>",
      "params": { "<action-specific parameters>" }
    }
  ]
}

Available agents and their actions:

file_agent:
  Primitives (use these for simple, direct tasks):
  - list_files: params {path/directory, extension/type, recursive}
  - find_files: params {path/directory, pattern, extension/type, modified_after, modified_before, size_gt, size_lt}
  - rename_file: params {path/source, new_name/destination}
  - move_file: params {path/source, destination}
  - copy_file: params {path/source, destination}
  - create_folder: params {path}
  - delete_file: params {path}
  - read_file: params {path}
  - get_metadata: params {path}
  - get_disk_usage: params {path/directory}

  Compound actions (for complex file tasks, use any descriptive action name — \
file_agent will plan internally using the primitives above):
  Examples: organize_by_type, bulk_rename, cleanup_old_files, deduplicate, \
sort_by_date, flatten_folders, archive_large_files.
  Just provide the action name and relevant params (e.g. path/directory). \
The agent will figure out the steps.

system_agent:
  - get_current_date: params {format} (default "YYYY-MM-DD")

browser_agent:
  - search_web: params {query, max_results} — search DuckDuckGo for information
  - fetch_page: params {url} — fetch and return a web page's text content
  - extract_data: params {url, description, content} — fetch a page and extract \
specific data using AI. "description" says what to extract. Optionally pass \
"content" directly instead of a URL (e.g. from a previous search_web result).

document_agent:
  - create_document: params {filename, content, title, save_path} — create a new \
.docx document. Default save location is ~/.intentos/workspace/outputs/. \
"content" is the text body. "title" is an optional heading.
  - append_content: params {path, content, heading} — add content to an existing \
.docx document. "heading" is an optional section heading.
  - read_document: params {path} — read a .docx or .pdf file and return its plain \
text content.
  - convert_document: params {path, format} — convert a document to another format \
(e.g. docx→txt, pdf→txt). Output saved to workspace/outputs/.
  - save_document: params {path, destination, filename} — save or copy a document \
to a new location.

Rules:
1. "raw_input" is always the exact text the user typed, unmodified.
2. "intent" is a short dot-notation label: <category>.<action>. Categories include: \
file, browser, image, media, system, document, utility, memory.
3. "subtasks" is an ordered array. Each subtask has an "id" (string, sequential from "1"), \
an "agent" (one of the known IntentOS agents), an "action" (verb describing what the agent does), \
and "params" (a dict of parameters for that action).
4. For multi-step tasks, decompose into the minimal ordered subtasks. If step 2 depends on \
step 1's output, reference it as "{{1.result}}" in the params.
5. If the instruction is ambiguous, pick the most likely interpretation. Do not ask questions.
6. Always return valid JSON. Never return markdown, code fences, or explanation text.
7. Use ~ for home directory paths (e.g. ~/Downloads, ~/Documents).
8. For file listing/searching tasks that feed into rename/move, always list files first \
as a separate subtask so the result can be passed to the next step.
"""

MODEL = "claude-sonnet-4-20250514"

# ---------------------------------------------------------------------------
# Agent registry — maps agent names to their module paths
# ---------------------------------------------------------------------------

AGENT_REGISTRY: dict[str, str] = {
    "file_agent": "capabilities.file_agent.agent",
    "system_agent": "capabilities.system_agent.agent",
    "browser_agent": "capabilities.browser_agent.agent",
    "document_agent": "capabilities.document_agent.agent",
}

# Future agents — not yet implemented, shown in helpful error messages
_FUTURE_AGENTS: dict[str, tuple[str, str]] = {
    "image_agent": ("Phase 3", "image processing and manipulation"),
    "media_agent": ("Phase 3", "audio and video processing"),
    "memory_agent": ("Phase 4", "persistent context and preference storage"),
}


def _load_agent(agent_name: str):
    """Dynamically import and return an agent module."""
    module_path = AGENT_REGISTRY.get(agent_name)
    if module_path is None:
        return None
    return importlib.import_module(module_path)


# ---------------------------------------------------------------------------
# Result reference resolution — replace {{n.result}} with actual values
# ---------------------------------------------------------------------------

_REF_PATTERN = re.compile(r"\{\{(\d+)\.result\}\}")


def _resolve_refs(obj, results: dict):
    """Recursively replace {{n.result}} references in params with actual results."""
    if isinstance(obj, str):
        match = _REF_PATTERN.fullmatch(obj)
        if match:
            ref_id = match.group(1)
            return results.get(ref_id, obj)
        def _replacer(m):
            ref_id = m.group(1)
            val = results.get(ref_id)
            return str(val) if val is not None else m.group(0)
        return _REF_PATTERN.sub(_replacer, obj)
    elif isinstance(obj, dict):
        return {k: _resolve_refs(v, results) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_refs(item, results) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# Workspace setup — first-run initialization
# ---------------------------------------------------------------------------

def _ensure_workspace() -> bool:
    """
    Ensure ~/.intentos/ exists with full directory structure.
    Returns True if created for the first time.
    """
    home = os.path.expanduser("~")
    base = os.path.join(home, ".intentos")
    first_run = not os.path.exists(base)

    dirs = [
        os.path.join(base, "logs"),
        os.path.join(base, "workspace", "outputs"),
        os.path.join(base, "workspace", "temp"),
        os.path.join(base, "rag"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

    # Create empty audit log if it doesn't exist
    audit_file = os.path.join(base, "logs", "audit.jsonl")
    if not os.path.exists(audit_file):
        open(audit_file, "a").close()

    return first_run


# ---------------------------------------------------------------------------
# Execution context builder
# ---------------------------------------------------------------------------

def _build_context(llm_client=None) -> dict:
    """Build the context dict that gets injected into every agent call."""
    home = os.path.expanduser("~")
    workspace = os.path.join(home, ".intentos", "workspace")

    ctx = {
        "user": os.getenv("USER", "unknown"),
        "workspace": workspace,
        "granted_paths": [
            os.path.join(home, "Documents"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Desktop"),
            workspace,
        ],
        "task_id": str(uuid.uuid4()),
        "dry_run": False,
    }
    if llm_client is not None:
        ctx["llm_client"] = llm_client
    return ctx


# ---------------------------------------------------------------------------
# Dry-run preview — show what will happen before executing
# ---------------------------------------------------------------------------

# Actions that are always safe (no preview needed even at high file counts)
_SAFE_ACTIONS = {"list_files", "find_files", "get_disk_usage", "read_file", "get_metadata"}

# Actions that are destructive and always need preview
_DESTRUCTIVE_ACTIONS = {"move_file", "rename_file", "delete_file"}


def _needs_preview(subtasks: list[dict]) -> bool:
    """Decide whether this set of subtasks should trigger a dry-run preview."""
    total_ops = 0
    has_destructive = False

    for st in subtasks:
        action = st.get("action", "")
        if action in _SAFE_ACTIONS:
            continue
        total_ops += 1
        if action in _DESTRUCTIVE_ACTIONS:
            has_destructive = True
        # Compound actions (not in SAFE_ACTIONS, not a known primitive) are
        # always treated as potentially large
        if action not in _SAFE_ACTIONS and action not in _DESTRUCTIVE_ACTIONS:
            has_destructive = True

    return total_ops >= 5 or has_destructive


def _show_preview(intent: dict, execution_log: list[dict]) -> bool:
    """
    Show a preview box and ask user to proceed.
    Returns True if user confirms, False if cancelled.
    """
    intent_label = intent.get("intent", "?")

    # Count planned operations from the dry-run results
    folders_created = 0
    files_moved = 0
    files_deleted = 0
    files_copied = 0
    files_renamed = 0
    other_ops = 0

    for entry in execution_log:
        output = entry.get("output", {})
        result = output.get("result", {})

        # Plan results from compound actions
        if isinstance(result, dict) and "plan" in result:
            for step in result.get("plan", []):
                tool = step.get("tool", "")
                if tool == "create_folder":
                    folders_created += 1
                elif tool == "move_file":
                    files_moved += 1
                elif tool == "delete_file":
                    files_deleted += 1
                elif tool == "copy_file":
                    files_copied += 1
                elif tool == "rename_file":
                    files_renamed += 1
                else:
                    other_ops += 1
        elif isinstance(result, dict) and "plan" not in result:
            # Single-action preview
            action = entry.get("action", "")
            if action in ("move_file", "rename_file", "delete_file", "copy_file"):
                if action == "move_file":
                    files_moved += 1
                elif action == "rename_file":
                    files_renamed += 1
                elif action == "delete_file":
                    files_deleted += 1
                elif action == "copy_file":
                    files_copied += 1

    # Build the summary lines
    lines = []
    if folders_created:
        lines.append(f"  Folders:  {folders_created} will be created")
    if files_moved:
        lines.append(f"  Files:    {files_moved} will be moved")
    if files_renamed:
        lines.append(f"  Renamed:  {files_renamed} will be renamed")
    if files_copied:
        lines.append(f"  Copied:   {files_copied} will be copied")
    if files_deleted:
        lines.append(f"  Deletes:  {files_deleted}")
    else:
        lines.append(f"  Deletes:  0")
    if other_ops:
        lines.append(f"  Other:    {other_ops} operations")

    # Display the preview box
    width = 52
    print()
    print("\u250c" + "\u2500" * width + "\u2510")
    print("\u2502" + "  PREVIEW -- nothing has happened yet".ljust(width) + "\u2502")
    print("\u2502" + "".ljust(width) + "\u2502")
    print("\u2502" + f"  Intent:   {intent_label}".ljust(width) + "\u2502")
    for line in lines:
        print("\u2502" + line.ljust(width) + "\u2502")
    print("\u2502" + "".ljust(width) + "\u2502")
    print("\u2502" + "  Proceed? (yes/no)".ljust(width) + "\u2502")
    print("\u2514" + "\u2500" * width + "\u2518")

    try:
        answer = input("\n  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "no"

    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# Subtask executor
# ---------------------------------------------------------------------------

def execute_subtasks(subtasks: list[dict], context: dict) -> list[dict]:
    """Execute subtasks sequentially, resolving {{n.result}} references."""
    results: dict[str, any] = {}
    execution_log: list[dict] = []

    for subtask in subtasks:
        sid = subtask.get("id", "?")
        agent_name = subtask.get("agent", "")
        action = subtask.get("action", "")
        params = subtask.get("params", {})

        # Resolve references from previous subtask results
        params = _resolve_refs(params, results)

        # Load agent
        agent_module = _load_agent(agent_name)
        if agent_module is None:
            entry = {
                "subtask_id": sid,
                "agent": agent_name,
                "action": action,
                "status": "error",
                "output": {
                    "status": "error",
                    "error": {
                        "code": "AGENT_NOT_AVAILABLE",
                        "message": f"Agent '{agent_name}' is not available yet",
                    },
                    "metadata": {"files_affected": 0, "bytes_affected": 0, "duration_ms": 0, "paths_accessed": []},
                },
            }
            execution_log.append(entry)

            # Print a helpful, specific warning
            print()
            print(f"  \u26a0\ufe0f  Agent not available: {agent_name}")
            print()
            if agent_name in _FUTURE_AGENTS:
                phase, desc = _FUTURE_AGENTS[agent_name]
                print(f"  This agent ({desc}) is planned for {phase}.")
            else:
                print("  This task needs a capability that hasn't been built yet.")
            print()
            print("  Planned agents:")
            for name, (phase, desc) in _FUTURE_AGENTS.items():
                print(f"  \u2192 {name:<18s} {phase} — {desc}")
            print()
            print("  Available now: file_agent, browser_agent, document_agent, system_agent")
            print()
            continue

        # Build agent input
        agent_input = {
            "action": action,
            "params": params,
            "context": context,
        }

        # Execute
        try:
            output = agent_module.run(agent_input)
        except Exception:
            output = {
                "status": "error",
                "error": {"code": "AGENT_CRASH", "message": "Something went wrong running that step"},
                "metadata": {"files_affected": 0, "bytes_affected": 0, "duration_ms": 0, "paths_accessed": []},
            }

        status = output.get("status", "error")
        result_value = output.get("result")
        action_performed = output.get("action_performed", "")

        # Store result for downstream references
        results[sid] = result_value

        entry = {
            "subtask_id": sid,
            "agent": agent_name,
            "action": action,
            "status": status,
            "output": output,
        }
        execution_log.append(entry)

        # --- Handle sensitive file block ---
        if status == "error" and output.get("error", {}).get("code") == "SENSITIVE_FILES_DETECTED":
            flagged = output.get("sensitive_files", [])
            print()
            print("  \U0001f512 Sensitive files detected")
            print()
            print("  I found files that may contain credentials or secrets:")
            for f in flagged:
                print(f"  - {f}")
            print()
            print("  IntentOS will not touch these files automatically.")
            print("  Please move them manually to a secure location")
            print("  and consider rotating the credentials.")
            print()
            break

        # Print progress
        if status == "success":
            if VERBOSE:
                print(f"  [{sid}] {agent_name}.{action} -- {action_performed}")
        elif status == "confirmation_required":
            prompt = output.get("confirmation_prompt", "Confirmation needed")
            print(f"  [{sid}] {agent_name}.{action} -- needs confirmation: {prompt}")

            try:
                confirm = input("       Confirm? (y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = "no"

            if confirm in ("y", "yes"):
                confirmed_input = {
                    "action": action,
                    "params": {**params, "confirmed": True},
                    "context": context,
                }
                try:
                    output = agent_module.run(confirmed_input)
                except Exception:
                    output = {
                        "status": "error",
                        "error": {"code": "AGENT_CRASH", "message": "Something went wrong running that step"},
                        "metadata": {"files_affected": 0, "bytes_affected": 0, "duration_ms": 0, "paths_accessed": []},
                    }

                results[sid] = output.get("result")
                entry["output"] = output
                entry["status"] = output.get("status", "error")
                ap = output.get("action_performed", "")
                if output.get("status") == "success":
                    print(f"       Done -- {ap}")
                else:
                    err = output.get("error", {}).get("message", "Unknown error")
                    print(f"       Failed -- {err}")
            else:
                print("       Skipped.")
        elif status == "error":
            err = output.get("error", {}).get("message", "Unknown error")
            print(f"  [{sid}] {agent_name}.{action} -- error: {err}")
            break

    return execution_log


# ---------------------------------------------------------------------------
# Claude API interaction
# ---------------------------------------------------------------------------

def create_client(credential_provider: CredentialProvider | None = None) -> anthropic.Anthropic:
    """Create an Anthropic client using the secure credential provider."""
    api_key = get_api_key(credential_provider)
    return anthropic.Anthropic(api_key=api_key)


def parse_intent(client: anthropic.Anthropic, user_input: str) -> dict | None:
    """Send a natural language instruction to Claude and return a structured intent object."""
    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_input}],
        )
    except anthropic.AuthenticationError:
        print("\nError: Invalid API key. Your stored key may be incorrect.")
        print("Run IntentOS again to enter a new key, or set ANTHROPIC_API_KEY in your environment.")
        return None
    except anthropic.APIConnectionError:
        print("\nError: Could not connect to the Anthropic API. Check your internet connection.")
        return None
    except anthropic.APIError as e:
        print(f"\nAPI error: {e.message}")
        return None

    raw_text = message.content[0].text

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "raw_input": user_input,
            "intent": "parse_error",
            "subtasks": [],
            "_raw_response": raw_text,
        }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_intent(intent: dict) -> None:
    """Pretty-print a structured intent object to the terminal."""
    print("\n" + "-" * 60)
    print(f"  Intent: {intent.get('intent', '?')}")
    print("-" * 60)
    subtasks = intent.get("subtasks", [])
    for st in subtasks:
        sid = st.get("id", "?")
        agent = st.get("agent", "?")
        action = st.get("action", "?")
        print(f"  [{sid}] {agent}.{action}")
    print("-" * 60)


def _count_results(execution_log: list[dict]) -> dict:
    """Extract counts from execution log for the clean summary."""
    counts = {
        "created": 0,
        "moved": 0,
        "renamed": 0,
        "copied": 0,
        "deleted": 0,
        "listed": 0,
        "errors": 0,
        "total_steps": 0,
        "files_affected": 0,
    }

    for entry in execution_log:
        output = entry.get("output", {})
        status = entry.get("status", "error")
        result = output.get("result", {})

        if status == "error":
            counts["errors"] += 1
            continue

        # Compound plan results
        if isinstance(result, dict) and "completed_steps" in result:
            for step in result.get("completed_steps", []):
                tool = step.get("tool", "")
                counts["total_steps"] += 1
                if tool == "create_folder":
                    counts["created"] += 1
                elif tool == "move_file":
                    counts["moved"] += 1
                elif tool == "rename_file":
                    counts["renamed"] += 1
                elif tool == "copy_file":
                    counts["copied"] += 1
                elif tool == "delete_file":
                    counts["deleted"] += 1
                else:
                    counts["files_affected"] += 1
        # File listing results
        elif isinstance(result, list):
            counts["listed"] += len(result)
            counts["total_steps"] += 1
        # Single-action results
        elif isinstance(result, dict):
            counts["total_steps"] += 1
            action = entry.get("action", "")
            meta = output.get("metadata", {})
            counts["files_affected"] += meta.get("files_affected", 0)

    return counts


def print_result_summary(intent: dict, execution_log: list[dict], duration_ms: int) -> None:
    """Print a clean summary of what happened."""
    if not execution_log:
        return

    last = execution_log[-1]
    output = last.get("output", {})
    status = last.get("status", "error")
    intent_label = intent.get("intent", "?")

    print("\n" + "=" * 60)

    if status == "success":
        counts = _count_results(execution_log)
        secs = duration_ms / 1000

        print("  \u2705 DONE")
        print("=" * 60)
        print(f"  Intent:    {intent_label}")

        # Show only non-zero counts
        if counts["created"]:
            print(f"  Created:   {counts['created']} folder{'s' if counts['created'] != 1 else ''}")
        if counts["moved"]:
            print(f"  Moved:     {counts['moved']} file{'s' if counts['moved'] != 1 else ''}")
        if counts["renamed"]:
            print(f"  Renamed:   {counts['renamed']} file{'s' if counts['renamed'] != 1 else ''}")
        if counts["copied"]:
            print(f"  Copied:    {counts['copied']} file{'s' if counts['copied'] != 1 else ''}")
        if counts["deleted"]:
            print(f"  Deleted:   {counts['deleted']} file{'s' if counts['deleted'] != 1 else ''}")
        if counts["listed"]:
            print(f"  Found:     {counts['listed']} file{'s' if counts['listed'] != 1 else ''}")
        if counts["files_affected"] and not any([counts["created"], counts["moved"], counts["renamed"], counts["copied"], counts["deleted"], counts["listed"]]):
            print(f"  Affected:  {counts['files_affected']} file{'s' if counts['files_affected'] != 1 else ''}")

        print(f"  Errors:    {counts['errors']}")
        print(f"  Time:      {secs:.1f} seconds")

        if counts["total_steps"] > 5 and not VERBOSE:
            print(f"\n  Run with --verbose to see all {counts['total_steps']} steps")

        # Show detailed results for file listings and simple queries
        result = output.get("result")
        if isinstance(result, list) and len(result) > 0:
            print()
            items = result
            def _fmt(item):
                if isinstance(item, dict):
                    if "from_name" in item and "to_name" in item:
                        return f"{item['from_name']}  ->  {item['to_name']}"
                    if "name" in item:
                        size = item.get("size_bytes", 0)
                        if size >= 1_073_741_824:
                            human = f"{size / 1_073_741_824:.1f} GB"
                        elif size >= 1_048_576:
                            human = f"{size / 1_048_576:.1f} MB"
                        elif size >= 1024:
                            human = f"{size / 1024:.1f} KB"
                        else:
                            human = f"{size} B"
                        return f"  {item['name']}  ({human})"
                    return json.dumps(item)
                return str(item)

            if len(items) > 20 and not VERBOSE:
                for item in items[:20]:
                    print(_fmt(item))
                print(f"  ... and {len(items) - 20} more")
            else:
                for item in items:
                    print(_fmt(item))

        # Show structured results (disk usage, metadata, etc.)
        elif isinstance(result, dict) and "completed_steps" not in result and "plan" not in result:
            print()
            for k, v in result.items():
                if k not in ("preview",):
                    print(f"  {k}: {v}")

        # Verbose: show all completed steps
        if VERBOSE and isinstance(result, dict) and "completed_steps" in result:
            print()
            for step in result.get("completed_steps", []):
                print(f"  [{step.get('step', '?')}] {step.get('tool', '?')} -- {step.get('action_performed', '')}")

    elif status == "error":
        err = output.get("error", {})
        code = err.get("code", "")
        # Sensitive files and agent-not-available already printed custom messages
        if code not in ("SENSITIVE_FILES_DETECTED", "AGENT_NOT_AVAILABLE"):
            print("  ERROR")
            print("=" * 60)
            print(f"  {err.get('message', 'Something went wrong')}")

    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    # --- Workspace setup ---
    first_run = _ensure_workspace()
    if first_run:
        home = os.path.expanduser("~")
        print(f"\n  \u2728 IntentOS workspace created at {home}/.intentos/\n")

    print("IntentOS Kernel v0.1.0")
    print("Type a task in natural language. Type 'exit' or 'quit' to stop.\n")

    client = create_client()
    context = _build_context(llm_client=client)

    # Import audit for task-level logging
    from capabilities.file_agent.audit import log_task

    while True:
        try:
            user_input = input("intentos> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            print("Exiting.")
            break

        task_start = time.monotonic()

        # Step 1: Parse intent via Claude
        intent = parse_intent(client, user_input)
        if intent is None:
            continue

        subtasks = intent.get("subtasks", [])
        if not subtasks:
            print("\nCouldn't break that down into actionable steps. Try rephrasing.\n")
            continue

        # Step 2: Show the plan
        print_intent(intent)

        # Step 3: Dry-run preview for destructive/large operations
        if _needs_preview(subtasks):
            print("\n  Running preview...")
            dry_context = {**context, "dry_run": True}
            preview_log = execute_subtasks(subtasks, dry_context)

            # Check if sensitive files were detected during preview
            sensitive_blocked = any(
                e.get("output", {}).get("error", {}).get("code") == "SENSITIVE_FILES_DETECTED"
                for e in preview_log
            )
            if sensitive_blocked:
                duration_ms = int((time.monotonic() - task_start) * 1000)
                agents = list({st.get("agent", "") for st in subtasks})
                log_task(user_input, intent.get("intent", "?"), agents, 0, "blocked_sensitive", duration_ms, cancelled=True)
                continue

            if not _show_preview(intent, preview_log):
                print("\n  Task cancelled -- nothing was changed.\n")
                duration_ms = int((time.monotonic() - task_start) * 1000)
                agents = list({st.get("agent", "") for st in subtasks})
                log_task(user_input, intent.get("intent", "?"), agents, 0, "cancelled", duration_ms, cancelled=True)
                continue

        # Step 4: Execute subtasks for real
        print("\n  Executing...\n")
        execution_log = execute_subtasks(subtasks, context)

        duration_ms = int((time.monotonic() - task_start) * 1000)

        # Step 5: Show result
        print_result_summary(intent, execution_log, duration_ms)

        # Step 6: Audit log
        agents_used = list({e.get("agent", "") for e in execution_log if e.get("agent")})
        total_files = 0
        final_status = "success"
        for entry in execution_log:
            meta = entry.get("output", {}).get("metadata", {})
            total_files += meta.get("files_affected", 0)
            if entry.get("status") == "error":
                final_status = "error"
            # Count files from completed plan steps
            result = entry.get("output", {}).get("result", {})
            if isinstance(result, dict) and "completed_steps" in result:
                total_files = max(total_files, len(result.get("completed_steps", [])))

        log_task(user_input, intent.get("intent", "?"), agents_used, total_files, final_status, duration_ms)


if __name__ == "__main__":
    main()
