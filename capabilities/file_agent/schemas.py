"""
IntentOS file_agent — Tool schemas for LLM planning

TOOL_SCHEMAS describes every primitive's name, description, and parameter
schema. Injected into the planner's system prompt so Claude knows what
tools it can compose into plans.
"""

TOOL_SCHEMAS = [
    {
        "name": "list_files",
        "description": "List files in a directory with metadata (name, path, size, modified date). Non-destructive.",
        "parameters": {
            "path": {"type": "string", "required": True, "description": "Directory path to list"},
            "extension": {"type": "string", "required": False, "description": "Filter by file extension (e.g. 'jpg', 'pdf')"},
            "recursive": {"type": "boolean", "required": False, "description": "Include files in subdirectories"},
        },
    },
    {
        "name": "find_files",
        "description": "Search for files by name pattern with optional filters (extension, size, date). Non-destructive.",
        "parameters": {
            "path": {"type": "string", "required": True, "description": "Directory path to search"},
            "pattern": {"type": "string", "required": False, "description": "Glob pattern to match filenames (e.g. '*.jpg')"},
            "extension": {"type": "string", "required": False, "description": "Filter by extension"},
            "modified_after": {"type": "string", "required": False, "description": "Only files modified after this date (YYYY-MM-DD)"},
            "modified_before": {"type": "string", "required": False, "description": "Only files modified before this date (YYYY-MM-DD)"},
            "size_gt": {"type": "integer", "required": False, "description": "Only files larger than this (bytes)"},
            "size_lt": {"type": "integer", "required": False, "description": "Only files smaller than this (bytes)"},
        },
    },
    {
        "name": "rename_file",
        "description": "Rename a single file. Provide the file path and the new name.",
        "parameters": {
            "path": {"type": "string", "required": True, "description": "Current file path"},
            "new_name": {"type": "string", "required": True, "description": "New filename (just the name, or a full path)"},
        },
    },
    {
        "name": "move_file",
        "description": "Move a file to a different directory.",
        "parameters": {
            "path": {"type": "string", "required": True, "description": "Current file path"},
            "destination": {"type": "string", "required": True, "description": "Destination path (directory or full path)"},
        },
    },
    {
        "name": "copy_file",
        "description": "Copy a file to a new location (preserves metadata).",
        "parameters": {
            "path": {"type": "string", "required": True, "description": "Source file path"},
            "destination": {"type": "string", "required": True, "description": "Destination path (directory or full path)"},
        },
    },
    {
        "name": "create_folder",
        "description": "Create a directory (including intermediate directories if needed).",
        "parameters": {
            "path": {"type": "string", "required": True, "description": "Directory path to create"},
        },
    },
    {
        "name": "delete_file",
        "description": "Permanently delete a file. Use with caution — always requires confirmation.",
        "parameters": {
            "path": {"type": "string", "required": True, "description": "File path to delete"},
        },
    },
    {
        "name": "read_file",
        "description": "Read the text content of a file (up to 1 MB). Useful for inspecting file contents before acting.",
        "parameters": {
            "path": {"type": "string", "required": True, "description": "File path to read"},
        },
    },
    {
        "name": "get_metadata",
        "description": "Get file or directory metadata (size, modified date, created date, type).",
        "parameters": {
            "path": {"type": "string", "required": True, "description": "File or directory path"},
        },
    },
    {
        "name": "get_disk_usage",
        "description": "Get disk usage for a file or directory (total size, file count, free disk space).",
        "parameters": {
            "path": {"type": "string", "required": True, "description": "File or directory path"},
        },
    },
]


def format_schemas_for_prompt() -> str:
    """Format TOOL_SCHEMAS into a human-readable string for the LLM prompt."""
    lines = []
    for tool in TOOL_SCHEMAS:
        lines.append(f"### {tool['name']}")
        lines.append(f"{tool['description']}")
        lines.append("Parameters:")
        for pname, pinfo in tool["parameters"].items():
            req = "required" if pinfo.get("required") else "optional"
            lines.append(f"  - {pname} ({pinfo['type']}, {req}): {pinfo['description']}")
        lines.append("")
    return "\n".join(lines)
