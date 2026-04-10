"""OllamaManager — lifecycle management for Ollama local inference engine.

Handles detection, installation, daemon startup, and model pulling
with progress feedback. Uses only stdlib dependencies.

Standalone usage:
    python -m core.inference.ollama_manager --status
    python -m core.inference.ollama_manager --install
    python -m core.inference.ollama_manager --pull llama3.1:8b
    python -m core.inference.ollama_manager --setup auto
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class OllamaStatus:
    """Aggregate status of the Ollama installation."""
    installed: bool = False
    running: bool = False
    version: str = ""
    models_available: List[str] = field(default_factory=list)
    base_url: str = "http://localhost:11434"


@dataclass
class PullProgress:
    """Progress update during a model pull."""
    model: str = ""
    status: str = ""       # downloading, unpacking, verifying, complete, error
    percent: float = 0.0
    downloaded_gb: float = 0.0
    total_gb: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class OllamaError(Exception):
    """Base exception for Ollama operations."""


class OllamaInstallError(OllamaError):
    """Raised when Ollama installation fails."""


class OllamaConnectionError(OllamaError):
    """Raised when Ollama daemon is unreachable."""


class OllamaModelPullError(OllamaError):
    """Raised when a model pull fails."""


# ---------------------------------------------------------------------------
# Approximate model sizes (GB) for disk space checks
# ---------------------------------------------------------------------------

_MODEL_SIZES_GB: Dict[str, float] = {
    # Gemma 4 (April 2026) — native function calling, agentic workflows
    "gemma4:e2b": 1.5,
    "gemma4:e4b": 3.6,
    "gemma4:26b-a4b": 16.0,
    "gemma4:31b": 18.0,
    # Gemma 3
    "gemma3:1b": 0.8,
    "gemma3:4b": 3.3,
    "gemma3:12b": 8.1,
    "gemma3:27b": 17.0,
    # Legacy models
    "qwen2.5:1.5b": 1.0,
    "phi3:mini": 2.3,
    "mistral:7b-instruct-q4_0": 4.0,
    "llama3.1:8b": 4.7,
    "llama3.1:70b-instruct-q4_0": 40.0,
    "nomic-embed-text": 0.3,
    "moondream2": 1.7,
}

# Embedding model pulled alongside the LLM
EMBEDDING_MODEL = "nomic-embed-text"


# ---------------------------------------------------------------------------
# OllamaManager
# ---------------------------------------------------------------------------

class OllamaManager:
    """Manages Ollama lifecycle: install, start, pull models, check status."""

    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self._base_url = base_url.rstrip("/")

    # -- Detection ----------------------------------------------------------

    @staticmethod
    def is_installed() -> bool:
        """Check if the ollama binary is on PATH."""
        return shutil.which("ollama") is not None

    @staticmethod
    def get_version() -> str:
        """Return Ollama version string, or empty string if unavailable."""
        try:
            result = subprocess.run(
                ["ollama", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                # Output format: "ollama version 0.3.14" or just "0.3.14"
                text = result.stdout.strip()
                if "version" in text:
                    return text.split("version")[-1].strip()
                return text
        except Exception:
            pass
        return ""

    def is_running(self) -> bool:
        """Check if the Ollama daemon is responding."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=3):
                return True
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """Return names of locally available models."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read())
            models = body.get("models", [])
            return [m.get("name", "") for m in models if m.get("name")]
        except Exception:
            return []

    def has_model(self, model_name: str) -> bool:
        """Check if a specific model is already pulled."""
        available = self.list_models()
        # Match with or without tag suffix (e.g. "llama3.1:8b" matches "llama3.1:8b")
        for m in available:
            if m == model_name or m.startswith(model_name.split(":")[0] + ":"):
                if model_name in m or m == model_name:
                    return True
        return model_name in available

    def get_status(self) -> OllamaStatus:
        """Aggregate check: installed, running, version, models."""
        installed = self.is_installed()
        running = self.is_running() if installed else False
        version = self.get_version() if installed else ""
        models = self.list_models() if running else []
        return OllamaStatus(
            installed=installed,
            running=running,
            version=version,
            models_available=models,
            base_url=self._base_url,
        )

    # -- Installation -------------------------------------------------------

    @staticmethod
    def install(silent: bool = False) -> bool:
        """Install Ollama for the current platform. Returns True on success."""
        plat = platform.system().lower()
        if plat == "darwin":
            return OllamaManager._install_macos(silent)
        elif plat == "windows":
            return OllamaManager._install_windows(silent)
        elif plat == "linux":
            return OllamaManager._install_linux(silent)
        else:
            raise OllamaInstallError(f"Unsupported platform: {plat}")

    @staticmethod
    def _install_macos(silent: bool) -> bool:
        """macOS: try brew, fallback to curl installer."""
        # Try Homebrew first
        if shutil.which("brew"):
            try:
                args = ["brew", "install", "ollama"]
                if silent:
                    args.append("--quiet")
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=300,
                )
                if result.returncode == 0 and shutil.which("ollama"):
                    return True
            except Exception:
                pass

        # Fallback: curl installer
        try:
            result = subprocess.run(
                ["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
                capture_output=True, text=True, timeout=300,
            )
            return result.returncode == 0 and shutil.which("ollama") is not None
        except Exception as exc:
            raise OllamaInstallError(
                "Could not install the local AI engine. "
                "You can install it manually from https://ollama.com/download"
            ) from exc

    @staticmethod
    def _install_windows(silent: bool) -> bool:
        """Windows: try winget, fallback to direct download."""
        # Try winget
        if shutil.which("winget"):
            try:
                args = [
                    "winget", "install", "Ollama.Ollama",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ]
                if silent:
                    args.append("--silent")
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=300,
                )
                if result.returncode == 0:
                    # Refresh PATH
                    _refresh_windows_path()
                    if shutil.which("ollama"):
                        return True
            except Exception:
                pass

        # Fallback: direct download
        try:
            installer_url = "https://ollama.com/download/OllamaSetup.exe"
            installer_path = os.path.join(
                os.environ.get("TEMP", "."), "OllamaSetup.exe"
            )
            urllib.request.urlretrieve(installer_url, installer_path)
            result = subprocess.run(
                [installer_path, "/S"],
                capture_output=True, text=True, timeout=300,
            )
            try:
                os.unlink(installer_path)
            except OSError:
                pass
            _refresh_windows_path()
            return shutil.which("ollama") is not None
        except Exception as exc:
            raise OllamaInstallError(
                "Could not install the local AI engine. "
                "You can install it manually from https://ollama.com/download"
            ) from exc

    @staticmethod
    def _install_linux(silent: bool) -> bool:
        """Linux: curl installer."""
        try:
            result = subprocess.run(
                ["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
                capture_output=True, text=True, timeout=300,
            )
            return result.returncode == 0 and shutil.which("ollama") is not None
        except Exception as exc:
            raise OllamaInstallError(
                "Could not install the local AI engine. "
                "You can install it manually from https://ollama.com/download"
            ) from exc

    # -- Daemon management --------------------------------------------------

    def start_daemon(self) -> bool:
        """Start ollama serve in the background. Returns True when ready."""
        if self.is_running():
            return True

        if not self.is_installed():
            return False

        # Log file for daemon output
        log_dir = Path.home() / ".intentos" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "ollama.log"

        try:
            kwargs: Dict[str, Any] = {
                "stdout": open(log_file, "a"),
                "stderr": subprocess.STDOUT,
            }
            # Windows: hide the console window
            if platform.system().lower() == "windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            subprocess.Popen(["ollama", "serve"], **kwargs)
        except Exception:
            return False

        # Poll for readiness (up to 10 seconds)
        for _ in range(20):
            time.sleep(0.5)
            if self.is_running():
                return True

        return False

    def ensure_running(self) -> bool:
        """Ensure Ollama is installed and running. Returns True when ready."""
        if not self.is_installed():
            return False
        if self.is_running():
            return True
        return self.start_daemon()

    # -- Model pulling ------------------------------------------------------

    def pull_model(
        self,
        model_name: str,
        progress_callback: Optional[Callable[[PullProgress], None]] = None,
    ) -> bool:
        """Pull a model via Ollama API with streaming progress.

        Returns True on success.
        """
        if not self.is_running():
            raise OllamaConnectionError(
                "The local AI engine is not running. "
                "Start it first or restart IntentOS."
            )

        try:
            payload = json.dumps({
                "name": model_name,
                "stream": True,
            }).encode()
            req = urllib.request.Request(
                f"{self._base_url}/api/pull",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=1800) as resp:
                for line in resp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if progress_callback:
                        progress = _parse_pull_progress(model_name, data)
                        progress_callback(progress)

                    # Check for error in stream
                    if "error" in data:
                        raise OllamaModelPullError(
                            f"Download failed for {model_name}: {data['error']}"
                        )

            return True

        except OllamaModelPullError:
            raise
        except urllib.error.URLError as exc:
            raise OllamaConnectionError(
                "Lost connection to the local AI engine during download."
            ) from exc
        except Exception as exc:
            raise OllamaModelPullError(
                f"Download failed for {model_name}: {exc}"
            ) from exc

    def ensure_model(
        self,
        model_name: str,
        progress_callback: Optional[Callable[[PullProgress], None]] = None,
    ) -> bool:
        """Pull a model only if not already available."""
        if self.has_model(model_name):
            if progress_callback:
                progress_callback(PullProgress(
                    model=model_name, status="complete", percent=100.0,
                ))
            return True
        return self.pull_model(model_name, progress_callback)

    # -- Disk space check ---------------------------------------------------

    @staticmethod
    def check_disk_space(model_name: str) -> Optional[str]:
        """Return a warning string if disk space is insufficient, else None."""
        needed_gb = _MODEL_SIZES_GB.get(model_name, 5.0) + 2.0  # 2GB buffer
        try:
            usage = shutil.disk_usage(Path.home())
            free_gb = usage.free / (1024 ** 3)
            if free_gb < needed_gb:
                return (
                    f"You need about {needed_gb:.0f} GB of free space, "
                    f"but only {free_gb:.1f} GB is available."
                )
        except Exception:
            pass
        return None

    # -- Convenience: full local setup --------------------------------------

    def setup_for_local(
        self,
        recommended_model: str,
        progress_callback: Optional[Callable[[PullProgress], None]] = None,
    ) -> Dict[str, Any]:
        """Full lifecycle: ensure running, pull recommended model + embeddings.

        Returns dict with 'success', 'models_pulled', 'errors'.
        """
        result: Dict[str, Any] = {
            "success": False,
            "models_pulled": [],
            "errors": [],
        }

        # Ensure daemon is running
        if not self.ensure_running():
            result["errors"].append(
                "Could not start the local AI engine. "
                "Try restarting your computer or reinstalling Ollama."
            )
            return result

        # Pull recommended model
        models_to_pull = [recommended_model, EMBEDDING_MODEL]
        for model in models_to_pull:
            try:
                self.ensure_model(model, progress_callback)
                result["models_pulled"].append(model)
            except (OllamaModelPullError, OllamaConnectionError) as exc:
                result["errors"].append(str(exc))

        result["success"] = len(result["models_pulled"]) > 0
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_pull_progress(model_name: str, data: dict) -> PullProgress:
    """Parse a streaming JSON line from /api/pull into a PullProgress."""
    status_raw = data.get("status", "")
    completed = data.get("completed", 0)
    total = data.get("total", 0)

    # Map Ollama status strings to user-friendly labels
    if "pulling" in status_raw or "downloading" in status_raw:
        status = "downloading"
    elif "verifying" in status_raw:
        status = "verifying"
    elif "writing" in status_raw or "removing" in status_raw:
        status = "unpacking"
    elif status_raw == "success":
        status = "complete"
    else:
        status = status_raw or "downloading"

    percent = 0.0
    if total > 0:
        percent = min((completed / total) * 100, 100.0)
    elif status == "complete":
        percent = 100.0

    return PullProgress(
        model=model_name,
        status=status,
        percent=round(percent, 1),
        downloaded_gb=round(completed / (1024 ** 3), 2) if completed else 0.0,
        total_gb=round(total / (1024 ** 3), 2) if total else 0.0,
    )


def _refresh_windows_path() -> None:
    """Refresh PATH from the registry on Windows."""
    try:
        machine = os.environ.get("PATH", "")
        user_path = subprocess.run(
            ["powershell", "-Command",
             "[System.Environment]::GetEnvironmentVariable('PATH', 'User')"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        sys_path = subprocess.run(
            ["powershell", "-Command",
             "[System.Environment]::GetEnvironmentVariable('PATH', 'Machine')"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if user_path or sys_path:
            os.environ["PATH"] = f"{sys_path};{user_path}"
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CLI entry point (used by setup scripts)
# ---------------------------------------------------------------------------

def _cli_progress(progress: PullProgress) -> None:
    """Print progress to stdout for CLI usage."""
    if progress.status == "complete":
        print(f"  [ok] {progress.model} ready")
    elif progress.status == "error":
        print(f"  [!!] {progress.model}: {progress.error}")
    elif progress.total_gb > 0:
        bar_width = 20
        filled = int(bar_width * progress.percent / 100)
        bar = "=" * filled + "-" * (bar_width - filled)
        print(
            f"\r  [{bar}] {progress.percent:5.1f}%  {progress.status}",
            end="", flush=True,
        )
    else:
        print(f"\r  {progress.status}...", end="", flush=True)


def main() -> None:
    """CLI entry point for setup scripts and debugging."""
    args = sys.argv[1:]

    if not args or "--help" in args:
        print("Usage: python -m core.inference.ollama_manager [OPTIONS]")
        print("  --status          Show Ollama status")
        print("  --install         Install Ollama")
        print("  --start           Start Ollama daemon")
        print("  --pull MODEL      Pull a specific model")
        print("  --setup auto      Full setup: install + start + pull recommended model")
        return

    manager = OllamaManager()

    if "--status" in args:
        status = manager.get_status()
        print(f"  Installed:  {status.installed}")
        print(f"  Running:    {status.running}")
        print(f"  Version:    {status.version or 'N/A'}")
        print(f"  Models:     {', '.join(status.models_available) or 'none'}")
        return

    if "--install" in args:
        if manager.is_installed():
            print("  [ok] Ollama already installed")
        else:
            print("  [..] Installing Ollama...")
            try:
                success = manager.install(silent=True)
                if success:
                    print("  [ok] Ollama installed")
                else:
                    print("  [!!] Installation failed")
                    sys.exit(1)
            except OllamaInstallError as exc:
                print(f"  [!!] {exc}")
                sys.exit(1)
        return

    if "--start" in args:
        if manager.is_running():
            print("  [ok] Ollama already running")
        else:
            print("  [..] Starting Ollama...")
            if manager.start_daemon():
                print("  [ok] Ollama running")
            else:
                print("  [!!] Could not start Ollama")
                sys.exit(1)
        return

    if "--pull" in args:
        idx = args.index("--pull")
        if idx + 1 >= len(args):
            print("  [!!] --pull requires a model name")
            sys.exit(1)
        model = args[idx + 1]
        if not manager.ensure_running():
            print("  [!!] Ollama is not running")
            sys.exit(1)
        print(f"  [..] Pulling {model}...")
        try:
            manager.pull_model(model, _cli_progress)
            print()  # newline after progress bar
        except OllamaError as exc:
            print(f"\n  [!!] {exc}")
            sys.exit(1)
        return

    if "--setup" in args:
        # Full auto setup: detect hardware, install, start, pull
        print("  [..] Setting up local AI engine...")

        # Install if needed
        if not manager.is_installed():
            print("  [..] Installing Ollama...")
            try:
                manager.install(silent=True)
                print("  [ok] Ollama installed")
            except OllamaInstallError as exc:
                print(f"  [!!] {exc}")
                sys.exit(1)

        # Start daemon
        if not manager.ensure_running():
            print("  [!!] Could not start Ollama")
            sys.exit(1)
        print("  [ok] Ollama running")

        # Detect hardware and recommend model
        from core.inference.hardware import HardwareDetector
        detector = HardwareDetector()
        profile = detector.detect()
        rec = detector.recommend_model(profile)
        print(f"  [ok] Recommended local AI: {rec.model_name} ({rec.reason})")

        # Pull models
        result = manager.setup_for_local(rec.model_name, _cli_progress)
        print()  # newline after progress
        if result["success"]:
            print(f"  [ok] Ready — {len(result['models_pulled'])} components set up")
        else:
            for err in result["errors"]:
                print(f"  [!!] {err}")
            sys.exit(1)
        return

    print("  Unknown option. Use --help for usage.")


if __name__ == "__main__":
    main()
