"""Tests for the CLI commands module."""

from __future__ import annotations

import os
import sys

import pytest

# Ensure project root is on sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.cli import CLICommands


# ---------------------------------------------------------------------------
# Fixture: CLI with no kernel (standalone mode)
# ---------------------------------------------------------------------------

@pytest.fixture
def cli():
    return CLICommands(kernel=None)


# ---------------------------------------------------------------------------
# 1. handle("status") returns hardware/model/mode info
# ---------------------------------------------------------------------------

def test_cmd_status(cli):
    output = cli.handle("status")
    assert "IntentOS Status" in output
    assert "Hardware" in output
    assert "Model" in output
    assert "Mode" in output
    assert "Cost" in output


# ---------------------------------------------------------------------------
# 2. handle("cost") returns cost breakdown
# ---------------------------------------------------------------------------

def test_cmd_cost(cli):
    output = cli.handle("cost")
    assert "Cost Breakdown" in output
    assert "Total" in output


# ---------------------------------------------------------------------------
# 3. handle("history") returns recent tasks
# ---------------------------------------------------------------------------

def test_cmd_history(cli):
    output = cli.handle("history")
    assert "Recent Tasks" in output


# ---------------------------------------------------------------------------
# 4. handle("credentials") returns credential names
# ---------------------------------------------------------------------------

def test_cmd_credentials(cli):
    output = cli.handle("credentials")
    assert "Credentials" in output


# ---------------------------------------------------------------------------
# 5. handle("security") returns security stats
# ---------------------------------------------------------------------------

def test_cmd_security(cli):
    output = cli.handle("security")
    assert "Security Pipeline" in output
    assert "Tasks scanned" in output
    assert "Threats blocked" in output


# ---------------------------------------------------------------------------
# 6. handle("help") lists all commands
# ---------------------------------------------------------------------------

def test_cmd_help(cli):
    output = cli.handle("help")
    assert "IntentOS Commands" in output
    # Every registered command should appear
    for cmd in ["status", "cost", "history", "credentials", "security", "help", "hardware"]:
        assert f"!{cmd}" in output


# ---------------------------------------------------------------------------
# 7. handle("hardware") returns hardware profile
# ---------------------------------------------------------------------------

def test_cmd_hardware(cli):
    output = cli.handle("hardware")
    assert "Hardware Profile" in output


# ---------------------------------------------------------------------------
# 8. handle("unknown_cmd") returns unknown command message
# ---------------------------------------------------------------------------

def test_cmd_unknown(cli):
    output = cli.handle("unknown_cmd")
    assert "Unknown command" in output
    assert "!help" in output


# ---------------------------------------------------------------------------
# 9. handle("") returns help
# ---------------------------------------------------------------------------

def test_cmd_empty_returns_help(cli):
    output = cli.handle("")
    assert "IntentOS Commands" in output


# ---------------------------------------------------------------------------
# Additional: kernel integration mock
# ---------------------------------------------------------------------------

def test_status_with_kernel(cli):
    """When a kernel object is provided, status pulls data from it."""

    class FakeKernel:
        model = "llama3.1:8b"
        mode = "batch"
        total_cost = 1.2345

    cli.kernel = FakeKernel()
    output = cli.handle("status")
    assert "llama3.1:8b" in output
    assert "batch" in output
    assert "1.2345" in output


def test_history_with_kernel(cli):
    """When kernel has task_history, history command shows them."""

    class FakeKernel:
        task_history = [
            {"status": "done", "intent": "file.rename", "timestamp": "12:00"},
            {"status": "error", "intent": "image.resize", "timestamp": "12:05"},
        ]

    cli.kernel = FakeKernel()
    output = cli.handle("history")
    assert "file.rename" in output
    assert "image.resize" in output


def test_cost_with_kernel(cli):
    """When kernel has cost_breakdown, cost command shows detail."""

    class FakeKernel:
        total_cost = 0.55
        cost_breakdown = [
            {"model": "claude-sonnet", "cost": 0.45, "tasks": 3},
            {"model": "llama3.1:8b", "cost": 0.10, "tasks": 7},
        ]

    cli.kernel = FakeKernel()
    output = cli.handle("cost")
    assert "claude-sonnet" in output
    assert "llama3.1:8b" in output
    assert "0.5500" in output
