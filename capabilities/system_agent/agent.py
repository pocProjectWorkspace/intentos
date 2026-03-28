"""
IntentOS system_agent — System information capability

Actions: get_current_date, get_disk_usage, get_system_info,
         get_process_list, get_network_info, get_hardware_profile,
         get_intentos_status
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime


# ---------------------------------------------------------------------------
# Version constant
# ---------------------------------------------------------------------------
__version__ = "0.3.0"

# ---------------------------------------------------------------------------
# Metadata helpers
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
# Actions
# ---------------------------------------------------------------------------


def _get_current_date(params: dict, context: dict) -> dict:
    """Return the current date in the requested format."""
    t0 = time.monotonic()
    fmt = params.get("format", "YYYY-MM-DD")

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would return today's date in {fmt} format",
            "result": {"preview": f"Current date in {fmt}"},
            "metadata": _meta(),
        }

    now = datetime.now()

    # Translate common format tokens to Python strftime
    py_fmt = (
        fmt.replace("YYYY", "%Y")
        .replace("YY", "%y")
        .replace("MM", "%m")
        .replace("DD", "%d")
        .replace("HH", "%H")
        .replace("mm", "%M")
        .replace("ss", "%S")
    )

    try:
        formatted = now.strftime(py_fmt)
    except ValueError:
        formatted = now.strftime("%Y-%m-%d")

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Retrieved current date: {formatted}",
        "result": formatted,
        "metadata": _meta(duration_ms=elapsed),
    }


def _get_disk_usage(params: dict, context: dict) -> dict:
    """Return disk usage stats for a given path."""
    t0 = time.monotonic()
    path = params.get("path", "/")

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": f"Would report disk usage for '{path}'",
            "result": {"preview": f"Disk usage for {path}"},
            "metadata": _meta(),
        }

    try:
        usage = shutil.disk_usage(path)
        total_gb = round(usage.total / (1024 ** 3), 2)
        used_gb = round(usage.used / (1024 ** 3), 2)
        free_gb = round(usage.free / (1024 ** 3), 2)
        percent_used = round((usage.used / usage.total) * 100, 1)

        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "status": "success",
            "action_performed": f"Retrieved disk usage for {path}",
            "result": {
                "total_gb": total_gb,
                "used_gb": used_gb,
                "free_gb": free_gb,
                "percent_used": percent_used,
            },
            "metadata": _meta(duration_ms=elapsed, paths_accessed=[path]),
        }
    except OSError as exc:
        return _error("DISK_ERROR", f"Cannot read disk usage for '{path}': {exc}")


def _get_system_info(params: dict, context: dict) -> dict:
    """Return basic system information."""
    t0 = time.monotonic()

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": "Would return system platform, arch, hostname, python version, CPU count, and RAM",
            "result": {"preview": "System information summary"},
            "metadata": _meta(),
        }

    cpu_count = os.cpu_count() or 1

    # Detect RAM — try psutil first, then platform-specific fallbacks
    ram_gb: float = 0.0
    try:
        import psutil  # type: ignore
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 2)
    except ImportError:
        try:
            if sys.platform == "darwin":
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    ram_gb = round(int(result.stdout.strip()) / (1024 ** 3), 2)
            elif sys.platform == "linux":
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemTotal"):
                            kb = int(line.split()[1])
                            ram_gb = round(kb / (1024 ** 2), 2)
                            break
        except Exception:
            pass

    if ram_gb == 0.0:
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            ram_gb = round((pages * page_size) / (1024 ** 3), 2)
        except (ValueError, OSError, AttributeError):
            ram_gb = -1.0  # unknown

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": "Retrieved system information",
        "result": {
            "platform": sys.platform,
            "arch": platform.machine(),
            "hostname": socket.gethostname(),
            "python_version": platform.python_version(),
            "cpu_count": cpu_count,
            "ram_gb": ram_gb,
        },
        "metadata": _meta(duration_ms=elapsed),
    }


def _get_process_list(params: dict, context: dict) -> dict:
    """Return top 10 processes by memory usage (Unix only)."""
    t0 = time.monotonic()
    name_filter = params.get("filter", None)

    if context.get("dry_run"):
        desc = "Would list top 10 processes by memory usage"
        if name_filter:
            desc += f" filtered by '{name_filter}'"
        return {
            "status": "success",
            "action_performed": desc,
            "result": {"preview": desc},
            "metadata": _meta(),
        }

    try:
        result = subprocess.run(
            ["ps", "aux", "--sort=-%mem"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            # macOS ps does not support --sort; fall back
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True, text=True, timeout=10,
            )
    except FileNotFoundError:
        return _error("PS_NOT_AVAILABLE", "The 'ps' command is not available on this system.")
    except Exception as exc:
        return _error("PROCESS_ERROR", f"Failed to list processes: {exc}")

    if result.returncode != 0:
        return _error("PROCESS_ERROR", f"ps command failed: {result.stderr.strip()}")

    lines = result.stdout.strip().split("\n")
    # Skip header
    entries = []
    for line in lines[1:]:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        pid = int(parts[1])
        mem_pct = float(parts[3])
        name = parts[10]
        if name_filter and name_filter.lower() not in name.lower():
            continue
        entries.append({"name": name, "pid": pid, "memory_percent": mem_pct})

    # Sort by memory descending and take top 10
    entries.sort(key=lambda x: x["memory_percent"], reverse=True)
    top10 = entries[:10]

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": f"Listed top {len(top10)} processes by memory usage",
        "result": top10,
        "metadata": _meta(duration_ms=elapsed),
    }


def _get_network_info(params: dict, context: dict) -> dict:
    """Return hostname and local IP addresses."""
    t0 = time.monotonic()

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": "Would return hostname and local IP addresses",
            "result": {"preview": "Network information summary"},
            "metadata": _meta(),
        }

    hostname = socket.gethostname()

    # Collect all local IPs
    local_ips: list[str] = []
    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
        for info in addr_infos:
            ip = info[4][0]
            if ip not in local_ips:
                local_ips.append(ip)
    except socket.gaierror:
        pass

    # Fallback: connect to an external address to find the primary IP
    if not local_ips:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ips.append(s.getsockname()[0])
        except Exception:
            local_ips.append("127.0.0.1")

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": "Retrieved network information",
        "result": {
            "hostname": hostname,
            "local_ips": local_ips,
        },
        "metadata": _meta(duration_ms=elapsed),
    }


def _get_hardware_profile(params: dict, context: dict) -> dict:
    """Return GPU, RAM, and CPU info via HardwareDetector."""
    t0 = time.monotonic()

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": "Would detect hardware profile (GPU, RAM, CPU)",
            "result": {"preview": "Hardware profile detection"},
            "metadata": _meta(),
        }

    try:
        from core.inference.hardware import HardwareDetector

        detector = HardwareDetector()
        profile = detector.detect()
        profile_dict = profile.to_dict()

        elapsed = int((time.monotonic() - t0) * 1000)
        return {
            "status": "success",
            "action_performed": "Detected hardware profile",
            "result": profile_dict,
            "metadata": _meta(duration_ms=elapsed),
        }
    except ImportError:
        return _error(
            "HARDWARE_UNAVAILABLE",
            "HardwareDetector is not available. Ensure core.inference.hardware is installed.",
        )
    except Exception as exc:
        return _error("HARDWARE_ERROR", f"Hardware detection failed: {exc}")


def _get_intentos_status(params: dict, context: dict) -> dict:
    """Return IntentOS status: version, workspace, agents, uptime."""
    t0 = time.monotonic()

    if context.get("dry_run"):
        return {
            "status": "success",
            "action_performed": "Would report IntentOS status (version, workspace, agents, uptime)",
            "result": {"preview": "IntentOS status summary"},
            "metadata": _meta(),
        }

    # Workspace path
    workspace = os.environ.get(
        "INTENTOS_WORKSPACE",
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )

    # Discover available agents
    agents_dir = os.path.join(workspace, "capabilities")
    agents_available: list[str] = []
    if os.path.isdir(agents_dir):
        for entry in sorted(os.listdir(agents_dir)):
            agent_path = os.path.join(agents_dir, entry, "agent.py")
            if os.path.isfile(agent_path):
                agents_available.append(entry)

    # Simple uptime: seconds since the Python process started
    try:
        import_time = time.monotonic()
        uptime_seconds = round(import_time, 1)
    except Exception:
        uptime_seconds = -1

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "success",
        "action_performed": "Retrieved IntentOS status",
        "result": {
            "version": __version__,
            "workspace_path": workspace,
            "agents_available": agents_available,
            "uptime_seconds": uptime_seconds,
        },
        "metadata": _meta(duration_ms=elapsed),
    }


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

_ACTIONS = {
    "get_current_date": _get_current_date,
    "get_disk_usage": _get_disk_usage,
    "get_system_info": _get_system_info,
    "get_process_list": _get_process_list,
    "get_network_info": _get_network_info,
    "get_hardware_profile": _get_hardware_profile,
    "get_intentos_status": _get_intentos_status,
}


def run(input: dict) -> dict:
    action = input.get("action")
    params = input.get("params", {})
    context = input.get("context", {})

    handler = _ACTIONS.get(action)
    if handler is None:
        return _error("UNKNOWN_ACTION", f"I don't know how to do '{action}'")

    return handler(params, context)
