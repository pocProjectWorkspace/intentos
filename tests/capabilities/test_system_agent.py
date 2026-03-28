"""Tests for the expanded system_agent capability."""

from __future__ import annotations

import re
import sys
import os

import pytest

# Ensure project root is on sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from capabilities.system_agent.agent import run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_action(action: str, params: dict | None = None, dry_run: bool = False) -> dict:
    inp: dict = {"action": action}
    if params:
        inp["params"] = params
    if dry_run:
        inp["context"] = {"dry_run": True}
    return run(inp)


def _assert_success(result: dict):
    assert result["status"] == "success", f"Expected success, got: {result}"
    assert "metadata" in result
    assert "action_performed" in result


# ---------------------------------------------------------------------------
# 1. get_current_date returns valid date string
# ---------------------------------------------------------------------------

def test_get_current_date_default():
    res = _run_action("get_current_date")
    _assert_success(res)
    # Should match YYYY-MM-DD pattern
    assert re.match(r"\d{4}-\d{2}-\d{2}", res["result"])


# ---------------------------------------------------------------------------
# 2. get_current_date with custom format
# ---------------------------------------------------------------------------

def test_get_current_date_custom_format():
    res = _run_action("get_current_date", {"format": "DD/MM/YYYY"})
    _assert_success(res)
    assert re.match(r"\d{2}/\d{2}/\d{4}", res["result"])


# ---------------------------------------------------------------------------
# 3. get_disk_usage returns total/used/free/percent
# ---------------------------------------------------------------------------

def test_get_disk_usage():
    res = _run_action("get_disk_usage")
    _assert_success(res)
    result = res["result"]
    assert "total_gb" in result
    assert "used_gb" in result
    assert "free_gb" in result
    assert "percent_used" in result
    assert result["total_gb"] > 0
    assert 0 <= result["percent_used"] <= 100


# ---------------------------------------------------------------------------
# 4. get_system_info returns platform, arch, hostname, cpu_count, ram_gb
# ---------------------------------------------------------------------------

def test_get_system_info():
    res = _run_action("get_system_info")
    _assert_success(res)
    result = res["result"]
    assert "platform" in result
    assert "arch" in result
    assert "hostname" in result
    assert "python_version" in result
    assert "cpu_count" in result
    assert result["cpu_count"] >= 1
    assert "ram_gb" in result


# ---------------------------------------------------------------------------
# 5. get_process_list returns list of processes
# ---------------------------------------------------------------------------

def test_get_process_list():
    res = _run_action("get_process_list")
    if res["status"] == "error" and "not available" in res["error"]["message"].lower():
        pytest.skip("ps command not available on this platform")
    _assert_success(res)
    assert isinstance(res["result"], list)
    if res["result"]:
        proc = res["result"][0]
        assert "name" in proc
        assert "pid" in proc
        assert "memory_percent" in proc


# ---------------------------------------------------------------------------
# 6. get_network_info returns hostname and IPs
# ---------------------------------------------------------------------------

def test_get_network_info():
    res = _run_action("get_network_info")
    _assert_success(res)
    result = res["result"]
    assert "hostname" in result
    assert "local_ips" in result
    assert isinstance(result["local_ips"], list)
    assert len(result["local_ips"]) >= 1


# ---------------------------------------------------------------------------
# 7. get_hardware_profile returns GPU/RAM/CPU info
# ---------------------------------------------------------------------------

def test_get_hardware_profile():
    res = _run_action("get_hardware_profile")
    # May error if HardwareDetector is unavailable; both cases acceptable
    if res["status"] == "error":
        assert "HARDWARE" in res["error"]["code"]
    else:
        _assert_success(res)
        result = res["result"]
        assert "ram_gb" in result
        assert "cpu_cores" in result
        assert "cpu_model" in result
        assert "platform" in result


# ---------------------------------------------------------------------------
# 8. get_intentos_status returns version and workspace
# ---------------------------------------------------------------------------

def test_get_intentos_status():
    res = _run_action("get_intentos_status")
    _assert_success(res)
    result = res["result"]
    assert "version" in result
    assert "workspace_path" in result
    assert "agents_available" in result
    assert isinstance(result["agents_available"], list)
    assert "uptime_seconds" in result


# ---------------------------------------------------------------------------
# 9. Unknown action returns error
# ---------------------------------------------------------------------------

def test_unknown_action():
    res = _run_action("totally_bogus_action")
    assert res["status"] == "error"
    assert res["error"]["code"] == "UNKNOWN_ACTION"
    assert "totally_bogus_action" in res["error"]["message"]


# ---------------------------------------------------------------------------
# 10. dry_run on each action returns description without side effects
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", [
    "get_current_date",
    "get_disk_usage",
    "get_system_info",
    "get_process_list",
    "get_network_info",
    "get_hardware_profile",
    "get_intentos_status",
])
def test_dry_run(action):
    res = _run_action(action, dry_run=True)
    _assert_success(res)
    # dry_run should contain "Would" in action_performed
    assert "Would" in res["action_performed"] or "would" in res["action_performed"].lower()
    assert "metadata" in res


# ---------------------------------------------------------------------------
# 11. Metadata always present
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", [
    "get_current_date",
    "get_disk_usage",
    "get_system_info",
    "get_process_list",
    "get_network_info",
    "get_hardware_profile",
    "get_intentos_status",
])
def test_metadata_always_present(action):
    res = _run_action(action)
    assert "metadata" in res
    meta = res["metadata"]
    assert "files_affected" in meta
    assert "bytes_affected" in meta
    assert "duration_ms" in meta
    assert "paths_accessed" in meta
