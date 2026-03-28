"""Tests for the Agent Scheduler — Phase 2C.6."""

import time
import pytest
from unittest.mock import patch, MagicMock

from core.orchestration.scheduler import (
    AgentManifest,
    AgentScheduler,
    ExecutionResult,
)


# ---------------------------------------------------------------------------
# Helpers — mock agent handlers
# ---------------------------------------------------------------------------

def _echo_agent(input_dict, context):
    """Returns input as output."""
    return {"echoed": input_dict}


def _slow_agent(input_dict, context):
    """Sleeps longer than typical timeout."""
    time.sleep(5)
    return {"done": True}


def _failing_agent(input_dict, context):
    """Raises an exception."""
    raise RuntimeError("something broke inside the agent")


def _non_dict_agent(input_dict, context):
    """Returns a string instead of dict."""
    return "I am not a dict"


def _action_aware_agent(input_dict, context):
    """Returns the action from input."""
    return {"action_done": input_dict.get("action", "none")}


def _make_manifest(
    name="test_agent",
    actions=None,
    permissions=None,
    sandbox_policy="WorkspaceWrite",
    version="1.0",
):
    return AgentManifest(
        name=name,
        version=version,
        actions=actions or ["read_file", "write_file"],
        permissions=permissions or ["/tmp/test_workspace"],
        sandbox_policy=sandbox_policy,
    )


# ---------------------------------------------------------------------------
# Agent Registration
# ---------------------------------------------------------------------------

class TestAgentRegistration:
    """1-4: Agent registration lifecycle."""

    def test_register_agent(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        manifest = _make_manifest()
        scheduler.register_agent("test_agent", _echo_agent, manifest)
        assert scheduler.is_registered("test_agent")

    def test_is_registered_false_for_unknown(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        assert scheduler.is_registered("ghost") is False

    def test_list_agents(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("a", _echo_agent, _make_manifest(name="a"))
        scheduler.register_agent("b", _echo_agent, _make_manifest(name="b"))
        assert sorted(scheduler.list_agents()) == ["a", "b"]

    def test_re_register_overwrites(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        manifest = _make_manifest()
        scheduler.register_agent("test_agent", _echo_agent, manifest)
        scheduler.register_agent("test_agent", _failing_agent, manifest)
        # The handler should now be _failing_agent
        result = scheduler.execute("test_agent", {}, {"action": "read_file"})
        assert result.status == "error"


# ---------------------------------------------------------------------------
# Execution — Single Agent
# ---------------------------------------------------------------------------

class TestSingleExecution:
    """5-7: Single agent execution."""

    def test_execute_returns_result(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("echo", _echo_agent, _make_manifest(name="echo"))
        result = scheduler.execute("echo", {"msg": "hi"}, {"action": "read_file"})
        assert result.status == "success"
        assert result.output["echoed"] == {"msg": "hi"}

    def test_result_includes_metadata(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("echo", _echo_agent, _make_manifest(name="echo"))
        result = scheduler.execute("echo", {"msg": "hi"}, {"action": "read_file"})
        assert result.agent_name == "echo"
        assert isinstance(result.duration_ms, (int, float))
        assert result.duration_ms >= 0

    def test_unknown_agent_returns_error(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        result = scheduler.execute("ghost", {}, {"action": "read_file"})
        assert result.status == "error"
        assert result.error_code == "AGENT_NOT_AVAILABLE"


# ---------------------------------------------------------------------------
# Execution — Sequential
# ---------------------------------------------------------------------------

class TestSequentialExecution:
    """8-11: Sequential subtask execution."""

    def _setup_scheduler(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("echo", _echo_agent, _make_manifest(name="echo"))
        scheduler.register_agent("fail", _failing_agent, _make_manifest(name="fail"))
        return scheduler

    def test_sequential_runs_in_order(self):
        scheduler = self._setup_scheduler()
        subtasks = [
            {"id": "1", "agent": "echo", "action": "read_file", "params": {"x": 1}},
            {"id": "2", "agent": "echo", "action": "read_file", "params": {"x": 2}},
        ]
        results = scheduler.execute_sequential(subtasks, {})
        assert len(results) == 2
        assert results[0].status == "success"
        assert results[1].status == "success"

    def test_sequential_results_accessible_by_id(self):
        scheduler = self._setup_scheduler()
        subtasks = [
            {"id": "s1", "agent": "echo", "action": "read_file", "params": {"v": 10}},
        ]
        results = scheduler.execute_sequential(subtasks, {})
        assert results[0].subtask_id == "s1"

    def test_sequential_failure_stops_execution(self):
        scheduler = self._setup_scheduler()
        subtasks = [
            {"id": "1", "agent": "fail", "action": "read_file", "params": {}},
            {"id": "2", "agent": "echo", "action": "read_file", "params": {}},
        ]
        results = scheduler.execute_sequential(subtasks, {})
        assert results[0].status == "error"
        assert results[1].status == "skipped"

    def test_sequential_reference_resolution(self):
        scheduler = self._setup_scheduler()
        subtasks = [
            {"id": "1", "agent": "echo", "action": "read_file", "params": {"val": "hello"}},
            {"id": "2", "agent": "echo", "action": "read_file", "params": {"prev": "{{1.result}}"}},
        ]
        results = scheduler.execute_sequential(subtasks, {})
        assert results[1].status == "success"
        # The second subtask should receive the resolved result of the first
        output = results[1].output
        assert "echoed" in output
        assert "prev" in output["echoed"]


# ---------------------------------------------------------------------------
# Execution — Parallel
# ---------------------------------------------------------------------------

class TestParallelExecution:
    """12-14: Parallel subtask execution."""

    def test_parallel_runs_subtasks(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("echo", _echo_agent, _make_manifest(name="echo"))
        subtasks = [
            {"id": "p1", "agent": "echo", "action": "read_file", "params": {"n": 1}},
            {"id": "p2", "agent": "echo", "action": "read_file", "params": {"n": 2}},
        ]
        results = scheduler.execute_parallel(subtasks, {})
        assert len(results) == 2
        statuses = {r.status for r in results}
        assert "success" in statuses

    def test_parallel_returns_all_even_on_failure(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("echo", _echo_agent, _make_manifest(name="echo"))
        scheduler.register_agent("fail", _failing_agent, _make_manifest(name="fail"))
        subtasks = [
            {"id": "p1", "agent": "echo", "action": "read_file", "params": {}},
            {"id": "p2", "agent": "fail", "action": "read_file", "params": {}},
        ]
        results = scheduler.execute_parallel(subtasks, {})
        assert len(results) == 2
        statuses = {r.status for r in results}
        assert "success" in statuses
        assert "error" in statuses

    @patch("core.orchestration.scheduler.ThreadPoolExecutor")
    def test_parallel_uses_thread_pool(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_pool.__enter__ = MagicMock(return_value=mock_pool)
        mock_pool.__exit__ = MagicMock(return_value=False)
        mock_future = MagicMock()
        mock_future.result.return_value = ExecutionResult(
            agent_name="echo", action="read_file", status="success",
            output={"ok": True}, duration_ms=1, subtask_id="p1",
        )
        mock_pool.submit.return_value = mock_future
        mock_pool_cls.return_value = mock_pool

        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("echo", _echo_agent, _make_manifest(name="echo"))
        subtasks = [
            {"id": "p1", "agent": "echo", "action": "read_file", "params": {}},
        ]
        scheduler.execute_parallel(subtasks, {})
        mock_pool.submit.assert_called()


# ---------------------------------------------------------------------------
# Sandbox Enforcement
# ---------------------------------------------------------------------------

class TestSandboxEnforcement:
    """15-18: Sandbox policy enforcement."""

    def test_manifest_declares_sandbox_policy(self):
        manifest = _make_manifest(sandbox_policy="ReadOnly")
        assert manifest.sandbox_policy == "ReadOnly"

    def test_scheduler_creates_sandbox_before_execution(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        manifest = _make_manifest()
        scheduler.register_agent("echo", _echo_agent, manifest)

        with patch.object(scheduler._sandbox_manager, "create_sandbox", wraps=scheduler._sandbox_manager.create_sandbox) as mock_create:
            scheduler.execute("echo", {}, {"action": "read_file"})
            mock_create.assert_called_once()

    def test_sandbox_violation_blocked(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        manifest = _make_manifest(sandbox_policy="ReadOnly")
        scheduler.register_agent("writer", _echo_agent, manifest)
        result = scheduler.execute(
            "writer", {},
            {"action": "write_file", "path": "/tmp/test_workspace/file.txt"},
        )
        assert result.status == "error"

    def test_default_sandbox_policy_is_workspace_write(self):
        manifest = AgentManifest(
            name="default_agent",
            version="1.0",
            actions=["read_file"],
            permissions=["/tmp"],
        )
        assert manifest.sandbox_policy == "WorkspaceWrite"


# ---------------------------------------------------------------------------
# Permission Enforcement
# ---------------------------------------------------------------------------

class TestPermissionEnforcement:
    """19-20: Action permission enforcement."""

    def test_agent_can_use_declared_actions(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        manifest = _make_manifest(actions=["read_file", "write_file"])
        scheduler.register_agent("echo", _echo_agent, manifest)
        result = scheduler.execute("echo", {}, {"action": "read_file"})
        assert result.status == "success"

    def test_undeclared_action_returns_error(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        manifest = _make_manifest(actions=["read_file"])
        scheduler.register_agent("echo", _echo_agent, manifest)
        result = scheduler.execute("echo", {}, {"action": "delete_file"})
        assert result.status == "error"
        assert result.error_code == "ACTION_NOT_PERMITTED"


# ---------------------------------------------------------------------------
# Failure Handling
# ---------------------------------------------------------------------------

class TestFailureHandling:
    """21-23: Exception and timeout handling."""

    def test_exception_caught_and_returned(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("fail", _failing_agent, _make_manifest(name="fail"))
        result = scheduler.execute("fail", {}, {"action": "read_file"})
        assert result.status == "error"
        assert "something broke" in result.error.lower() or "broke" in result.error.lower()

    def test_timeout_returns_error(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("slow", _slow_agent, _make_manifest(name="slow"))
        result = scheduler.execute("slow", {}, {"action": "read_file"}, timeout=0.5)
        assert result.status == "error"
        assert "too long" in result.error.lower()

    def test_default_timeout_is_120(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        assert scheduler._default_timeout == 120


# ---------------------------------------------------------------------------
# Dry Run
# ---------------------------------------------------------------------------

class TestDryRun:
    """24-25: Dry run mode."""

    def test_dry_run_passed_to_agent(self):
        received = {}

        def capture_agent(input_dict, context):
            received.update(context)
            return {"ok": True}

        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("cap", capture_agent, _make_manifest(name="cap"))
        scheduler.execute("cap", {}, {"action": "read_file", "dry_run": True})
        assert received.get("dry_run") is True

    def test_dry_run_metadata_in_result(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("echo", _echo_agent, _make_manifest(name="echo"))
        result = scheduler.execute("echo", {}, {"action": "read_file", "dry_run": True})
        assert result.dry_run is True


# ---------------------------------------------------------------------------
# Audit Integration
# ---------------------------------------------------------------------------

class TestAuditIntegration:
    """26-27: Execution audit log."""

    def test_execution_logged(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("echo", _echo_agent, _make_manifest(name="echo"))
        scheduler.execute("echo", {}, {"action": "read_file"})
        log = scheduler.get_execution_log()
        assert len(log) == 1
        entry = log[0]
        assert entry.agent_name == "echo"
        assert entry.action == "read_file"
        assert isinstance(entry.duration_ms, (int, float))
        assert entry.status in ("success", "error")

    def test_get_execution_log_returns_all(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("echo", _echo_agent, _make_manifest(name="echo"))
        scheduler.execute("echo", {}, {"action": "read_file"})
        scheduler.execute("echo", {}, {"action": "write_file"})
        log = scheduler.get_execution_log()
        assert len(log) == 2


# ---------------------------------------------------------------------------
# Context Building
# ---------------------------------------------------------------------------

class TestContextBuilding:
    """28-29: Agent-specific context construction."""

    def test_build_agent_context_includes_workspace(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        manifest = _make_manifest(permissions=["/tmp/data"])
        ctx = scheduler._build_agent_context({"action": "read_file"}, manifest)
        assert ctx["workspace"] == "/tmp/test_workspace"

    def test_build_agent_context_filters_granted_paths(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        manifest = _make_manifest(permissions=["/tmp/data", "/tmp/other"])
        ctx = scheduler._build_agent_context({"action": "read_file"}, manifest)
        assert "/tmp/data" in ctx["granted_paths"]
        assert "/tmp/other" in ctx["granted_paths"]


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """30-32: Edge case handling."""

    def test_empty_subtask_list_sequential(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        results = scheduler.execute_sequential([], {})
        assert results == []

    def test_empty_subtask_list_parallel(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        results = scheduler.execute_parallel([], {})
        assert results == []

    def test_none_context_uses_default(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("echo", _echo_agent, _make_manifest(name="echo"))
        result = scheduler.execute("echo", {}, None)
        assert result.status == "success"

    def test_agent_returns_non_dict(self):
        scheduler = AgentScheduler(workspace="/tmp/test_workspace")
        scheduler.register_agent("bad", _non_dict_agent, _make_manifest(name="bad"))
        result = scheduler.execute("bad", {}, {"action": "read_file"})
        assert result.status == "error"
