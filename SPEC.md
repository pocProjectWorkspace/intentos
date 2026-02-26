# IntentOS Capability Specification
### *Everything you need to build a capability that works with IntentOS*

**Version:** 0.1.0
**Location:** `/capabilities/SPEC.md`

---

## What Is a Capability?

A capability is the IntentOS equivalent of an application. It is a self-contained agent that knows how to do one category of things — working with files, browsing the web, editing images, playing media, and so on.

The difference between a capability and an app is fundamental: the user never chooses, launches, or manages a capability. The Intent Kernel routes tasks to capabilities automatically. The user just describes what they want. The right capability runs. The user never knows its name.

If you can build a capability that does one thing well and follows this spec, it becomes part of IntentOS for every user. No distribution. No store listing. No install instructions to write. It just works.

---

## Before You Build

**Check the registry first.** Before building a new capability, search the IntentHub registry to make sure one doesn't already exist for your use case. Duplicate capabilities fragment the ecosystem.

**Start with one action.** The best capabilities start narrow and expand. A capability that does one thing reliably is more valuable than one that does ten things poorly. `file_agent` started with `list_files` before it did anything else.

**Read an existing spec.** The `/capabilities/file_agent.md` spec is the reference implementation. Read it before writing your own.

---

## Capability Structure

Every capability lives in its own folder inside `/capabilities/`:

```
/capabilities/
└── your_agent/
    ├── agent.py           ← required: main entry point
    ├── manifest.json      ← required: identity and permissions
    ├── SPEC.md            ← required: human-readable specification
    ├── requirements.txt   ← required: Python dependencies
    ├── tests/
    │   ├── test_agent.py  ← required: test suite
    │   └── fixtures/      ← optional: test data
    └── README.md          ← optional: contributor notes
```

Every file marked **required** must be present and valid before a capability can be accepted to IntentHub.

---

## The Manifest

`manifest.json` is the identity card of your capability. The Agent Scheduler reads this before deciding whether and how to run your agent.

### Full manifest schema

```json
{
  "name": "your_agent",
  "version": "0.1.0",
  "description": "One sentence describing what this agent does",
  "author": "your-github-handle",
  "license": "MIT",
  "category": "files | browser | image | media | system | document | utility",
  "status": "draft | stable | deprecated",

  "permissions": [
    "filesystem.read",
    "filesystem.write",
    "filesystem.move",
    "filesystem.delete",
    "network",
    "system.processes",
    "system.hardware",
    "display"
  ],

  "optional_permissions": [],

  "actions": [
    "action_one",
    "action_two"
  ],

  "platforms": ["linux", "macos", "windows"],

  "dependencies": {
    "ollama_models": [],
    "system_binaries": [],
    "python_packages": "see requirements.txt"
  },

  "min_intentos_version": "0.1.0"
}
```

### Permission reference

Declare only the permissions your capability actually needs. The Agent Scheduler will reject capabilities that request more than their declared actions require.

| Permission | What it allows | Notes |
|---|---|---|
| `filesystem.read` | Read file contents and metadata | Most capabilities need this |
| `filesystem.write` | Create and modify files | Only write to `workspace/outputs/` by default |
| `filesystem.move` | Move and rename files | Requires `filesystem.read` |
| `filesystem.delete` | Delete files | Always triggers confirmation flow |
| `network` | Make HTTP/S requests | Browser and API-connected agents only |
| `system.processes` | List and manage processes | System agent only |
| `system.hardware` | Read hardware info (CPU, RAM, disk) | System agent only |
| `display` | Render output to screen | Media playback agents only |

**The golden rule:** if you can complete your capability's actions without a permission, do not declare it. A capability that requests `network` but only works with local files will be rejected.

---

## The Entry Point

`agent.py` must expose a single function:

```python
def run(input: dict) -> dict:
    ...
```

That is the entire contract. The Agent Scheduler calls `run()` with an input dict and expects a response dict back. Everything else is implementation detail.

### Input dict

```python
{
    "action": str,           # which action to perform
    "params": dict,          # action-specific parameters
    "context": {             # injected by the scheduler, read-only
        "user": str,         # OS username of the requesting user
        "workspace": str,    # absolute path to ~/.intentos/workspace/
        "granted_paths": list[str],  # paths this capability may access
        "task_id": str,      # unique ID of the parent task
        "dry_run": bool      # if True, describe what would happen, don't do it
    }
}
```

### Output dict

```python
{
    "status": str,           # "success" | "error" | "confirmation_required"
    "action_performed": str, # plain language: what actually happened
    "result": any,           # the data returned (files, content, info, etc.)

    # only present if status == "confirmation_required"
    "confirmation_prompt": str,   # plain language: what will happen if confirmed
    "confirmation_action": dict,  # the exact input to re-run if user confirms

    # only present if status == "error"
    "error": {
        "code": str,         # machine-readable error code
        "message": str       # plain language: what went wrong (never a stack trace)
    },

    # always present
    "metadata": {
        "files_affected": int,
        "bytes_affected": int,
        "duration_ms": int,
        "paths_accessed": list[str]   # for audit log
    }
}
```

### Minimal working example

```python
# capabilities/hello_agent/agent.py

def run(input: dict) -> dict:
    action = input.get("action")
    params = input.get("params", {})
    context = input.get("context", {})

    if action == "greet":
        name = params.get("name", "world")
        return {
            "status": "success",
            "action_performed": f"Greeted {name}",
            "result": f"Hello, {name}!",
            "metadata": {
                "files_affected": 0,
                "bytes_affected": 0,
                "duration_ms": 1,
                "paths_accessed": []
            }
        }

    return {
        "status": "error",
        "error": {
            "code": "UNKNOWN_ACTION",
            "message": f"I don't know how to do '{action}'"
        },
        "metadata": {
            "files_affected": 0,
            "bytes_affected": 0,
            "duration_ms": 0,
            "paths_accessed": []
        }
    }
```

---

## The Five Rules

Every capability must follow these rules without exception. Capabilities that violate them will not be accepted to IntentHub.

---

### Rule 1: Never exceed your granted paths

The `context.granted_paths` list tells you exactly which filesystem paths you may access. You must never read from or write to any path outside this list — even if the task explicitly asks you to.

```python
# CORRECT
def is_path_allowed(path: str, granted_paths: list[str]) -> bool:
    from pathlib import Path
    resolved = Path(path).resolve()
    return any(
        str(resolved).startswith(str(Path(gp).resolve()))
        for gp in granted_paths
    )

# Before any file operation:
if not is_path_allowed(target_path, context["granted_paths"]):
    return {
        "status": "error",
        "error": {
            "code": "PATH_NOT_GRANTED",
            "message": "I don't have access to that location"
        },
        ...
    }
```

---

### Rule 2: All writes go to the workspace by default

Unless the task explicitly requires modifying a file in place (e.g. renaming), all output files must be written to `context["workspace"] + "/outputs/"`.

```python
import os

output_dir = os.path.join(context["workspace"], "outputs")
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "result.pdf")
```

Never scatter output files across the user's filesystem. The workspace is the only place agents create new files by default.

---

### Rule 3: Destructive actions require confirmation

Any action that cannot be undone — deletion, overwriting an existing file, moving a file out of its original location permanently — must return `confirmation_required` on first invocation.

```python
def delete_file(path: str, params: dict) -> dict:
    if not params.get("confirmed"):
        return {
            "status": "confirmation_required",
            "confirmation_prompt": f"This will permanently delete {os.path.basename(path)}. This cannot be undone.",
            "confirmation_action": {
                "action": "delete_file",
                "params": {**params, "confirmed": True}
            },
            ...
        }

    # only reaches here if confirmed == True
    os.remove(path)
    return { "status": "success", ... }
```

The Intent Kernel handles surfacing the confirmation to the user. Your job is just to return the right status and prompt.

---

### Rule 4: Respect dry_run

If `context["dry_run"]` is `True`, your capability must describe what it *would* do without actually doing it. Every action must support dry run.

```python
if context.get("dry_run"):
    return {
        "status": "success",
        "action_performed": f"Would rename {len(files)} files using pattern {pattern}",
        "result": {
            "preview": [
                {"from": f["name"], "to": generate_new_name(f, pattern)}
                for f in files
            ]
        },
        ...
    }
```

Dry run is how IntentOS previews batch operations before committing. It is not optional.

---

### Rule 5: Never surface raw errors

Never return a Python exception, stack trace, or OS error code directly in the `error.message` field. Always translate to plain language.

```python
# WRONG
except FileNotFoundError as e:
    return {"status": "error", "error": {"message": str(e)}}
    # returns: "[Errno 2] No such file or directory: '/home/user/thing.pdf'"

# CORRECT
except FileNotFoundError:
    return {"status": "error", "error": {
        "code": "FILE_NOT_FOUND",
        "message": "I couldn't find that file — it may have been moved or deleted"
    }}
```

The user never sees error codes or technical details. The Intent Kernel translates your `error.message` into a response. Write it as if you're explaining the problem to a non-technical person.

---

## Handling the dry_run + confirmation Pattern Together

For batch destructive operations, the recommended flow combines dry_run preview with confirmation:

```
1. Intent Kernel calls your agent with dry_run=True
   → You return a preview of what would happen
   → Intent Kernel shows this to the user

2. User confirms
   → Intent Kernel calls your agent with dry_run=False, confirmed=False
   → For small operations: proceed directly
   → For irreversible operations: return confirmation_required

3. User confirms the confirmation
   → Intent Kernel calls with confirmed=True
   → You execute
```

This two-stage pattern (preview → confirm → execute) is the standard for any operation affecting 5+ files or any irreversible single-file operation.

---

## Writing Your SPEC.md

Every capability must include a `SPEC.md` that documents what it does in human language. Follow the structure of `/capabilities/file_agent.md`:

```markdown
# your_agent
### *One line description*

**Version:** x.x.x
**Status:** draft | stable
**Category:** files | browser | image | media | system | document | utility

## What This Agent Does
Plain language description. Example tasks it handles (use blockquotes).

## Permissions
Table of permissions — required vs optional, with reason for each.

## ACP Interface
### Agent Manifest (the full JSON)
### Input Schema (the full JSON)
### Output Schema (the full JSON)

## Behavior Specifications
One section per action. Plain language description of exactly what it does,
edge cases, and error handling.

## Implementation Notes
Language, key libraries, what NOT to build in v0.x.

## Contributing
How to set up, test, and submit a PR.
```

If a developer can read your SPEC.md and know exactly what to build without asking you any questions — it's good enough.

---

## Testing Requirements

Every capability must have a test suite in `/tests/test_agent.py`. Tests must:

**Cover every declared action.** If your manifest lists 6 actions, you have at least 6 tests — one per action covering the happy path.

**Cover error cases.** Test what happens with a missing file, a bad path, an unsupported file type, a network timeout. Errors should return the right structure, not raise exceptions.

**Test dry_run for every action.** Every action has a dry_run test that verifies it returns a preview without side effects.

**Test confirmation flow for destructive actions.** Verify that without `confirmed=True`, destructive actions return `confirmation_required`. Verify that with `confirmed=True`, they execute.

**Use a sandboxed directory.** All tests must use a temporary directory (`tempfile.mkdtemp()` or `tmp_path` in pytest). No test may touch the real user filesystem.

```python
# tests/test_agent.py — minimal structure

import tempfile
import os
import pytest
from agent import run

@pytest.fixture
def context(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return {
        "user": "test_user",
        "workspace": str(workspace),
        "granted_paths": [str(tmp_path)],
        "task_id": "test-task-001",
        "dry_run": False
    }

def test_action_happy_path(context, tmp_path):
    # create test fixture
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")

    result = run({
        "action": "your_action",
        "params": {"path": str(test_file)},
        "context": context
    })

    assert result["status"] == "success"
    assert "metadata" in result
    assert "paths_accessed" in result["metadata"]

def test_action_dry_run(context, tmp_path):
    dry_context = {**context, "dry_run": True}
    result = run({
        "action": "your_action",
        "params": {"path": str(tmp_path)},
        "context": dry_context
    })
    assert result["status"] == "success"
    # verify no side effects occurred
    assert len(list(tmp_path.iterdir())) == 0  # nothing written

def test_path_outside_grants_rejected(context, tmp_path):
    result = run({
        "action": "your_action",
        "params": {"path": "/etc/passwd"},
        "context": context
    })
    assert result["status"] == "error"
    assert result["error"]["code"] == "PATH_NOT_GRANTED"

def test_destructive_action_requires_confirmation(context, tmp_path):
    test_file = tmp_path / "deleteme.txt"
    test_file.write_text("content")

    result = run({
        "action": "delete_file",
        "params": {"path": str(test_file)},
        "context": context
    })
    assert result["status"] == "confirmation_required"
    assert test_file.exists()  # file not deleted yet
```

---

## Submitting a Capability

When your capability is ready:

**1. Self-review checklist**

Before opening a PR, confirm all of the following:

```
□ manifest.json is valid and permissions are minimal
□ agent.py exposes run(input: dict) -> dict
□ All five rules are implemented
□ Every action has a happy path test
□ Every action has a dry_run test
□ Every destructive action has a confirmation test
□ Error messages are plain language, no stack traces
□ All writes go to workspace/outputs/ by default
□ Path grants are enforced before every file operation
□ SPEC.md follows the required structure
□ requirements.txt lists all dependencies
□ Tested on at least one platform (Linux preferred)
```

**2. Open a Pull Request**

Title format: `capability: add your_agent`

PR description must include:
- What the capability does (one paragraph)
- Which platform(s) you tested on
- Any known limitations
- Three example tasks from the user's perspective (natural language, as if typed into the Task Interface)

**3. Review process**

A maintainer will review: manifest permissions vs declared actions, test coverage, error handling, SPEC.md completeness, and — most importantly — whether the capability does one thing well rather than many things partially.

Expect feedback. The first review is usually about scope — first-time contributors almost always build too much. That's fine. Scope it down, ship the core, expand from there.

**4. After acceptance**

Your capability is published to IntentHub automatically on merge. It becomes available to all IntentOS users on their next registry sync. You'll be listed as the author in the manifest and in the IntentHub directory.

---

## Capability Categories and Naming

| Category | Naming convention | Examples |
|---|---|---|
| `files` | `*_agent` | `file_agent`, `archive_agent` |
| `browser` | `*_agent` | `browser_agent`, `search_agent` |
| `image` | `*_agent` | `image_agent`, `screenshot_agent` |
| `media` | `*_agent` | `media_agent`, `audio_agent` |
| `system` | `*_agent` | `system_agent`, `network_agent` |
| `document` | `*_agent` | `document_agent`, `pdf_agent` |
| `utility` | `*_agent` | `calendar_agent`, `email_agent` |

Names must be lowercase, snake_case, end in `_agent`, and be unique in the registry.

---

## Version Policy

IntentOS capabilities use semantic versioning: `MAJOR.MINOR.PATCH`

- `PATCH` — bug fixes, no interface changes
- `MINOR` — new actions added, existing actions unchanged
- `MAJOR` — breaking changes to existing action interfaces

The `min_intentos_version` field in your manifest must reflect the minimum IntentOS version your capability requires. Do not use features from newer IntentOS versions without updating this field.

---

## Getting Help

**GitHub Discussions** — for design questions before you build
**GitHub Issues** — for bugs in the spec itself
**`#capabilities` channel** — real-time contributor chat (link in repo README)

If you're unsure whether your idea is a good fit for a capability, open a Discussion first. Describe the user-facing tasks you want to enable. The community will help you figure out the right scope and whether it overlaps with existing work.

---

*IntentOS Capability Specification v0.1.0 — build something the user will never have to think about.*
