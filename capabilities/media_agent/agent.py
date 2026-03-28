"""
IntentOS Media Agent — audio/video operations via ffmpeg.

ACP-compliant agent that handles media operations:
- get_info: Retrieve media file metadata
- convert: Convert between media formats
- trim: Trim media to a time range
- extract_audio: Extract audio track from video
- compress: Compress media with quality control

All actions gracefully handle missing ffmpeg.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_FORMATS = {"mp4", "mkv", "avi", "mov", "mp3", "wav", "flac", "aac", "ogg", "webm"}

_ACTIONS = {"get_info", "convert", "trim", "extract_audio", "compress"}

_QUALITY_CRF = {
    "low": "32",
    "medium": "23",
    "high": "18",
}

# Regex for time validation: HH:MM:SS, MM:SS, or a number (seconds)
_TIME_RE = re.compile(
    r"^(?:\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2}|\d+(?:\.\d+)?)$"
)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _check_ffmpeg() -> bool:
    """Return True if ffmpeg is available on PATH."""
    return shutil.which("ffmpeg") is not None


def _check_ffprobe() -> bool:
    """Return True if ffprobe is available on PATH."""
    return shutil.which("ffprobe") is not None


def _error(code: str, message: str) -> dict:
    return {
        "status": "error",
        "action_performed": None,
        "result": None,
        "error": {"code": code, "message": message},
        "metadata": {"duration_ms": 0, "paths_accessed": []},
    }


def _success(action: str, result, metadata: dict) -> dict:
    return {
        "status": "success",
        "action_performed": action,
        "result": result,
        "metadata": metadata,
    }


def _validate_path(path: str, granted_paths: list[str]) -> str | None:
    """Return an error message if *path* is outside all granted_paths, else None."""
    resolved = str(Path(path).resolve())
    for gp in granted_paths:
        gp_resolved = str(Path(gp).resolve())
        if resolved == gp_resolved or resolved.startswith(gp_resolved + os.sep):
            return None
    return f"Path '{path}' is outside granted paths"


def _validate_time(t: str) -> bool:
    """Return True if *t* matches an accepted time format."""
    return bool(_TIME_RE.match(t))


def _output_path(workspace: str, source: str, suffix: str) -> str:
    """Build an output path inside workspace/outputs/."""
    out_dir = os.path.join(workspace, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    stem = Path(source).stem
    return os.path.join(out_dir, f"{stem}{suffix}")


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def _handle_get_info(params: dict, context: dict) -> dict:
    path = params.get("path")
    if not path:
        return _error("MISSING_PARAM", "get_info requires a 'path' parameter")

    granted = context.get("granted_paths", [])
    err = _validate_path(path, granted)
    if err:
        return _error("PATH_DENIED", err)

    if not os.path.exists(path):
        return _error("FILE_NOT_FOUND", f"File not found: {path}")

    dry_run = context.get("dry_run", False)
    if dry_run:
        return _success("get_info", f"Would retrieve media info for: {path}", {
            "duration_ms": 0,
            "paths_accessed": [path],
            "dry_run": True,
        })

    if not _check_ffprobe():
        return _error(
            "TOOL_NOT_INSTALLED",
            "Media tools are not installed on this system. "
            "Media processing requires ffmpeg. Install it with: "
            "brew install ffmpeg (macOS) or apt install ffmpeg (Linux)",
        )

    # Real execution with ffprobe
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return _error("FFPROBE_FAILED", result.stderr.strip() or "ffprobe failed")
        import json
        info = json.loads(result.stdout)
        return _success("get_info", info, {
            "duration_ms": 0,
            "paths_accessed": [path],
        })
    except Exception as exc:
        return _error("FFPROBE_FAILED", str(exc))


def _handle_convert(params: dict, context: dict) -> dict:
    path = params.get("path")
    target_format = params.get("target_format")

    if not path:
        return _error("MISSING_PARAM", "convert requires a 'path' parameter")
    if not target_format:
        return _error("MISSING_PARAM", "convert requires a 'target_format' parameter")

    target_format = target_format.lower().lstrip(".")
    if target_format not in SUPPORTED_FORMATS:
        return _error(
            "UNSUPPORTED_FORMAT",
            f"Unsupported format '{target_format}'. "
            f"Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}",
        )

    granted = context.get("granted_paths", [])
    err = _validate_path(path, granted)
    if err:
        return _error("PATH_DENIED", err)

    workspace = context.get("workspace", ".")
    out = _output_path(workspace, path, f".{target_format}")

    dry_run = context.get("dry_run", False)
    if dry_run:
        return _success("convert", f"Would convert {path} to {target_format} -> {out}", {
            "duration_ms": 0,
            "paths_accessed": [path],
            "output_path": out,
            "dry_run": True,
        })

    if not _check_ffmpeg():
        return _error(
            "TOOL_NOT_INSTALLED",
            "Media processing requires ffmpeg. Install it with: "
            "brew install ffmpeg (macOS) or apt install ffmpeg (Linux)",
        )

    if not os.path.exists(path):
        return _error("FILE_NOT_FOUND", f"File not found: {path}")

    try:
        t0 = time.time()
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", path, out],
            capture_output=True, text=True, timeout=300,
        )
        elapsed = int((time.time() - t0) * 1000)
        if result.returncode != 0:
            return _error("FFMPEG_FAILED", result.stderr.strip() or "ffmpeg conversion failed")
        return _success("convert", {"output_path": out}, {
            "duration_ms": elapsed,
            "paths_accessed": [path, out],
        })
    except Exception as exc:
        return _error("FFMPEG_FAILED", str(exc))


def _handle_trim(params: dict, context: dict) -> dict:
    path = params.get("path")
    if not path:
        return _error("MISSING_PARAM", "trim requires a 'path' parameter")

    start_time = params.get("start_time")
    end_time = params.get("end_time")

    if not start_time and not end_time:
        return _error("MISSING_PARAM", "trim requires at least one of 'start_time' or 'end_time'")

    if start_time and not _validate_time(start_time):
        return _error("INVALID_TIME", f"Invalid time format: '{start_time}'. Use HH:MM:SS, MM:SS, or seconds")
    if end_time and not _validate_time(end_time):
        return _error("INVALID_TIME", f"Invalid time format: '{end_time}'. Use HH:MM:SS, MM:SS, or seconds")

    granted = context.get("granted_paths", [])
    err = _validate_path(path, granted)
    if err:
        return _error("PATH_DENIED", err)

    ext = Path(path).suffix or ".mp4"
    workspace = context.get("workspace", ".")
    out = _output_path(workspace, path, f"_trimmed{ext}")

    dry_run = context.get("dry_run", False)
    if dry_run:
        desc = f"Would trim {path}"
        if start_time:
            desc += f" from {start_time}"
        if end_time:
            desc += f" to {end_time}"
        desc += f" -> {out}"
        return _success("trim", desc, {
            "duration_ms": 0,
            "paths_accessed": [path],
            "output_path": out,
            "dry_run": True,
        })

    if not _check_ffmpeg():
        return _error(
            "TOOL_NOT_INSTALLED",
            "Media processing requires ffmpeg. Install it with: "
            "brew install ffmpeg (macOS) or apt install ffmpeg (Linux)",
        )

    if not os.path.exists(path):
        return _error("FILE_NOT_FOUND", f"File not found: {path}")

    cmd = ["ffmpeg", "-y", "-i", path]
    if start_time:
        cmd += ["-ss", start_time]
    if end_time:
        cmd += ["-to", end_time]
    cmd += ["-c", "copy", out]

    try:
        t0 = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        elapsed = int((time.time() - t0) * 1000)
        if result.returncode != 0:
            return _error("FFMPEG_FAILED", result.stderr.strip() or "ffmpeg trim failed")
        return _success("trim", {"output_path": out}, {
            "duration_ms": elapsed,
            "paths_accessed": [path, out],
        })
    except Exception as exc:
        return _error("FFMPEG_FAILED", str(exc))


def _handle_extract_audio(params: dict, context: dict) -> dict:
    path = params.get("path")
    if not path:
        return _error("MISSING_PARAM", "extract_audio requires a 'path' parameter")

    granted = context.get("granted_paths", [])
    err = _validate_path(path, granted)
    if err:
        return _error("PATH_DENIED", err)

    audio_format = params.get("format", "mp3")
    workspace = context.get("workspace", ".")
    out = _output_path(workspace, path, f".{audio_format}")

    dry_run = context.get("dry_run", False)
    if dry_run:
        return _success("extract_audio", f"Would extract audio from {path} -> {out}", {
            "duration_ms": 0,
            "paths_accessed": [path],
            "output_path": out,
            "dry_run": True,
        })

    if not _check_ffmpeg():
        return _error(
            "TOOL_NOT_INSTALLED",
            "Media processing requires ffmpeg. Install it with: "
            "brew install ffmpeg (macOS) or apt install ffmpeg (Linux)",
        )

    if not os.path.exists(path):
        return _error("FILE_NOT_FOUND", f"File not found: {path}")

    try:
        t0 = time.time()
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-vn", "-acodec", "libmp3lame", out],
            capture_output=True, text=True, timeout=300,
        )
        elapsed = int((time.time() - t0) * 1000)
        if result.returncode != 0:
            return _error("FFMPEG_FAILED", result.stderr.strip() or "ffmpeg extraction failed")
        return _success("extract_audio", {"output_path": out}, {
            "duration_ms": elapsed,
            "paths_accessed": [path, out],
        })
    except Exception as exc:
        return _error("FFMPEG_FAILED", str(exc))


def _handle_compress(params: dict, context: dict) -> dict:
    path = params.get("path")
    if not path:
        return _error("MISSING_PARAM", "compress requires a 'path' parameter")

    granted = context.get("granted_paths", [])
    err = _validate_path(path, granted)
    if err:
        return _error("PATH_DENIED", err)

    quality = params.get("quality", "medium").lower()
    if quality not in _QUALITY_CRF:
        return _error("INVALID_PARAM", f"Quality must be one of: low, medium, high (got '{quality}')")

    ext = Path(path).suffix or ".mp4"
    workspace = context.get("workspace", ".")
    out = _output_path(workspace, path, f"_compressed{ext}")

    dry_run = context.get("dry_run", False)
    if dry_run:
        return _success("compress", f"Would compress {path} at {quality} quality -> {out}", {
            "duration_ms": 0,
            "paths_accessed": [path],
            "output_path": out,
            "dry_run": True,
        })

    if not _check_ffmpeg():
        return _error(
            "TOOL_NOT_INSTALLED",
            "Media processing requires ffmpeg. Install it with: "
            "brew install ffmpeg (macOS) or apt install ffmpeg (Linux)",
        )

    if not os.path.exists(path):
        return _error("FILE_NOT_FOUND", f"File not found: {path}")

    crf = _QUALITY_CRF[quality]
    try:
        t0 = time.time()
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-crf", crf, out],
            capture_output=True, text=True, timeout=300,
        )
        elapsed = int((time.time() - t0) * 1000)
        if result.returncode != 0:
            return _error("FFMPEG_FAILED", result.stderr.strip() or "ffmpeg compression failed")
        return _success("compress", {"output_path": out}, {
            "duration_ms": elapsed,
            "paths_accessed": [path, out],
        })
    except Exception as exc:
        return _error("FFMPEG_FAILED", str(exc))


# ---------------------------------------------------------------------------
# Action dispatch
# ---------------------------------------------------------------------------

_DISPATCH = {
    "get_info": _handle_get_info,
    "convert": _handle_convert,
    "trim": _handle_trim,
    "extract_audio": _handle_extract_audio,
    "compress": _handle_compress,
}


# ---------------------------------------------------------------------------
# ACP Entry Point
# ---------------------------------------------------------------------------

def run(input: dict) -> dict:
    """
    ACP entry point for the Media Agent.

    Input shape:
        {
            "action": str,
            "params": dict,
            "context": {
                "granted_paths": list[str],
                "workspace": str,
                "dry_run": bool (optional),
                ...
            }
        }
    """
    action = input.get("action")
    params = input.get("params", {})
    context = input.get("context", {})

    if action not in _DISPATCH:
        return _error("UNKNOWN_ACTION", f"Unknown action: '{action}'")

    return _DISPATCH[action](params, context)
