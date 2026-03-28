# file_agent
### *The File System Capability for IntentOS*

**Version:** 0.1.0 (Specification)
**Status:** Draft
**Category:** Core Capability

---

## What This Agent Does

`file_agent` is IntentOS's interface to the local file system. It handles any task that involves reading, writing, finding, moving, organizing, or understanding files and folders — without the user ever needing to know where files are or how file operations work.

**Example tasks this agent handles:**

> *"Find all the PDFs I downloaded this month"*
> *"Move everything in my Downloads folder older than 30 days to Archive"*
> *"Rename all the photos from my holiday trip by date taken"*
> *"How much space are my video files taking up?"*
> *"Find the invoice I got from Ahmed last week"*
> *"Compress all the images in this folder"*
> *"What are the 10 largest files on my computer?"*

---

## Permissions

`file_agent` must declare and be granted the following permissions before execution. The Agent Scheduler enforces these — the agent cannot exceed them.

| Permission | Required | Reason |
|---|---|---|
| `filesystem.read` | Yes | Reading file contents and metadata |
| `filesystem.write` | Yes | Creating, modifying, saving files |
| `filesystem.move` | Yes | Moving and renaming files |
| `filesystem.delete` | Optional | Deleting files (requires explicit user confirmation) |
| `network` | No | File agent never makes network calls |

> **Note:** `filesystem.delete` is never executed without an explicit confirmation step returned to the Task Interface. The Intent Kernel must surface this confirmation in plain language before the Scheduler allows deletion.

---

## ACP Interface

Every IntentOS capability must implement the Agent Communication Protocol (ACP). Below is the `file_agent` interface contract.

### Agent Manifest
```json
{
  "name": "file_agent",
  "version": "0.1.0",
  "description": "Handles all local file system operations for IntentOS",
  "permissions": ["filesystem.read", "filesystem.write", "filesystem.move"],
  "optional_permissions": ["filesystem.delete"],
  "actions": [
    "list_files",
    "read_file",
    "write_file",
    "move_file",
    "rename_file",
    "copy_file",
    "delete_file",
    "search_files",
    "get_metadata",
    "get_disk_usage"
  ]
}
```

### Input Schema
```json
{
  "action": "string (required) — one of the declared actions",
  "path": "string — file or folder path, supports ~ and glob patterns",
  "destination": "string — target path for move/copy/rename operations",
  "query": "string — natural language search query for search_files",
  "filters": {
    "type": "string — file extension or mime type (e.g. 'pdf', 'image/*')",
    "modified_after": "ISO8601 date string",
    "modified_before": "ISO8601 date string",
    "size_gt": "integer — bytes",
    "size_lt": "integer — bytes"
  },
  "options": {
    "recursive": "boolean — apply to subfolders",
    "dry_run": "boolean — return what would happen without doing it",
    "confirm_required": "boolean — pause and request confirmation before destructive actions"
  }
}
```

### Output Schema
```json
{
  "status": "success | error | confirmation_required",
  "action_performed": "string — what was actually done",
  "result": "array or object — the files/data returned",
  "confirmation_prompt": "string — plain language confirmation request (if status is confirmation_required)",
  "error": {
    "code": "string",
    "message": "string — plain language, never a stack trace"
  },
  "metadata": {
    "files_affected": "integer",
    "bytes_affected": "integer",
    "duration_ms": "integer"
  }
}
```

---

## Behavior Specifications

### Listing Files
When asked to list files, `file_agent` returns files with human-readable metadata — name, size, type, last modified date. It never returns raw inodes or technical filesystem data to the Intent Kernel unless specifically requested.

### Searching Files
`file_agent` supports both exact and semantic search. For semantic search (e.g. *"the invoice from Ahmed"*), it uses filename, file content (for text files), and the Semantic Memory Layer's file index to surface the most relevant result.

### Destructive Operations
Any action that cannot be undone — deletion, overwriting an existing file — must:
1. Return `status: "confirmation_required"` on first call
2. Include a `confirmation_prompt` in plain language describing exactly what will happen
3. Only proceed when re-invoked with `options.confirm_required: false` (set by Intent Kernel after user confirms)

### Dry Run Mode
Any operation can be run with `options.dry_run: true`. This returns a plain language description of what *would* happen — useful for the Intent Kernel to surface a preview to the user before committing to large batch operations.

### Error Handling
`file_agent` never surfaces raw OS errors to the Intent Kernel. All errors are translated to plain language. Examples:

| OS Error | file_agent message |
|---|---|
| `ENOENT: no such file or directory` | "I couldn't find a file at that path" |
| `EACCES: permission denied` | "I don't have permission to access that file" |
| `ENOSPC: no space left on device` | "There isn't enough disk space to complete this" |

---

## Implementation Notes

*For contributors building the first version of file_agent.*

**Language:** Python 3.11+

**Key libraries:**
- `pathlib` — all path operations (no `os.path`)
- `shutil` — copy/move operations
- `fnmatch` / `glob` — pattern matching
- `python-magic` — file type detection from content, not extension
- `humanize` — human-readable file sizes and dates in output

**What NOT to build in v0.1:**
- Compression/decompression (that's a separate `archive_agent`)
- File content parsing (PDFs, images — those route to `document_agent` and `image_agent`)
- Network file systems (S3, Google Drive — future capability)
- Watching for file changes (future, for automation workflows)

**Testing approach:**
Every action must have a dry_run test. No test should write to or delete real user files. Use a sandboxed `/tmp/intentos_test/` directory for all tests.

---

## Future Actions (Post v0.1)

- `watch_folder` — trigger a task when files are added to a folder
- `sync_folder` — keep two folders in sync
- `extract_archive` — unzip/untar files
- `tag_file` — add semantic tags to files for better search
- `version_file` — simple versioning for important files

---

## Contributing

To implement this capability:
1. Read `/capabilities/SPEC.md` for the full ACP contributor guide
2. Create your implementation in `/capabilities/file_agent/`
3. Your entry point must be `agent.py` with a `run(input: dict) -> dict` function
4. Include tests in `/capabilities/file_agent/tests/`
5. Open a PR — the capability is ready when all tests pass and a human can use it for 5 real tasks without confusion

---

*IntentOS Capability — file_agent v0.1.0 spec*
