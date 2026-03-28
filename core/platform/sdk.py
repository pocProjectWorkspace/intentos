"""IntentOS Contributor SDK (Phase 4.8) -- CLI tools for building and publishing agents."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import tarfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class TestResult:
    passed: int
    failed: int
    total: int
    output: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _detect_actions(agent_py_path: Path) -> List[str]:
    """Parse agent.py to find action names dispatched in run()."""
    source = agent_py_path.read_text()
    actions: List[str] = []

    # Look for string comparisons with action: action == "name" or action == 'name'
    pattern = re.compile(r"""action\s*==\s*['"]([^'"]+)['"]""")
    actions = pattern.findall(source)
    return list(dict.fromkeys(actions))  # dedupe, preserve order


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def _agent_py_template(agent_name: str) -> str:
    return textwrap.dedent(f'''\
        """IntentOS Agent: {agent_name}"""

        from typing import Any, Dict


        def run(action: str, **kwargs) -> Dict[str, Any]:
            """ACP-compliant entry point.

            Args:
                action: The action to execute.
                **kwargs: Action-specific parameters.

            Returns:
                Dict with action results.
            """
            if action == "hello":
                name = kwargs.get("name", "world")
                return {{"message": f"Hello, {{name}}!"}}
            else:
                return {{"error": f"Unknown action: {{action}}"}}
    ''')


def _manifest_template(agent_name: str) -> str:
    manifest = {
        "name": agent_name,
        "version": "0.1.0",
        "description": f"IntentOS agent: {agent_name}",
        "actions": [
            {"name": "hello", "description": "Greet a user by name."}
        ],
        "permissions": ["network"],
        "entry_point": "agent.py",
    }
    return json.dumps(manifest, indent=2) + "\n"


def _test_template(agent_name: str) -> str:
    return textwrap.dedent(f'''\
        """Tests for {agent_name}."""

        import sys
        from pathlib import Path

        # Ensure agent package is importable
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

        from agent import run


        def test_hello_action():
            result = run("hello", name="IntentOS")
            assert result["message"] == "Hello, IntentOS!"


        def test_unknown_action():
            result = run("unknown")
            assert "error" in result
    ''')


def _spec_template(agent_name: str) -> str:
    return textwrap.dedent(f"""\
        # {agent_name} Specification

        ## Overview
        Describe the purpose of **{agent_name}** here.

        ## Actions
        - `hello` -- Greet a user by name.

        ## Permissions
        - `network`

        ## Testing
        Run `pytest tests/` from the agent directory.
    """)


# ---------------------------------------------------------------------------
# ContributorSDK
# ---------------------------------------------------------------------------

class ContributorSDK:
    """SDK for scaffolding, validating, testing, building, and publishing IntentOS agents."""

    # ---- scaffold ----

    def scaffold(self, agent_name: str, target_dir: str) -> Path:
        """Create a new agent project from templates.

        Args:
            agent_name: Must be snake_case and end with ``_agent``.
            target_dir: Parent directory where the agent folder will be created.

        Returns:
            Path to the newly created agent directory.

        Raises:
            ValueError: If *agent_name* is invalid.
            FileExistsError: If the agent directory already exists.
        """
        # Validate name
        if not _SNAKE_CASE_RE.match(agent_name):
            raise ValueError(
                f"Agent name '{agent_name}' must be snake_case "
                "(lowercase letters, digits, underscores)."
            )
        if not agent_name.endswith("_agent"):
            raise ValueError(
                f"Agent name '{agent_name}' must end with '_agent'."
            )

        base = Path(target_dir) / agent_name
        if base.exists():
            raise FileExistsError(f"Directory already exists: {base}")

        base.mkdir(parents=True)
        (base / "agent.py").write_text(_agent_py_template(agent_name))
        (base / "manifest.json").write_text(_manifest_template(agent_name))
        (base / "__init__.py").write_text("")
        (base / "requirements.txt").write_text("")
        tests_dir = base / "tests"
        tests_dir.mkdir()
        (tests_dir / "__init__.py").write_text("")
        (tests_dir / "test_agent.py").write_text(_test_template(agent_name))
        (base / "SPEC.md").write_text(_spec_template(agent_name))

        return base

    # ---- validate ----

    def validate(self, agent_dir: str) -> ValidationResult:
        """Validate an agent directory against the IntentOS spec.

        Returns a :class:`ValidationResult` with ``is_valid``, ``errors``, and
        ``warnings``.
        """
        d = Path(agent_dir)
        errors: List[str] = []
        warnings: List[str] = []

        # 1. agent.py must exist
        agent_py = d / "agent.py"
        if not agent_py.is_file():
            errors.append("Missing required file: agent.py")
        else:
            source = agent_py.read_text()
            if "def run(" not in source:
                errors.append("agent.py must define a run() function.")

        # 2. manifest.json must exist and be valid
        manifest_path = d / "manifest.json"
        manifest: Optional[Dict[str, Any]] = None
        if not manifest_path.is_file():
            errors.append("Missing required file: manifest.json")
        else:
            try:
                manifest = json.loads(manifest_path.read_text())
            except json.JSONDecodeError as exc:
                errors.append(f"manifest.json is not valid JSON: {exc}")

        if manifest is not None:
            # version must be semver
            version = manifest.get("version", "")
            if not _SEMVER_RE.match(str(version)):
                errors.append(
                    f"Version '{version}' is not valid semver (expected MAJOR.MINOR.PATCH)."
                )

            # permissions must be declared
            if "permissions" not in manifest:
                errors.append("manifest.json must declare 'permissions' (may be empty list).")

            # actions without tests -> warnings
            actions = manifest.get("actions", [])
            tests_dir = d / "tests"
            test_sources = ""
            if tests_dir.is_dir():
                for tf in tests_dir.glob("*.py"):
                    test_sources += tf.read_text()
            for act in actions:
                act_name = act.get("name", "")
                if act_name and act_name not in test_sources:
                    warnings.append(
                        f"Action '{act_name}' declared in manifest has no corresponding test."
                    )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # ---- run_tests ----

    def run_tests(self, agent_dir: str) -> TestResult:
        """Discover and run pytest in the agent's ``tests/`` directory.

        Returns a :class:`TestResult` summarising passed / failed / total.
        """
        d = Path(agent_dir)
        tests_dir = d / "tests"

        result = subprocess.run(
            ["python", "-m", "pytest", str(tests_dir), "-v", "--tb=short"],
            capture_output=True,
            text=True,
            cwd=str(d),
        )

        output = result.stdout + result.stderr

        # Parse pytest summary line, e.g. "2 passed", "1 failed, 1 passed"
        passed = failed = 0
        m_passed = re.search(r"(\d+) passed", output)
        m_failed = re.search(r"(\d+) failed", output)
        if m_passed:
            passed = int(m_passed.group(1))
        if m_failed:
            failed = int(m_failed.group(1))

        return TestResult(
            passed=passed,
            failed=failed,
            total=passed + failed,
            output=output,
        )

    # ---- build ----

    def build(self, agent_dir: str, output_dir: str) -> str:
        """Build a distributable ``.tar.gz`` bundle.

        The archive contains:
        - The agent directory (code, manifest, requirements).
        - ``MANIFEST.json`` at the archive root.
        - ``SHA256SUMS`` with checksums for every included file.

        Returns the path to the created bundle.
        """
        d = Path(agent_dir)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        agent_name = d.name
        manifest_path = d / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {"name": agent_name}

        # Collect files
        files: List[Path] = []
        for root, _dirs, filenames in os.walk(d):
            for fn in filenames:
                fp = Path(root) / fn
                if fp.suffix == ".pyc" or "__pycache__" in str(fp):
                    continue
                files.append(fp)

        # Compute checksums
        checksums: List[str] = []
        for fp in sorted(files):
            rel = fp.relative_to(d)
            checksums.append(f"{_sha256(fp)}  {rel}")

        bundle_name = f"{agent_name}-{manifest.get('version', '0.0.0')}.tar.gz"
        bundle_path = out / bundle_name

        with tarfile.open(str(bundle_path), "w:gz") as tar:
            # Add agent files under agent_name/
            for fp in files:
                arcname = f"{agent_name}/{fp.relative_to(d)}"
                tar.add(str(fp), arcname=arcname)

            # MANIFEST.json at root
            import io
            manifest_bytes = json.dumps(manifest, indent=2).encode()
            ti = tarfile.TarInfo(name="MANIFEST.json")
            ti.size = len(manifest_bytes)
            tar.addfile(ti, io.BytesIO(manifest_bytes))

            # SHA256SUMS at root
            sums_bytes = "\n".join(checksums).encode()
            ti2 = tarfile.TarInfo(name="SHA256SUMS")
            ti2.size = len(sums_bytes)
            tar.addfile(ti2, io.BytesIO(sums_bytes))

        return str(bundle_path)

    # ---- generate_manifest ----

    def generate_manifest(self, agent_dir: str) -> Dict[str, Any]:
        """Introspect ``agent.py`` to auto-detect actions and generate a manifest dict."""
        d = Path(agent_dir)
        agent_py = d / "agent.py"
        agent_name = d.name

        actions = _detect_actions(agent_py)

        return {
            "name": agent_name,
            "version": "0.1.0",
            "description": f"Auto-generated manifest for {agent_name}",
            "actions": [{"name": a, "description": ""} for a in actions],
            "permissions": [],
            "entry_point": "agent.py",
        }
