"""
IntentOS file_agent — Primitive filesystem operations

Dumb, reliable building blocks. Each primitive:
  - Enforces path grants (Rule 1)
  - Respects dry_run (Rule 4)
  - Returns standard output dicts
  - Never surfaces raw OS errors (Rule 5)

The PRIMITIVES dict maps action names → functions.
"""

from __future__ import annotations

import fnmatch
import os
import shutil
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _is_path_allowed(path: str, granted_paths: list[str]) -> bool:
    resolved = str(Path(path).expanduser().resolve())
    for gp in granted_paths:
        gp_resolved = str(Path(gp).expanduser().resolve())
        if resolved == gp_resolved or resolved.startswith(gp_resolved + os.sep):
            return True
    return False


def _deny(path: str) -> dict:
    return {
        "status": "error",
        "error": {
            "code": "PATH_NOT_GRANTED",
            "message": f"I don't have access to that location ({Path(path).name})",
        },
        "metadata": _meta(),
    }


def _error(code: str, message: str, **meta_overrides) -> dict:
    return {
        "status": "error",
        "error": {"code": code, "message": message},
        "metadata": _meta(**meta_overrides),
    }


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


# ---------------------------------------------------------------------------
# Primitives — existing (extracted from original agent.py)
# ---------------------------------------------------------------------------

def list_files(params: dict, context: dict) -> dict:
    """List files in a directory with human-readable metadata."""
    t0 = time.monotonic()
    directory = params.get("path") or params.get("directory", ".")
    directory = str(Path(directory).expanduser().resolve())

    if not _is_path_allowed(directory, context["granted_paths"]):
        return _deny(directory)

    extension = params.get("extension") or params.get("type")
    recursive = params.get("recursive", False)

    if not Path(directory).exists():
        return _error("PATH_NOT_FOUND", "That folder doesn't exist — it may have been moved or deleted")

    if not Path(directory).is_dir():
        return _error("NOT_A_DIRECTORY", "That path is a file, not a folder")

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would list files in {Path(directory).name}/",
            "result": {"preview": f"Contents of {directory}"},
            "metadata": _meta(paths_accessed=[directory]),
        }

    files = []
    try:
        entries = Path(directory).rglob("*") if recursive else Path(directory).iterdir()
        for entry in entries:
            if not entry.is_file():
                continue
            if extension:
                ext = extension.lstrip(".")
                if entry.suffix.lstrip(".").lower() != ext.lower():
                    continue
            try:
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "path": str(entry),
                    "size_bytes": stat.st_size,
                    "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                })
            except OSError:
                continue
    except PermissionError:
        return _error("PERMISSION_DENIED", "I don't have permission to read that folder")

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Listed {len(files)} file(s) in {Path(directory).name}/",
        "result": files,
        "metadata": _meta(
            files_affected=len(files),
            duration_ms=elapsed,
            paths_accessed=[directory],
        ),
    }


def find_files(params: dict, context: dict) -> dict:
    """Find files by name pattern and optional filters."""
    t0 = time.monotonic()
    directory = params.get("path") or params.get("directory", ".")
    directory = str(Path(directory).expanduser().resolve())

    if not _is_path_allowed(directory, context["granted_paths"]):
        return _deny(directory)

    if not Path(directory).is_dir():
        return _error("NOT_A_DIRECTORY", "That path is not a folder I can search")

    pattern = params.get("pattern", "*")
    extension = params.get("extension") or params.get("type")
    if extension:
        pattern = f"*.{extension.lstrip('.')}"

    modified_after = params.get("modified_after")
    modified_before = params.get("modified_before")
    size_gt = params.get("size_gt")
    size_lt = params.get("size_lt")

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would search for '{pattern}' in {Path(directory).name}/",
            "result": {"preview": f"Search {directory} for {pattern}"},
            "metadata": _meta(paths_accessed=[directory]),
        }

    matches = []
    try:
        for entry in Path(directory).rglob("*"):
            if not entry.is_file():
                continue
            if not fnmatch.fnmatch(entry.name.lower(), pattern.lower()):
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            if modified_after:
                cutoff = time.mktime(time.strptime(modified_after[:10], "%Y-%m-%d"))
                if stat.st_mtime < cutoff:
                    continue
            if modified_before:
                cutoff = time.mktime(time.strptime(modified_before[:10], "%Y-%m-%d"))
                if stat.st_mtime > cutoff:
                    continue
            if size_gt and stat.st_size <= size_gt:
                continue
            if size_lt and stat.st_size >= size_lt:
                continue
            matches.append({
                "name": entry.name,
                "path": str(entry),
                "size_bytes": stat.st_size,
                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            })
    except PermissionError:
        return _error("PERMISSION_DENIED", "I don't have permission to search that folder")

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Found {len(matches)} file(s) matching '{pattern}'",
        "result": matches,
        "metadata": _meta(
            files_affected=len(matches),
            duration_ms=elapsed,
            paths_accessed=[directory],
        ),
    }


def rename_file(params: dict, context: dict) -> dict:
    """Rename a single file."""
    t0 = time.monotonic()
    source = params.get("path") or params.get("source", "")
    source = str(Path(source).expanduser().resolve())
    new_name = params.get("new_name") or params.get("destination", "")

    if not _is_path_allowed(source, context["granted_paths"]):
        return _deny(source)

    if not Path(source).exists():
        return _error("FILE_NOT_FOUND", "I couldn't find that file — it may have been moved or deleted")

    if os.sep in new_name or new_name.startswith("~"):
        destination = str(Path(new_name).expanduser().resolve())
    else:
        destination = str(Path(source).parent / new_name)

    if not _is_path_allowed(destination, context["granted_paths"]):
        return _deny(destination)

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would rename {Path(source).name} to {Path(destination).name}",
            "result": {"from": source, "to": destination},
            "metadata": _meta(files_affected=1, paths_accessed=[source]),
        }

    # Confirmation — skipped when called with confirmed: True (e.g. from planner)
    if not params.get("confirmed"):
        return {
            "status": "confirmation_required",
            "confirmation_prompt": f"Rename '{Path(source).name}' to '{Path(destination).name}'?",
            "confirmation_action": {
                "action": "rename_file",
                "params": {**params, "confirmed": True},
            },
            "metadata": _meta(paths_accessed=[source]),
        }

    try:
        Path(source).rename(destination)
    except FileNotFoundError:
        return _error("FILE_NOT_FOUND", "I couldn't find that file — it may have been moved or deleted")
    except PermissionError:
        return _error("PERMISSION_DENIED", "I don't have permission to rename that file")
    except OSError:
        return _error("RENAME_FAILED", "Something went wrong while renaming that file")

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Renamed {Path(source).name} to {Path(destination).name}",
        "result": {"from": source, "to": destination},
        "metadata": _meta(
            files_affected=1,
            duration_ms=elapsed,
            paths_accessed=[source, destination],
        ),
    }


def move_file(params: dict, context: dict) -> dict:
    """Move a file to a new location."""
    t0 = time.monotonic()
    source = params.get("path") or params.get("source", "")
    source = str(Path(source).expanduser().resolve())
    destination = params.get("destination", "")
    destination = str(Path(destination).expanduser().resolve())

    if not _is_path_allowed(source, context["granted_paths"]):
        return _deny(source)
    if not _is_path_allowed(destination, context["granted_paths"]):
        return _deny(destination)

    if not Path(source).exists():
        return _error("FILE_NOT_FOUND", "I couldn't find that file — it may have been moved or deleted")

    if Path(destination).is_dir():
        destination = str(Path(destination) / Path(source).name)

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would move {Path(source).name} to {Path(destination).parent.name}/",
            "result": {"from": source, "to": destination},
            "metadata": _meta(files_affected=1, paths_accessed=[source]),
        }

    # Confirmation — skipped when called with confirmed: True (e.g. from planner)
    if not params.get("confirmed"):
        return {
            "status": "confirmation_required",
            "confirmation_prompt": f"Move '{Path(source).name}' to '{Path(destination).parent.name}/'?",
            "confirmation_action": {
                "action": "move_file",
                "params": {**params, "confirmed": True},
            },
            "metadata": _meta(paths_accessed=[source]),
        }

    try:
        os.makedirs(Path(destination).parent, exist_ok=True)
        shutil.move(source, destination)
    except FileNotFoundError:
        return _error("FILE_NOT_FOUND", "I couldn't find that file — it may have been moved or deleted")
    except PermissionError:
        return _error("PERMISSION_DENIED", "I don't have permission to move that file")
    except OSError:
        return _error("MOVE_FAILED", "Something went wrong while moving that file")

    elapsed = int((time.monotonic() - t0) * 1000)
    size = Path(destination).stat().st_size if Path(destination).exists() else 0
    return {
        "status": "success",
        "action_performed": f"Moved {Path(source).name} to {Path(destination).parent.name}/",
        "result": {"from": source, "to": destination},
        "metadata": _meta(
            files_affected=1,
            bytes_affected=size,
            duration_ms=elapsed,
            paths_accessed=[source, destination],
        ),
    }


def get_disk_usage(params: dict, context: dict) -> dict:
    """Get disk usage for a path."""
    t0 = time.monotonic()
    target = params.get("path") or params.get("directory", ".")
    target = str(Path(target).expanduser().resolve())

    if not _is_path_allowed(target, context["granted_paths"]):
        return _deny(target)

    if not Path(target).exists():
        return _error("PATH_NOT_FOUND", "That path doesn't exist")

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would calculate disk usage for {Path(target).name}",
            "result": {"preview": f"Disk usage of {target}"},
            "metadata": _meta(paths_accessed=[target]),
        }

    try:
        if Path(target).is_file():
            total_bytes = Path(target).stat().st_size
            file_count = 1
        else:
            total_bytes = 0
            file_count = 0
            for entry in Path(target).rglob("*"):
                if entry.is_file():
                    try:
                        total_bytes += entry.stat().st_size
                        file_count += 1
                    except OSError:
                        continue

        if total_bytes >= 1_073_741_824:
            human_size = f"{total_bytes / 1_073_741_824:.2f} GB"
        elif total_bytes >= 1_048_576:
            human_size = f"{total_bytes / 1_048_576:.2f} MB"
        elif total_bytes >= 1024:
            human_size = f"{total_bytes / 1024:.2f} KB"
        else:
            human_size = f"{total_bytes} bytes"

        disk = shutil.disk_usage(target)
        disk_free_gb = disk.free / 1_073_741_824
    except PermissionError:
        return _error("PERMISSION_DENIED", "I don't have permission to read that location")

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"{Path(target).name}/ uses {human_size} across {file_count} file(s)",
        "result": {
            "path": target,
            "total_bytes": total_bytes,
            "human_size": human_size,
            "file_count": file_count,
            "disk_free_gb": round(disk_free_gb, 2),
        },
        "metadata": _meta(
            files_affected=file_count,
            bytes_affected=total_bytes,
            duration_ms=elapsed,
            paths_accessed=[target],
        ),
    }


# ---------------------------------------------------------------------------
# Primitives — new
# ---------------------------------------------------------------------------

_READ_SIZE_LIMIT = 1_048_576  # 1 MB


def read_file(params: dict, context: dict) -> dict:
    """Read text file content (up to 1 MB)."""
    t0 = time.monotonic()
    filepath = params.get("path", "")
    filepath = str(Path(filepath).expanduser().resolve())

    if not _is_path_allowed(filepath, context["granted_paths"]):
        return _deny(filepath)

    if not Path(filepath).exists():
        return _error("FILE_NOT_FOUND", "I couldn't find that file")

    if not Path(filepath).is_file():
        return _error("NOT_A_FILE", "That path is a directory, not a file")

    size = Path(filepath).stat().st_size
    if size > _READ_SIZE_LIMIT:
        return _error("FILE_TOO_LARGE", f"That file is too large to read ({size:,} bytes, limit is 1 MB)")

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would read {Path(filepath).name}",
            "result": {"preview": f"Contents of {filepath} ({size} bytes)"},
            "metadata": _meta(paths_accessed=[filepath]),
        }

    try:
        content = Path(filepath).read_text(errors="replace")
    except PermissionError:
        return _error("PERMISSION_DENIED", "I don't have permission to read that file")

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Read {Path(filepath).name} ({size:,} bytes)",
        "result": {"path": filepath, "content": content, "size_bytes": size},
        "metadata": _meta(
            files_affected=1,
            bytes_affected=size,
            duration_ms=elapsed,
            paths_accessed=[filepath],
        ),
    }


def copy_file(params: dict, context: dict) -> dict:
    """Copy a file to a new location (preserves metadata)."""
    t0 = time.monotonic()
    source = params.get("path") or params.get("source", "")
    source = str(Path(source).expanduser().resolve())
    destination = params.get("destination", "")
    destination = str(Path(destination).expanduser().resolve())

    if not _is_path_allowed(source, context["granted_paths"]):
        return _deny(source)
    if not _is_path_allowed(destination, context["granted_paths"]):
        return _deny(destination)

    if not Path(source).exists():
        return _error("FILE_NOT_FOUND", "I couldn't find that file")

    if Path(destination).is_dir():
        destination = str(Path(destination) / Path(source).name)

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would copy {Path(source).name} to {Path(destination).parent.name}/",
            "result": {"from": source, "to": destination},
            "metadata": _meta(files_affected=1, paths_accessed=[source]),
        }

    # Confirmation — skipped when called with confirmed: True (e.g. from planner)
    if not params.get("confirmed"):
        return {
            "status": "confirmation_required",
            "confirmation_prompt": f"Copy '{Path(source).name}' to '{Path(destination).parent.name}/'?",
            "confirmation_action": {
                "action": "copy_file",
                "params": {**params, "confirmed": True},
            },
            "metadata": _meta(paths_accessed=[source]),
        }

    try:
        os.makedirs(Path(destination).parent, exist_ok=True)
        shutil.copy2(source, destination)
    except FileNotFoundError:
        return _error("FILE_NOT_FOUND", "I couldn't find that file")
    except PermissionError:
        return _error("PERMISSION_DENIED", "I don't have permission to copy that file")
    except OSError:
        return _error("COPY_FAILED", "Something went wrong while copying that file")

    elapsed = int((time.monotonic() - t0) * 1000)
    size = Path(destination).stat().st_size if Path(destination).exists() else 0
    return {
        "status": "success",
        "action_performed": f"Copied {Path(source).name} to {Path(destination).parent.name}/",
        "result": {"from": source, "to": destination},
        "metadata": _meta(
            files_affected=1,
            bytes_affected=size,
            duration_ms=elapsed,
            paths_accessed=[source, destination],
        ),
    }


def create_folder(params: dict, context: dict) -> dict:
    """Create a directory (including intermediate directories)."""
    t0 = time.monotonic()
    folder = params.get("path", "")
    folder = str(Path(folder).expanduser().resolve())

    if not _is_path_allowed(folder, context["granted_paths"]):
        return _deny(folder)

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would create folder {Path(folder).name}/",
            "result": {"path": folder},
            "metadata": _meta(paths_accessed=[folder]),
        }

    try:
        os.makedirs(folder, exist_ok=True)
    except PermissionError:
        return _error("PERMISSION_DENIED", "I don't have permission to create that folder")
    except OSError:
        return _error("CREATE_FAILED", "Something went wrong while creating that folder")

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Created folder {Path(folder).name}/",
        "result": {"path": folder},
        "metadata": _meta(
            duration_ms=elapsed,
            paths_accessed=[folder],
        ),
    }


def delete_file(params: dict, context: dict) -> dict:
    """Delete a file. ALWAYS requires confirmation (confirmed: True)."""
    t0 = time.monotonic()
    filepath = params.get("path", "")
    filepath = str(Path(filepath).expanduser().resolve())

    if not _is_path_allowed(filepath, context["granted_paths"]):
        return _deny(filepath)

    if not Path(filepath).exists():
        return _error("FILE_NOT_FOUND", "I couldn't find that file")

    if not Path(filepath).is_file():
        return _error("NOT_A_FILE", "That path is a directory — use a different approach to remove directories")

    size = Path(filepath).stat().st_size

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would delete {Path(filepath).name}",
            "result": {"path": filepath, "size_bytes": size},
            "metadata": _meta(files_affected=1, paths_accessed=[filepath]),
        }

    # delete_file ALWAYS requires explicit confirmation
    if not params.get("confirmed"):
        return {
            "status": "confirmation_required",
            "confirmation_prompt": f"Permanently delete '{Path(filepath).name}'?",
            "confirmation_action": {
                "action": "delete_file",
                "params": {**params, "confirmed": True},
            },
            "metadata": _meta(paths_accessed=[filepath]),
        }

    try:
        os.remove(filepath)
    except FileNotFoundError:
        return _error("FILE_NOT_FOUND", "I couldn't find that file")
    except PermissionError:
        return _error("PERMISSION_DENIED", "I don't have permission to delete that file")
    except OSError:
        return _error("DELETE_FAILED", "Something went wrong while deleting that file")

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Deleted {Path(filepath).name}",
        "result": {"path": filepath, "size_bytes": size},
        "metadata": _meta(
            files_affected=1,
            bytes_affected=size,
            duration_ms=elapsed,
            paths_accessed=[filepath],
        ),
    }


def get_metadata(params: dict, context: dict) -> dict:
    """Get file/directory metadata (size, modified, created, type)."""
    t0 = time.monotonic()
    filepath = params.get("path", "")
    filepath = str(Path(filepath).expanduser().resolve())

    if not _is_path_allowed(filepath, context["granted_paths"]):
        return _deny(filepath)

    if not Path(filepath).exists():
        return _error("FILE_NOT_FOUND", "I couldn't find that path")

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would get metadata for {Path(filepath).name}",
            "result": {"preview": f"Metadata for {filepath}"},
            "metadata": _meta(paths_accessed=[filepath]),
        }

    try:
        stat = Path(filepath).stat()
        is_dir = Path(filepath).is_dir()
        info = {
            "path": filepath,
            "name": Path(filepath).name,
            "type": "directory" if is_dir else "file",
            "size_bytes": stat.st_size,
            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            "created": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_ctime)),
            "extension": Path(filepath).suffix if not is_dir else None,
        }
    except PermissionError:
        return _error("PERMISSION_DENIED", "I don't have permission to read that file's metadata")

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Got metadata for {Path(filepath).name}",
        "result": info,
        "metadata": _meta(
            files_affected=1,
            duration_ms=elapsed,
            paths_accessed=[filepath],
        ),
    }


# ---------------------------------------------------------------------------
# Registry — the only export that matters
# ---------------------------------------------------------------------------

PRIMITIVES: dict[str, callable] = {
    "list_files": list_files,
    "find_files": find_files,
    "rename_file": rename_file,
    "move_file": move_file,
    "get_disk_usage": get_disk_usage,
    "read_file": read_file,
    "copy_file": copy_file,
    "create_folder": create_folder,
    "delete_file": delete_file,
    "get_metadata": get_metadata,
}
