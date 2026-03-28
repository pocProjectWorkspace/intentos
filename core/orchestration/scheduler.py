"""
IntentOS Agent Scheduler (Phase 2C.6).

Spawns agents, enforces sandbox policies, manages execution, and handles
failures.  Ties together the security and orchestration modules.
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.security.sandbox import SandboxManager, SandboxPolicy, FileOp


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AgentManifest:
    """Declares an agent's identity, capabilities, and sandbox requirements."""
    name: str
    version: str
    actions: List[str]
    permissions: List[str]  # granted filesystem paths
    sandbox_policy: str = "WorkspaceWrite"


@dataclass
class ExecutionResult:
    """Outcome of a single agent execution."""
    agent_name: str
    action: str
    status: str  # "success" | "error" | "skipped"
    output: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    error: Optional[str] = None
    error_code: Optional[str] = None
    subtask_id: Optional[str] = None
    dry_run: bool = False
    paths_accessed: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Policy mapping
# ---------------------------------------------------------------------------

_POLICY_MAP = {
    "ReadOnly": SandboxPolicy.READ_ONLY,
    "WorkspaceWrite": SandboxPolicy.WORKSPACE_WRITE,
    "FullAccess": SandboxPolicy.FULL_ACCESS,
}

# Map action names to FileOp for sandbox checks
_ACTION_TO_FILEOP = {
    "read_file": FileOp.READ,
    "write_file": FileOp.WRITE,
    "delete_file": FileOp.DELETE,
    "create_dir": FileOp.CREATE_DIR,
    "move_file": FileOp.MOVE,
    "copy_file": FileOp.COPY,
    "execute": FileOp.EXECUTE,
}


# ---------------------------------------------------------------------------
# AgentScheduler
# ---------------------------------------------------------------------------

class AgentScheduler:
    """Orchestrates agent lifecycle: registration, sandboxing, execution."""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self._agents: Dict[str, Tuple[Callable, AgentManifest]] = {}
        self._execution_log: List[ExecutionResult] = []
        self._sandbox_manager = SandboxManager()
        self._default_timeout = 120

    # -- Registration -------------------------------------------------------

    def register_agent(self, name: str, handler: Callable, manifest: AgentManifest):
        """Register (or overwrite) an agent handler and manifest."""
        self._agents[name] = (handler, manifest)

    def is_registered(self, name: str) -> bool:
        return name in self._agents

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())

    # -- Single Execution ---------------------------------------------------

    def execute(
        self,
        agent_name: str,
        input_dict: dict,
        context: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        """Execute a single agent and return an ExecutionResult."""
        context = context or {}
        action = context.get("action", "unknown")
        timeout = timeout if timeout is not None else self._default_timeout
        dry_run = context.get("dry_run", False)

        # Unknown agent
        if not self.is_registered(agent_name):
            result = ExecutionResult(
                agent_name=agent_name,
                action=action,
                status="error",
                error="Agent not available",
                error_code="AGENT_NOT_AVAILABLE",
                dry_run=dry_run,
            )
            self._execution_log.append(result)
            return result

        handler, manifest = self._agents[agent_name]

        # Permission enforcement
        if not self._enforce_permissions(manifest, action):
            result = ExecutionResult(
                agent_name=agent_name,
                action=action,
                status="error",
                error=f"Action '{action}' is not permitted for agent '{agent_name}'",
                error_code="ACTION_NOT_PERMITTED",
                dry_run=dry_run,
            )
            self._execution_log.append(result)
            return result

        # Sandbox enforcement
        sandbox_policy = _POLICY_MAP.get(manifest.sandbox_policy, SandboxPolicy.WORKSPACE_WRITE)
        path = context.get("path", self.workspace)

        self._sandbox_manager.create_sandbox(
            agent_name=agent_name,
            policy=sandbox_policy,
            granted_paths=manifest.permissions,
            workspace=self.workspace,
        )

        if not self._enforce_sandbox(manifest, action, path):
            result = ExecutionResult(
                agent_name=agent_name,
                action=action,
                status="error",
                error=f"Sandbox policy '{manifest.sandbox_policy}' blocks '{action}' on '{path}'",
                error_code="SANDBOX_VIOLATION",
                dry_run=dry_run,
            )
            self._execution_log.append(result)
            return result

        # Build agent context
        agent_context = self._build_agent_context(context, manifest)

        # Execute with timeout
        start = time.monotonic()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(handler, input_dict, agent_context)
                raw_output = future.result(timeout=timeout)
        except FuturesTimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                agent_name=agent_name,
                action=action,
                status="error",
                duration_ms=elapsed,
                error=f"Agent '{agent_name}' took too long (exceeded {timeout}s timeout)",
                error_code="TIMEOUT",
                dry_run=dry_run,
            )
            self._execution_log.append(result)
            return result
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                agent_name=agent_name,
                action=action,
                status="error",
                duration_ms=elapsed,
                error=f"Agent '{agent_name}' failed: {exc}",
                error_code="AGENT_ERROR",
                dry_run=dry_run,
            )
            self._execution_log.append(result)
            return result

        elapsed = (time.monotonic() - start) * 1000

        # Validate output type
        if not isinstance(raw_output, dict):
            result = ExecutionResult(
                agent_name=agent_name,
                action=action,
                status="error",
                duration_ms=elapsed,
                error=f"Agent '{agent_name}' returned non-dict output (got {type(raw_output).__name__})",
                error_code="INVALID_OUTPUT",
                dry_run=dry_run,
            )
            self._execution_log.append(result)
            return result

        result = ExecutionResult(
            agent_name=agent_name,
            action=action,
            status="success",
            output=raw_output,
            duration_ms=elapsed,
            dry_run=dry_run,
            paths_accessed=[path] if path else [],
        )
        self._execution_log.append(result)
        return result

    # -- Sequential Execution -----------------------------------------------

    def execute_sequential(
        self, subtasks: List[dict], context: dict
    ) -> List[ExecutionResult]:
        """Run subtasks in order; stop on first failure."""
        if not subtasks:
            return []

        context = context or {}
        results: List[ExecutionResult] = []
        results_by_id: Dict[str, ExecutionResult] = {}
        failed = False

        for i, subtask in enumerate(subtasks):
            subtask_id = subtask["id"]

            if failed:
                result = ExecutionResult(
                    agent_name=subtask.get("agent", "unknown"),
                    action=subtask.get("action", "unknown"),
                    status="skipped",
                    subtask_id=subtask_id,
                )
                results.append(result)
                continue

            # Resolve references in params
            params = self._resolve_references(
                dict(subtask.get("params", {})), results_by_id
            )

            sub_context = {**context, "action": subtask.get("action", "unknown")}
            result = self.execute(
                subtask["agent"], params, sub_context
            )
            result.subtask_id = subtask_id
            results.append(result)
            results_by_id[subtask_id] = result

            if result.status == "error":
                failed = True

        return results

    # -- Parallel Execution -------------------------------------------------

    def execute_parallel(
        self, subtasks: List[dict], context: dict
    ) -> List[ExecutionResult]:
        """Run independent subtasks concurrently via ThreadPoolExecutor."""
        if not subtasks:
            return []

        context = context or {}

        def _run_subtask(subtask):
            sub_context = {**context, "action": subtask.get("action", "unknown")}
            result = self.execute(
                subtask["agent"], subtask.get("params", {}), sub_context
            )
            result.subtask_id = subtask["id"]
            return result

        with ThreadPoolExecutor(max_workers=len(subtasks)) as pool:
            futures = [pool.submit(_run_subtask, st) for st in subtasks]
            results = [f.result() for f in futures]

        return results

    # -- Reference Resolution -----------------------------------------------

    def _resolve_references(
        self, params: dict, previous_results: Dict[str, ExecutionResult]
    ) -> dict:
        """Replace {{N.result}} patterns with actual outputs from earlier subtasks."""
        resolved = {}
        ref_pattern = re.compile(r"\{\{(\w+)\.result\}\}")
        for key, value in params.items():
            if isinstance(value, str):
                match = ref_pattern.fullmatch(value)
                if match:
                    ref_id = match.group(1)
                    if ref_id in previous_results:
                        resolved[key] = previous_results[ref_id].output
                    else:
                        resolved[key] = value
                else:
                    resolved[key] = value
            else:
                resolved[key] = value
        return resolved

    # -- Sandbox Enforcement ------------------------------------------------

    def _enforce_sandbox(self, manifest: AgentManifest, action: str, path: str) -> bool:
        """Return True if the action on path is allowed by the sandbox policy."""
        sandbox_policy = _POLICY_MAP.get(manifest.sandbox_policy, SandboxPolicy.WORKSPACE_WRITE)
        file_op = _ACTION_TO_FILEOP.get(action, FileOp.READ)

        from core.security.sandbox import Sandbox
        sandbox = Sandbox(
            policy=sandbox_policy,
            granted_paths=manifest.permissions,
            workspace=self.workspace,
        )
        result = sandbox.check(file_op, path)
        return result.allowed

    # -- Permission Enforcement ---------------------------------------------

    def _enforce_permissions(self, manifest: AgentManifest, action: str) -> bool:
        """Return True if the agent manifest declares the given action."""
        if action == "unknown":
            return True
        return action in manifest.actions

    # -- Context Building ---------------------------------------------------

    def _build_agent_context(self, context: dict, manifest: AgentManifest) -> dict:
        """Create agent-specific context with workspace and granted paths."""
        agent_context = dict(context)
        agent_context["workspace"] = self.workspace
        agent_context["granted_paths"] = list(manifest.permissions)
        return agent_context

    # -- Audit --------------------------------------------------------------

    def get_execution_log(self) -> List[ExecutionResult]:
        """Return all logged execution results."""
        return list(self._execution_log)
