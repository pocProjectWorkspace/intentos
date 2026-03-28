"""
IntentOS Image Agent (Phase 2C.3)

ACP-compliant agent for image manipulation tasks.
Supports: get_info, resize, crop, convert_format, compress, remove_background (stub).

Entry point: run(input: dict) -> dict
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from PIL import Image

# ---------------------------------------------------------------------------
# Sensitive file patterns (mirrors file_agent)
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
]

_SENSITIVE_RE = [re.compile(p) for p in SENSITIVE_PATTERNS]

SUPPORTED_FORMATS = {"JPEG", "PNG", "GIF", "BMP", "TIFF", "WEBP"}

ACTIONS = {
    "get_info",
    "resize",
    "crop",
    "convert_format",
    "compress",
    "remove_background",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(code: str, message: str) -> dict:
    return {
        "status": "error",
        "action_performed": None,
        "result": None,
        "error": {"code": code, "message": message},
        "metadata": {
            "files_affected": 0,
            "bytes_affected": 0,
            "duration_ms": 0,
            "paths_accessed": [],
        },
    }


def _success(action: str, result: dict, metadata: dict) -> dict:
    return {
        "status": "success",
        "action_performed": action,
        "result": result,
        "metadata": metadata,
    }


def _is_sensitive(path: str) -> bool:
    name = Path(path).name
    for pat in _SENSITIVE_RE:
        if pat.search(name):
            return True
    return False


def _check_path(path: str, granted_paths: list[str]) -> str | None:
    """Return an error message if path is not under any granted path, else None."""
    real = os.path.realpath(path)
    for gp in granted_paths:
        if real.startswith(os.path.realpath(gp)):
            return None
    return f"Path not allowed: {path}"


def _output_path(context: dict, source_path: str, suffix: str = "", ext: str | None = None) -> str:
    """Build an output path inside workspace/outputs/."""
    workspace = context.get("workspace", ".")
    out_dir = os.path.join(workspace, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    base = Path(source_path).stem
    if ext is None:
        ext = Path(source_path).suffix
    if suffix:
        base = f"{base}_{suffix}"
    return os.path.join(out_dir, f"{base}{ext}")


def _format_to_ext(fmt: str) -> str:
    mapping = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "BMP": ".bmp", "TIFF": ".tiff", "WEBP": ".webp"}
    return mapping.get(fmt.upper(), f".{fmt.lower()}")


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _get_info(params: dict, context: dict, dry_run: bool) -> dict:
    path = params.get("path", "")
    if not os.path.isfile(path):
        return _error("FILE_NOT_FOUND", f"File not found: {path}")

    start = time.time()
    with Image.open(path) as img:
        info = {
            "width": img.width,
            "height": img.height,
            "format": img.format,
            "mode": img.mode,
            "file_size": os.path.getsize(path),
        }
    duration = int((time.time() - start) * 1000)
    return _success("get_info", info, {
        "files_affected": 0,
        "bytes_affected": 0,
        "duration_ms": duration,
        "paths_accessed": [path],
    })


def _resize(params: dict, context: dict, dry_run: bool) -> dict:
    path = params.get("path", "")
    width = params.get("width")
    height = params.get("height")

    if not os.path.isfile(path):
        return _error("FILE_NOT_FOUND", f"File not found: {path}")

    # Validate dimensions
    if width is not None and width <= 0:
        return _error("INVALID_DIMENSIONS", "Width must be a positive integer")
    if height is not None and height <= 0:
        return _error("INVALID_DIMENSIONS", "Height must be a positive integer")
    if width is None and height is None:
        return _error("INVALID_DIMENSIONS", "At least one of width or height is required")

    start = time.time()
    with Image.open(path) as img:
        orig_w, orig_h = img.size
        if width and not height:
            ratio = width / orig_w
            height = int(orig_h * ratio)
        elif height and not width:
            ratio = height / orig_h
            width = int(orig_w * ratio)

        if dry_run:
            duration = int((time.time() - start) * 1000)
            return _success("resize", {
                "description": f"Would resize {path} from {orig_w}x{orig_h} to {width}x{height}",
            }, {
                "files_affected": 0,
                "bytes_affected": 0,
                "duration_ms": duration,
                "paths_accessed": [path],
            })

        resized = img.resize((width, height), Image.LANCZOS)
        out = _output_path(context, path, suffix="resized")
        # Convert RGBA to RGB if saving as JPEG
        if resized.mode == "RGBA" and out.lower().endswith((".jpg", ".jpeg")):
            resized = resized.convert("RGB")
        resized.save(out)

    out_size = os.path.getsize(out)
    duration = int((time.time() - start) * 1000)
    return _success("resize", {
        "output_path": out,
        "width": width,
        "height": height,
    }, {
        "files_affected": 1,
        "bytes_affected": out_size,
        "duration_ms": duration,
        "paths_accessed": [path, out],
    })


def _crop(params: dict, context: dict, dry_run: bool) -> dict:
    path = params.get("path", "")
    box = params.get("box")  # [left, top, right, bottom]

    if not os.path.isfile(path):
        return _error("FILE_NOT_FOUND", f"File not found: {path}")
    if not box or len(box) != 4:
        return _error("INVALID_BOX", "Crop box must be [left, top, right, bottom]")

    start = time.time()
    left, top, right, bottom = box

    with Image.open(path) as img:
        w, h = img.size
        if right > w or bottom > h or left < 0 or top < 0:
            return _error("CROP_OUT_OF_BOUNDS", f"Crop box {box} exceeds image dimensions {w}x{h}")

        if dry_run:
            duration = int((time.time() - start) * 1000)
            return _success("crop", {
                "description": f"Would crop {path} to box {box} (result {right - left}x{bottom - top})",
            }, {
                "files_affected": 0,
                "bytes_affected": 0,
                "duration_ms": duration,
                "paths_accessed": [path],
            })

        cropped = img.crop((left, top, right, bottom))
        out = _output_path(context, path, suffix="cropped")
        cropped.save(out)

    out_size = os.path.getsize(out)
    duration = int((time.time() - start) * 1000)
    return _success("crop", {
        "output_path": out,
        "width": right - left,
        "height": bottom - top,
    }, {
        "files_affected": 1,
        "bytes_affected": out_size,
        "duration_ms": duration,
        "paths_accessed": [path, out],
    })


def _convert_format(params: dict, context: dict, dry_run: bool) -> dict:
    path = params.get("path", "")
    target_format = params.get("target_format", "").upper()

    if not os.path.isfile(path):
        return _error("FILE_NOT_FOUND", f"File not found: {path}")
    if target_format not in SUPPORTED_FORMATS:
        return _error("UNSUPPORTED_FORMAT", f"Unsupported format: {target_format}. Supported: {', '.join(sorted(SUPPORTED_FORMATS))}")

    start = time.time()

    if dry_run:
        duration = int((time.time() - start) * 1000)
        return _success("convert_format", {
            "description": f"Would convert {path} to {target_format}",
        }, {
            "files_affected": 0,
            "bytes_affected": 0,
            "duration_ms": duration,
            "paths_accessed": [path],
        })

    ext = _format_to_ext(target_format)
    out = _output_path(context, path, suffix="converted", ext=ext)

    with Image.open(path) as img:
        save_img = img
        # JPEG doesn't support alpha
        if target_format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
            save_img = img.convert("RGB")
        save_img.save(out, format=target_format)

    out_size = os.path.getsize(out)
    duration = int((time.time() - start) * 1000)
    return _success("convert_format", {
        "output_path": out,
        "target_format": target_format,
    }, {
        "files_affected": 1,
        "bytes_affected": out_size,
        "duration_ms": duration,
        "paths_accessed": [path, out],
    })


def _compress(params: dict, context: dict, dry_run: bool) -> dict:
    path = params.get("path", "")
    quality = params.get("quality", 75)

    if not os.path.isfile(path):
        return _error("FILE_NOT_FOUND", f"File not found: {path}")

    start = time.time()

    if dry_run:
        duration = int((time.time() - start) * 1000)
        return _success("compress", {
            "description": f"Would compress {path} with quality={quality}",
        }, {
            "files_affected": 0,
            "bytes_affected": 0,
            "duration_ms": duration,
            "paths_accessed": [path],
        })

    out = _output_path(context, path, suffix="compressed", ext=".jpg")

    with Image.open(path) as img:
        save_img = img
        if img.mode in ("RGBA", "P", "LA"):
            save_img = img.convert("RGB")
        elif img.mode != "RGB":
            save_img = img.convert("RGB")
        save_img.save(out, format="JPEG", quality=quality, optimize=True)

    out_size = os.path.getsize(out)
    duration = int((time.time() - start) * 1000)
    return _success("compress", {
        "output_path": out,
        "original_size": os.path.getsize(path),
        "compressed_size": out_size,
    }, {
        "files_affected": 1,
        "bytes_affected": out_size,
        "duration_ms": duration,
        "paths_accessed": [path, out],
    })


def _remove_background(params: dict, context: dict, dry_run: bool) -> dict:
    return _error("NOT_AVAILABLE", "Background removal is not yet available")


# ---------------------------------------------------------------------------
# Action dispatch table
# ---------------------------------------------------------------------------

_DISPATCH = {
    "get_info": _get_info,
    "resize": _resize,
    "crop": _crop,
    "convert_format": _convert_format,
    "compress": _compress,
    "remove_background": _remove_background,
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(input: dict) -> dict:
    """ACP entry point for the Image Agent."""
    action = input.get("action")
    params = input.get("params", {})
    context = input.get("context", {})
    dry_run = input.get("dry_run", False)

    # Unknown action
    if action not in _DISPATCH:
        return _error("UNKNOWN_ACTION", f"Unknown action: {action}")

    # Path enforcement
    path = params.get("path", "")
    granted_paths = context.get("granted_paths", [])
    if path and granted_paths:
        err = _check_path(path, granted_paths)
        if err:
            return _error("PATH_DENIED", err)

    # Sensitive file check
    if path and _is_sensitive(path):
        return _error("SENSITIVE_FILE", f"Sensitive file detected, operation blocked: {Path(path).name}")

    # Dispatch
    return _DISPATCH[action](params, context, dry_run)
