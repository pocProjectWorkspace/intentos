"""
IntentOS CLI commands module.

Handles the !command subcommands dispatched from the kernel REPL.
Each command returns a human-readable string for display.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Callable, Dict, List, Optional


class CLICommands:
    """Handles ! subcommands in the IntentOS CLI."""

    def __init__(self, kernel=None):
        self.kernel = kernel
        self.commands: Dict[str, Callable] = {
            "status": self.cmd_status,
            "cost": self.cmd_cost,
            "history": self.cmd_history,
            "credentials": self.cmd_credentials,
            "security": self.cmd_security,
            "help": self.cmd_help,
            "hardware": self.cmd_hardware,
        }

    def handle(self, command_str: str) -> str:
        """Parse and execute a ! command. Returns output string."""
        parts = command_str.strip().split()
        cmd = parts[0] if parts else "help"
        args = parts[1:] if len(parts) > 1 else []

        handler = self.commands.get(cmd, self.cmd_unknown)
        return handler(args)

    # ------------------------------------------------------------------
    # Individual command handlers
    # ------------------------------------------------------------------

    def cmd_status(self, args: List[str]) -> str:
        """Hardware, model, mode, and cost summary."""
        lines = ["=== IntentOS Status ==="]

        # Hardware summary
        hw = self._get_hardware_summary()
        lines.append(f"Hardware : {hw}")

        # Model
        model = self._get_active_model()
        lines.append(f"Model    : {model}")

        # Mode
        mode = self._get_mode()
        lines.append(f"Mode     : {mode}")

        # Cost summary
        cost = self._get_total_cost()
        lines.append(f"Cost     : ${cost:.4f}")

        return "\n".join(lines)

    def cmd_cost(self, args: List[str]) -> str:
        """Detailed cost breakdown by model/task."""
        lines = ["=== Cost Breakdown ==="]

        cost_data = self._get_cost_breakdown()
        if not cost_data:
            lines.append("No costs recorded yet.")
        else:
            for entry in cost_data:
                model = entry.get("model", "unknown")
                amount = entry.get("cost", 0.0)
                tasks = entry.get("tasks", 0)
                lines.append(f"  {model}: ${amount:.4f} ({tasks} tasks)")

        total = self._get_total_cost()
        lines.append(f"  Total: ${total:.4f}")

        return "\n".join(lines)

    def cmd_history(self, args: List[str]) -> str:
        """Recent 10 tasks with status."""
        lines = ["=== Recent Tasks ==="]

        tasks = self._get_recent_tasks(limit=10)
        if not tasks:
            lines.append("No tasks recorded yet.")
        else:
            for i, task in enumerate(tasks, 1):
                status = task.get("status", "unknown")
                intent = task.get("intent", "?")
                ts = task.get("timestamp", "")
                lines.append(f"  {i}. [{status}] {intent}  ({ts})")

        return "\n".join(lines)

    def cmd_credentials(self, args: List[str]) -> str:
        """List stored credential names (never values)."""
        lines = ["=== Stored Credentials ==="]

        creds = self._get_credential_names()
        if not creds:
            lines.append("No credentials stored.")
        else:
            for name in creds:
                lines.append(f"  - {name}")

        return "\n".join(lines)

    def cmd_security(self, args: List[str]) -> str:
        """Security pipeline stats."""
        lines = ["=== Security Pipeline ==="]

        stats = self._get_security_stats()
        lines.append(f"Tasks scanned   : {stats.get('tasks_scanned', 0)}")
        lines.append(f"Threats blocked : {stats.get('threats_blocked', 0)}")
        lines.append(f"Pipeline status : {stats.get('status', 'unknown')}")

        return "\n".join(lines)

    def cmd_help(self, args: List[str]) -> str:
        """List all available ! commands."""
        lines = ["=== IntentOS Commands ==="]
        descriptions = {
            "status": "Show hardware, model, mode, and cost summary",
            "cost": "Detailed cost breakdown by model/task",
            "history": "Show recent 10 tasks with status",
            "credentials": "List stored credential names",
            "security": "Show security pipeline stats",
            "help": "Show this help message",
            "hardware": "Show hardware detection results",
        }
        for cmd, desc in descriptions.items():
            lines.append(f"  !{cmd:15s} {desc}")
        return "\n".join(lines)

    def cmd_hardware(self, args: List[str]) -> str:
        """Hardware detection results."""
        lines = ["=== Hardware Profile ==="]

        try:
            from core.inference.hardware import HardwareDetector

            detector = HardwareDetector()
            profile = detector.detect()
            d = profile.to_dict()

            lines.append(f"Platform  : {d['platform']}")
            lines.append(f"Arch      : {d['arch']}")
            lines.append(f"CPU       : {d['cpu_model']} ({d['cpu_cores']} cores)")
            lines.append(f"RAM       : {d['ram_gb']:.1f} GB")

            gpu = d.get("gpu")
            if gpu:
                lines.append(f"GPU       : {gpu['vendor']} {gpu['model']} ({gpu['vram_gb']:.1f} GB)")
            else:
                lines.append("GPU       : None detected")

            rec = HardwareDetector.recommend_model(profile)
            lines.append(f"Rec Model : {rec.model_name} ({rec.model_size})")
        except ImportError:
            lines.append("HardwareDetector not available.")
        except Exception as exc:
            lines.append(f"Detection error: {exc}")

        return "\n".join(lines)

    def cmd_unknown(self, args: List[str]) -> str:
        """Unknown command message."""
        return "Unknown command. Type !help for available commands."

    # ------------------------------------------------------------------
    # Internal helpers — pull data from kernel when available
    # ------------------------------------------------------------------

    def _get_hardware_summary(self) -> str:
        """One-line hardware summary."""
        try:
            from core.inference.hardware import HardwareDetector

            detector = HardwareDetector()
            profile = detector.detect()
            gpu_str = ""
            if profile.gpu:
                gpu_str = f", {profile.gpu.vendor} GPU"
            return f"{profile.cpu_model} / {profile.ram_gb:.0f}GB RAM{gpu_str}"
        except Exception:
            return "unknown"

    def _get_active_model(self) -> str:
        """Return the currently active model name."""
        if self.kernel and hasattr(self.kernel, "model"):
            return self.kernel.model
        return os.environ.get("INTENTOS_MODEL", "claude-sonnet-4-20250514")

    def _get_mode(self) -> str:
        """Return current operating mode."""
        if self.kernel and hasattr(self.kernel, "mode"):
            return self.kernel.mode
        return os.environ.get("INTENTOS_MODE", "interactive")

    def _get_total_cost(self) -> float:
        """Return total accumulated cost."""
        if self.kernel and hasattr(self.kernel, "total_cost"):
            return self.kernel.total_cost
        return 0.0

    def _get_cost_breakdown(self) -> List[Dict]:
        """Return per-model cost breakdown."""
        if self.kernel and hasattr(self.kernel, "cost_breakdown"):
            return self.kernel.cost_breakdown
        return []

    def _get_recent_tasks(self, limit: int = 10) -> List[Dict]:
        """Return recent tasks from kernel history."""
        if self.kernel and hasattr(self.kernel, "task_history"):
            history = self.kernel.task_history
            return history[-limit:] if history else []
        return []

    def _get_credential_names(self) -> List[str]:
        """Return names of stored credentials."""
        try:
            from core.security.credential_provider import CredentialProvider

            provider = CredentialProvider()
            if hasattr(provider, "list_credentials"):
                return provider.list_credentials()
        except Exception:
            pass

        # Fall back to checking common env var names
        cred_vars = [
            "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY",
            "SERPAPI_API_KEY", "STABILITY_API_KEY",
        ]
        found = [v for v in cred_vars if os.environ.get(v)]
        return found

    def _get_security_stats(self) -> Dict:
        """Return security pipeline statistics."""
        if self.kernel and hasattr(self.kernel, "security_stats"):
            return self.kernel.security_stats
        return {"tasks_scanned": 0, "threats_blocked": 0, "status": "active"}
