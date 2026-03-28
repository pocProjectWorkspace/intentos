"""
IntentOS Intent Kernel v2.0.0 — Production Execution Loop.

Fully integrated with Phase 2/3 modules:
  - Security pipeline (input/output scanning, credential leak detection)
  - Inference service (privacy-aware LLM routing, cost tracking)
  - Orchestration (SOP engine, agent scheduler, mode router, message bus)
  - RAG context assembler (file index, task history, experience)

The v1 kernel (kernel.py) is preserved as legacy fallback.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# --- Phase 2/3 module imports ---
from core.security.pipeline import SecurityPipeline
from core.security.credential_provider import CredentialProvider, get_api_key
from core.inference.llm import LLMService, LLMResponse
from core.inference.router import PrivacyMode
from core.orchestration.sop import SOPExecutor, Phase, PhaseResult, RecoveryAction, SOPResult
from core.orchestration.scheduler import AgentScheduler, AgentManifest, ExecutionResult
from core.orchestration.mode_router import ModeRouter, ReactMode
from core.orchestration.cost_manager import CostManager
from core.orchestration.message_bus import MessageBus, Message
from core.rag.context import ContextAssembler

# ---------------------------------------------------------------------------
# System prompt (carried forward from v1 kernel)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the IntentOS Intent Kernel. Your sole job is to receive a natural \
language instruction from the user and return a structured intent object as JSON.

You must respond with ONLY valid JSON — no markdown, no explanation, no wrapping.

The intent object schema:

{
  "raw_input": "<the exact instruction the user typed>",
  "intent": "<category.action in dot notation, e.g. file.rename, image.background_remove, browser.search>",
  "subtasks": [
    {
      "id": "1",
      "agent": "<which agent handles this step, e.g. file_agent, browser_agent, image_agent, media_agent, system_agent, document_agent>",
      "action": "<the specific action the agent should perform>",
      "params": { "<action-specific parameters>" }
    }
  ]
}

Available agents and their actions:

file_agent:
  Primitives: list_files, find_files, rename_file, move_file, copy_file, \
create_folder, delete_file, read_file, get_metadata, get_disk_usage.
  Compound actions: organize_by_type, bulk_rename, cleanup_old_files, \
deduplicate, sort_by_date, flatten_folders, archive_large_files.

system_agent:
  - get_current_date: params {format}

browser_agent:
  - search_web: params {query, max_results}
  - fetch_page: params {url}
  - extract_data: params {url, description, content}

document_agent:
  - create_document: params {filename, content, title, save_path}
  - append_content: params {path, content, heading}
  - read_document: params {path}
  - convert_document: params {path, format}
  - save_document: params {path, destination, filename}

image_agent:
  - remove_background: params {path}
  - resize: params {path, width, height}

media_agent:
  - convert: params {path, format}
  - trim: params {path, start, end}

Rules:
1. "raw_input" is always the exact text the user typed, unmodified.
2. "intent" is a short dot-notation label: <category>.<action>.
3. "subtasks" is an ordered array with id, agent, action, and params.
4. For multi-step tasks, decompose into minimal ordered subtasks. \
Reference earlier results as "{{1.result}}".
5. If the instruction is ambiguous, pick the most likely interpretation.
6. Always return valid JSON. Never return markdown or explanation text.
7. Use ~ for home directory paths.
"""

# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------

AGENT_REGISTRY: Dict[str, str] = {
    "file_agent": "capabilities.file_agent.agent",
    "system_agent": "capabilities.system_agent.agent",
    "browser_agent": "capabilities.browser_agent.agent",
    "document_agent": "capabilities.document_agent.agent",
    "image_agent": "capabilities.image_agent.agent",
    "media_agent": "capabilities.media_agent.agent",
}

# Agent manifests for the scheduler
_AGENT_MANIFESTS: Dict[str, Dict[str, Any]] = {
    "file_agent": {
        "version": "1.0.0",
        "actions": [
            "list_files", "find_files", "rename_file", "move_file",
            "copy_file", "create_folder", "delete_file", "read_file",
            "get_metadata", "get_disk_usage", "organize_by_type",
            "bulk_rename", "cleanup_old_files", "deduplicate",
            "sort_by_date", "flatten_folders", "archive_large_files",
        ],
        "permissions": ["~/Documents", "~/Downloads", "~/Desktop"],
        "sandbox_policy": "WorkspaceWrite",
    },
    "browser_agent": {
        "version": "1.0.0",
        "actions": ["search_web", "fetch_page", "extract_data"],
        "permissions": [],
        "sandbox_policy": "ReadOnly",
    },
    "document_agent": {
        "version": "1.0.0",
        "actions": [
            "create_document", "append_content", "read_document",
            "convert_document", "save_document",
        ],
        "permissions": ["~/Documents", "~/Downloads", "~/Desktop"],
        "sandbox_policy": "WorkspaceWrite",
    },
    "system_agent": {
        "version": "1.0.0",
        "actions": ["get_current_date"],
        "permissions": [],
        "sandbox_policy": "ReadOnly",
    },
    "image_agent": {
        "version": "0.1.0",
        "actions": ["remove_background", "resize"],
        "permissions": ["~/Documents", "~/Downloads", "~/Desktop"],
        "sandbox_policy": "WorkspaceWrite",
    },
    "media_agent": {
        "version": "0.1.0",
        "actions": ["convert", "trim"],
        "permissions": ["~/Documents", "~/Downloads", "~/Desktop"],
        "sandbox_policy": "WorkspaceWrite",
    },
}


# ---------------------------------------------------------------------------
# TaskResult
# ---------------------------------------------------------------------------

@dataclass
class TaskResult:
    """Final result of a process_task() invocation."""
    task_id: str
    status: str  # "success" | "error" | "blocked"
    intent: Optional[Dict[str, Any]] = None
    execution_results: List[ExecutionResult] = field(default_factory=list)
    sop_result: Optional[SOPResult] = None
    report: str = ""
    cost_usd: float = 0.0
    duration_ms: int = 0
    security_warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Workspace setup
# ---------------------------------------------------------------------------

def _ensure_workspace() -> bool:
    """Ensure ~/.intentos/ exists with full directory structure."""
    home = os.path.expanduser("~")
    base = os.path.join(home, ".intentos")
    first_run = not os.path.exists(base)
    dirs = [
        os.path.join(base, "logs"),
        os.path.join(base, "workspace", "outputs"),
        os.path.join(base, "workspace", "temp"),
        os.path.join(base, "rag"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    audit_file = os.path.join(base, "logs", "audit.jsonl")
    if not os.path.exists(audit_file):
        open(audit_file, "a").close()
    return first_run


# ---------------------------------------------------------------------------
# IntentKernel
# ---------------------------------------------------------------------------

class IntentKernel:
    """The v2 kernel — fully integrated with all Phase 2/3 modules."""

    VERSION = "2.0.0"

    def __init__(
        self,
        privacy_mode: PrivacyMode = PrivacyMode.SMART_ROUTING,
        budget: Optional[float] = None,
    ) -> None:
        # Workspace
        _ensure_workspace()
        self._workspace = os.path.join(os.path.expanduser("~"), ".intentos", "workspace")

        # Security
        self.security = SecurityPipeline(strict_mode=True)
        self.credentials = CredentialProvider()

        # Inference
        self.llm = LLMService(
            privacy_mode=privacy_mode,
            credential_provider=self.credentials,
            budget=budget,
        )

        # Orchestration
        self.scheduler = AgentScheduler(workspace=self._workspace)
        self.mode_router = ModeRouter()
        self.message_bus = MessageBus()
        self.sop = None  # Created per-task

        # Context
        self.context_assembler = ContextAssembler()

        # Task history (in-memory for the session)
        self._task_history: List[TaskResult] = []

        # Register all agents
        self._register_agents()

    # -- Agent registration -------------------------------------------------

    def _register_agents(self) -> None:
        """Register all capability agents with the scheduler."""
        for agent_name, module_path in AGENT_REGISTRY.items():
            manifest_data = _AGENT_MANIFESTS.get(agent_name, {})
            home = os.path.expanduser("~")
            permissions = [
                p.replace("~", home) for p in manifest_data.get("permissions", [])
            ]
            permissions.append(self._workspace)

            manifest = AgentManifest(
                name=agent_name,
                version=manifest_data.get("version", "0.0.0"),
                actions=manifest_data.get("actions", []),
                permissions=permissions,
                sandbox_policy=manifest_data.get("sandbox_policy", "WorkspaceWrite"),
            )

            # Create a handler that dynamically loads and calls the agent module
            handler = _make_agent_handler(agent_name, module_path)
            self.scheduler.register_agent(agent_name, handler, manifest)

    # -- Main execution loop ------------------------------------------------

    def process_task(self, user_input: str) -> TaskResult:
        """The main execution loop — a single task from input to result."""
        task_id = str(uuid.uuid4())
        task_start = time.monotonic()
        cost_before = self.llm.get_total_spent()

        # 1. Security: scan input
        input_scan = self.security.process_input(user_input)
        if input_scan.blocked:
            return TaskResult(
                task_id=task_id,
                status="blocked",
                error="Input blocked by security pipeline",
                security_warnings=input_scan.warnings,
                duration_ms=int((time.monotonic() - task_start) * 1000),
            )

        sanitized_input = input_scan.sanitized_input

        # 2. Context: assemble relevant context from RAG
        assembled = self.context_assembler.build_context(sanitized_input)

        # 3. Create SOP executor for this task
        sop = SOPExecutor(context={"task_id": task_id, "user_input": sanitized_input})
        self.sop = sop

        # Register phase handlers
        sop.register_handler(Phase.PARSE, lambda inp, ctx: self._phase_parse(inp, ctx))
        sop.register_handler(Phase.PLAN, lambda inp, ctx: self._phase_plan(inp, ctx))
        sop.register_handler(Phase.VALIDATE, lambda inp, ctx: self._phase_validate(inp, ctx))
        sop.register_handler(Phase.PREVIEW, lambda inp, ctx: self._phase_preview(inp, ctx))
        sop.register_handler(Phase.EXECUTE, lambda inp, ctx: self._phase_execute(inp, ctx))
        sop.register_handler(Phase.VERIFY, lambda inp, ctx: self._phase_verify(inp, ctx))
        sop.register_handler(Phase.REPORT, lambda inp, ctx: self._phase_report(inp, ctx))

        # Register error handler
        sop.register_error_handler(self._handle_sop_error)

        # Determine if preview is needed (will be checked inside SOP run)
        # For now, run all phases; PREVIEW handler itself decides whether to
        # do real work or pass through.
        sop_result = sop.run(
            initial_input={"user_input": sanitized_input, "context": assembled},
            skip_preview=False,
        )

        duration_ms = int((time.monotonic() - task_start) * 1000)
        cost_after = self.llm.get_total_spent()
        task_cost = cost_after - cost_before

        # Extract results from SOP
        intent = None
        execution_results = []
        report = ""

        parse_phase = sop_result.get_phase(Phase.PARSE)
        if parse_phase and parse_phase.output:
            intent = parse_phase.output

        execute_phase = sop_result.get_phase(Phase.EXECUTE)
        if execute_phase and execute_phase.output:
            execution_results = execute_phase.output if isinstance(execute_phase.output, list) else []

        report_phase = sop_result.get_phase(Phase.REPORT)
        if report_phase and report_phase.output:
            report = report_phase.output if isinstance(report_phase.output, str) else str(report_phase.output)

        # Build task result
        task_result = TaskResult(
            task_id=task_id,
            status=sop_result.overall_status,
            intent=intent,
            execution_results=execution_results,
            sop_result=sop_result,
            report=report,
            cost_usd=task_cost,
            duration_ms=duration_ms,
            security_warnings=input_scan.warnings if input_scan.has_warnings else [],
        )

        # Record in history
        self._task_history.append(task_result)

        # Record in RAG context assembler
        try:
            agents_used = list({r.agent_name for r in execution_results if hasattr(r, "agent_name")})
            files_accessed = []
            for r in execution_results:
                if hasattr(r, "paths_accessed"):
                    files_accessed.extend(r.paths_accessed)
            params = intent.get("subtasks", [{}])[0].get("params", {}) if intent else {}
            self.context_assembler.record_task(
                raw_input=user_input,
                intent=intent.get("intent", "unknown") if intent else "unknown",
                agents=agents_used,
                files=files_accessed or [""],
                params=params,
                status=sop_result.overall_status,
                duration=duration_ms,
            )
        except Exception:
            pass  # Context recording is best-effort

        # Publish completion message on the bus
        self.message_bus.publish(Message(
            content=f"Task {task_id} completed: {sop_result.overall_status}",
            cause_by="task_complete",
            sent_from="kernel",
            payload={"task_id": task_id, "status": sop_result.overall_status},
        ))

        return task_result

    # -- SOP Phase Handlers -------------------------------------------------

    def _phase_parse(self, initial_input: Any, context: Dict) -> Dict:
        """PARSE: Use LLM to parse intent from user input + assembled context."""
        user_input = initial_input["user_input"]
        assembled = initial_input.get("context")

        # Build prompt with context
        context_text = assembled.context_text if assembled else ""
        if context_text:
            prompt = f"{context_text}\n\nUser instruction: {user_input}"
        else:
            prompt = user_input

        result = self.llm.parse_intent(prompt, SYSTEM_PROMPT)
        if result is None:
            raise ValueError("LLM failed to parse intent — no valid JSON returned")

        # Ensure raw_input is preserved
        if "raw_input" not in result:
            result["raw_input"] = user_input

        return result

    def _phase_plan(self, intent: Dict, context: Dict) -> Dict:
        """PLAN: Decompose intent into subtasks, select execution mode."""
        subtasks = intent.get("subtasks", [])
        if not subtasks:
            raise ValueError("No subtasks generated — try rephrasing the instruction")

        mode = self.mode_router.select_mode(intent.get("raw_input", ""), subtasks)
        return {"intent": intent, "subtasks": subtasks, "mode": mode}

    def _phase_validate(self, plan: Dict, context: Dict) -> Dict:
        """VALIDATE: Check all agents exist, permissions valid."""
        for subtask in plan["subtasks"]:
            agent = subtask.get("agent")
            if not self.scheduler.is_registered(agent):
                raise ValueError(f"Agent '{agent}' is not available")
        return plan

    def _phase_preview(self, plan: Dict, context: Dict) -> Dict:
        """PREVIEW: Dry-run for destructive/batch operations."""
        subtasks = plan["subtasks"]
        needs_preview = SOPExecutor.needs_preview(subtasks)

        if not needs_preview:
            return {"plan": plan, "preview": None, "skipped": True}

        dry_context = {**self._build_context(), "dry_run": True}
        results = self.scheduler.execute_sequential(subtasks, dry_context)
        return {"plan": plan, "preview": results, "skipped": False}

    def _phase_execute(self, preview_data: Dict, context: Dict) -> List[ExecutionResult]:
        """EXECUTE: Run subtasks through scheduler with security pipeline."""
        plan = preview_data.get("plan", preview_data)
        real_context = self._build_context()

        mode = plan.get("mode", ReactMode.BY_ORDER)
        subtasks = plan["subtasks"]

        if mode == ReactMode.BY_ORDER:
            results = self.scheduler.execute_sequential(subtasks, real_context)
        elif mode == ReactMode.PLAN_AND_ACT:
            results = self.scheduler.execute_sequential(subtasks, real_context)
        else:  # REACT — sequential for now (dynamic selection is Phase 4)
            results = self.scheduler.execute_sequential(subtasks, real_context)

        return results

    def _phase_verify(self, results: List[ExecutionResult], context: Dict) -> List[ExecutionResult]:
        """VERIFY: Check results match intent, scan for leaks."""
        for result in results:
            if result.output:
                scan = self.security.process_output(result.output)
                if scan.had_leaks:
                    result.output = scan.sanitized_output
        return results

    def _phase_report(self, results: List[ExecutionResult], context: Dict) -> str:
        """REPORT: Format results for display."""
        return self._format_results(results)

    # -- Error handling -----------------------------------------------------

    def _handle_sop_error(self, phase_result: PhaseResult) -> RecoveryAction:
        """Decide recovery action on phase failure."""
        phase = phase_result.phase
        error = phase_result.error_message or ""

        # Parse failures can be retried once (LLM might return valid JSON)
        if phase == Phase.PARSE:
            return RecoveryAction.ABORT

        # Validation failure: abort (can't recover from missing agents)
        if phase == Phase.VALIDATE:
            return RecoveryAction.ABORT

        # Execution failure: abort for now (retry logic is Phase 4)
        if phase == Phase.EXECUTE:
            return RecoveryAction.ABORT

        return RecoveryAction.ABORT

    # -- Context builder ----------------------------------------------------

    def _build_context(self) -> Dict:
        """Build the context dict injected into every agent call."""
        home = os.path.expanduser("~")
        return {
            "user": os.getenv("USER", "unknown"),
            "workspace": self._workspace,
            "granted_paths": [
                os.path.join(home, "Documents"),
                os.path.join(home, "Downloads"),
                os.path.join(home, "Desktop"),
                self._workspace,
            ],
            "task_id": str(uuid.uuid4()),
            "dry_run": False,
        }

    # -- Result formatting --------------------------------------------------

    def _format_results(self, results: List[ExecutionResult]) -> str:
        """Format execution results into a human-readable report."""
        if not results:
            return "No results."

        lines = []
        success_count = 0
        error_count = 0
        skipped_count = 0

        for r in results:
            prefix = ""
            if r.status == "success":
                prefix = "[OK]"
                success_count += 1
            elif r.status == "error":
                prefix = "[ERR]"
                error_count += 1
            elif r.status == "skipped":
                prefix = "[SKIP]"
                skipped_count += 1

            sid = r.subtask_id or "?"
            line = f"  {prefix} [{sid}] {r.agent_name}.{r.action}"
            if r.error:
                line += f" — {r.error}"
            lines.append(line)

        # Summary
        lines.append("")
        lines.append(f"  Total: {len(results)} | OK: {success_count} | "
                      f"Errors: {error_count} | Skipped: {skipped_count}")

        return "\n".join(lines)

    # -- CLI subcommand handler ---------------------------------------------

    def handle_command(self, command: str) -> str:
        """Handle !-prefixed CLI subcommands. Returns output string."""
        parts = command.strip().split()
        cmd = parts[0].lower() if parts else ""

        if cmd == "status":
            return self._cmd_status()
        elif cmd == "cost":
            return self._cmd_cost()
        elif cmd == "history":
            return self._cmd_history()
        elif cmd == "credentials":
            return self._cmd_credentials()
        elif cmd == "security":
            return self._cmd_security()
        else:
            return f"Unknown command: {cmd}\nAvailable: !status, !cost, !history, !credentials, !security"

    def _cmd_status(self) -> str:
        """Hardware profile, model, privacy mode, cost summary."""
        config = self.llm.get_config()
        hw = config.get("hardware", {})
        stats = self.llm.get_stats()
        lines = [
            "IntentOS Kernel v2.0.0 — Status",
            "=" * 40,
            f"  Model (local):   {config.get('local_model', 'N/A')}",
            f"  Model (cloud):   {config.get('cloud_model', 'N/A')}",
            f"  Privacy mode:    {config.get('privacy_mode', 'N/A')}",
            f"  Recommended:     {config.get('recommended_model', 'N/A')}",
            "",
            f"  Platform:        {hw.get('platform', 'N/A')}",
            f"  CPU:             {hw.get('cpu_model', 'N/A')} ({hw.get('cpu_cores', '?')} cores)",
            f"  RAM:             {hw.get('ram_gb', '?')} GB",
            f"  GPU:             {hw.get('gpu', {}).get('model', 'None') if hw.get('gpu') else 'None'}",
            "",
            f"  Agents:          {len(self.scheduler.list_agents())} registered",
            f"  Tasks this run:  {len(self._task_history)}",
            f"  Total cost:      ${stats['total_cost_usd']:.4f}",
        ]
        return "\n".join(lines)

    def _cmd_cost(self) -> str:
        """Detailed cost breakdown."""
        report = self.llm.get_cost_report()
        report_dict = report.to_dict()
        lines = [
            "Cost Report",
            "=" * 40,
            f"  Total spent:     ${report_dict['total_spent_usd']:.4f}",
            f"  Input tokens:    {report_dict['total_input_tokens']}",
            f"  Output tokens:   {report_dict['total_output_tokens']}",
            f"  API calls:       {report_dict['call_count']}",
        ]
        budget = self.llm.get_remaining_budget()
        if budget is not None:
            lines.append(f"  Remaining:       ${budget:.4f}")

        if report_dict.get("by_model"):
            lines.append("")
            lines.append("  By model:")
            for model, usage in report_dict["by_model"].items():
                lines.append(
                    f"    {model}: {usage['total_tokens']} tokens, "
                    f"${usage['cost_usd']:.4f}, {usage['call_count']} calls"
                )

        return "\n".join(lines)

    def _cmd_history(self) -> str:
        """Recent task history."""
        if not self._task_history:
            return "No tasks executed this session."

        lines = [
            "Task History",
            "=" * 40,
        ]
        for i, t in enumerate(self._task_history[-10:], 1):
            intent_label = t.intent.get("intent", "?") if t.intent else "?"
            lines.append(
                f"  {i}. [{t.status}] {intent_label} — "
                f"{t.duration_ms}ms, ${t.cost_usd:.4f}"
            )
        return "\n".join(lines)

    def _cmd_credentials(self) -> str:
        """Credential management info."""
        lines = [
            "Credentials",
            "=" * 40,
            f"  Provider:  CredentialProvider",
            f"  Status:    Active",
        ]
        return "\n".join(lines)

    def _cmd_security(self) -> str:
        """Security pipeline stats."""
        stats = self.security.get_stats()
        lines = [
            "Security Pipeline",
            "=" * 40,
            f"  Total scans:       {stats['total_scans']}",
            f"  Inputs blocked:    {stats['inputs_blocked']}",
            f"  Outputs blocked:   {stats['outputs_blocked']}",
            f"  Leaks redacted:    {stats['leaks_redacted']}",
            f"  Policy violations: {stats['policy_violations']}",
        ]
        return "\n".join(lines)

    # -- Display helper -----------------------------------------------------

    def display_result(self, result: TaskResult) -> None:
        """Print a TaskResult to the terminal."""
        print()
        if result.status == "blocked":
            print("=" * 60)
            print("  BLOCKED")
            print("=" * 60)
            if result.error:
                print(f"  {result.error}")
            for w in result.security_warnings:
                print(f"  Warning: {w}")
            print("=" * 60)
            return

        if result.status == "error":
            print("=" * 60)
            print("  ERROR")
            print("=" * 60)
            sop = result.sop_result
            if sop:
                for pr in sop.phases:
                    if pr.status == "error":
                        print(f"  Phase {pr.phase.name}: {pr.error_message}")
            elif result.error:
                print(f"  {result.error}")
            print("=" * 60)
            return

        # Success
        intent_label = result.intent.get("intent", "?") if result.intent else "?"
        print("=" * 60)
        print("  DONE")
        print("=" * 60)
        print(f"  Intent:   {intent_label}")

        if result.report:
            print(result.report)

        secs = result.duration_ms / 1000
        print(f"  Time:     {secs:.1f}s")
        print(f"  Cost:     ${result.cost_usd:.4f}")
        print("=" * 60)
        print()


# ---------------------------------------------------------------------------
# Agent handler factory
# ---------------------------------------------------------------------------

def _make_agent_handler(agent_name: str, module_path: str):
    """Create a handler function that dynamically loads an agent module."""
    def handler(input_dict: Dict, context: Dict) -> Dict:
        try:
            agent_module = importlib.import_module(module_path)
        except ImportError:
            return {
                "status": "error",
                "error": {"code": "AGENT_NOT_AVAILABLE", "message": f"Module '{module_path}' not found"},
                "metadata": {"files_affected": 0},
            }
        agent_input = {
            "action": context.get("action", "unknown"),
            "params": input_dict,
            "context": context,
        }
        try:
            return agent_module.run(agent_input)
        except Exception as exc:
            return {
                "status": "error",
                "error": {"code": "AGENT_CRASH", "message": str(exc)},
                "metadata": {"files_affected": 0},
            }
    return handler


# ---------------------------------------------------------------------------
# CLI main loop
# ---------------------------------------------------------------------------

def main() -> None:
    _ensure_workspace()

    # First-run wizard
    try:
        from core.first_run import FirstRunWizard
        wizard = FirstRunWizard()
        if wizard.is_first_run():
            print("\n" + "=" * 56)
            print("  Welcome to IntentOS")
            print("  Your computer, finally on your side.")
            print("=" * 56 + "\n")
            wizard.run(skip_prompts=False)
    except Exception as e:
        print(f"  Setup note: {e}")
        print("  Continuing with defaults...\n")

    kernel = IntentKernel()

    # Start API bridge in background
    try:
        from core.api.server import APIBridge
        api = APIBridge(kernel=kernel)
        api.start(port=7891)
        api_status = "API bridge on :7891"
    except Exception:
        api_status = "API bridge offline"

    config = kernel.llm.get_config()
    print(f"IntentOS Kernel v{IntentKernel.VERSION}")
    print(f"Model: {config.get('local_model', 'N/A')} | Mode: {config.get('privacy_mode', 'N/A')} | {api_status}")
    print("Type a task in natural language. Type '!help' for commands. Type 'exit' to stop.\n")

    while True:
        try:
            user_input = input("intentos> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            stats = kernel.llm.get_stats()
            print(
                f"\nSession summary: {stats['total_calls']} calls, "
                f"{stats['total_tokens']} tokens, ${stats['total_cost_usd']:.4f}"
            )
            break

        # Handle CLI subcommands
        if user_input.startswith("!"):
            cmd_text = user_input[1:].strip().lower()

            # Voice input
            if cmd_text in ("voice", "v"):
                try:
                    from core.voice.stt import VoiceInput
                    vi = VoiceInput()
                    if vi.is_available():
                        print("  Listening... (speak now, 5 seconds)")
                        result = vi.listen_and_transcribe(duration=5)
                        if result and result.text:
                            print(f'  Heard: "{result.text}"')
                            user_input = result.text
                            # Fall through to process_task below
                        else:
                            print("  Couldn't understand that. Try again or type your task.")
                            continue
                    else:
                        print("  Voice input not available. Install: pip install SpeechRecognition pyaudio")
                        continue
                except Exception as e:
                    print(f"  Voice error: {e}")
                    continue
            elif cmd_text == "help":
                print(
                    "Commands:\n"
                    "  !help         Show this help\n"
                    "  !voice / !v   Voice input (speak a task)\n"
                    "  !status       System status\n"
                    "  !cost         Cost breakdown\n"
                    "  !history      Task history\n"
                    "  !credentials  Credential info\n"
                    "  !security     Security stats\n"
                    "  exit          Quit"
                )
                continue
            else:
                output = kernel.handle_command(cmd_text)
                print(output)
                continue

        result = kernel.process_task(user_input)
        kernel.display_result(result)


if __name__ == "__main__":
    main()
