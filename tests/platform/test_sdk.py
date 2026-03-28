"""Tests for IntentOS Contributor SDK (Phase 4.8)."""

import json
import os
import tarfile
import tempfile
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.platform.sdk import (
    ContributorSDK,
    ValidationResult,
    TestResult,
)


@pytest.fixture
def sdk():
    return ContributorSDK()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def scaffolded_agent(sdk, tmp_dir):
    """Return path to a fully scaffolded agent."""
    sdk.scaffold("example_agent", str(tmp_dir))
    return tmp_dir / "example_agent"


# ---------- scaffold tests ----------

class TestScaffold:
    def test_scaffold_creates_directory_structure(self, sdk, tmp_dir):
        sdk.scaffold("my_agent", str(tmp_dir))
        base = tmp_dir / "my_agent"
        assert base.is_dir()
        assert (base / "agent.py").is_file()
        assert (base / "manifest.json").is_file()
        assert (base / "__init__.py").is_file()
        assert (base / "requirements.txt").is_file()
        assert (base / "tests").is_dir()
        assert (base / "tests" / "test_agent.py").is_file()
        assert (base / "SPEC.md").is_file()

    def test_scaffold_agent_py_has_run_function(self, sdk, tmp_dir):
        sdk.scaffold("my_agent", str(tmp_dir))
        content = (tmp_dir / "my_agent" / "agent.py").read_text()
        assert "def run(" in content
        assert "action" in content

    def test_scaffold_manifest_contains_agent_name(self, sdk, tmp_dir):
        sdk.scaffold("my_agent", str(tmp_dir))
        manifest = json.loads((tmp_dir / "my_agent" / "manifest.json").read_text())
        assert manifest["name"] == "my_agent"
        assert "version" in manifest
        assert "actions" in manifest

    def test_scaffold_test_template_exists(self, sdk, tmp_dir):
        sdk.scaffold("my_agent", str(tmp_dir))
        content = (tmp_dir / "my_agent" / "tests" / "test_agent.py").read_text()
        assert "def test_" in content

    def test_scaffold_rejects_non_snake_case(self, sdk, tmp_dir):
        with pytest.raises(ValueError, match="snake_case"):
            sdk.scaffold("MyAgent", str(tmp_dir))

    def test_scaffold_rejects_name_not_ending_with_agent(self, sdk, tmp_dir):
        with pytest.raises(ValueError, match="_agent"):
            sdk.scaffold("my_tool", str(tmp_dir))

    def test_scaffold_rejects_existing_directory(self, sdk, tmp_dir):
        sdk.scaffold("my_agent", str(tmp_dir))
        with pytest.raises(FileExistsError):
            sdk.scaffold("my_agent", str(tmp_dir))

    def test_scaffold_spec_md_created(self, sdk, tmp_dir):
        sdk.scaffold("my_agent", str(tmp_dir))
        content = (tmp_dir / "my_agent" / "SPEC.md").read_text()
        assert "my_agent" in content


# ---------- validate tests ----------

class TestValidate:
    def test_validate_valid_agent(self, sdk, scaffolded_agent):
        result = sdk.validate(str(scaffolded_agent))
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert result.errors == []

    def test_validate_missing_agent_py(self, sdk, scaffolded_agent):
        (scaffolded_agent / "agent.py").unlink()
        result = sdk.validate(str(scaffolded_agent))
        assert result.is_valid is False
        assert any("agent.py" in e for e in result.errors)

    def test_validate_missing_manifest(self, sdk, scaffolded_agent):
        (scaffolded_agent / "manifest.json").unlink()
        result = sdk.validate(str(scaffolded_agent))
        assert result.is_valid is False
        assert any("manifest.json" in e for e in result.errors)

    def test_validate_missing_run_function(self, sdk, scaffolded_agent):
        (scaffolded_agent / "agent.py").write_text("# no run function\n")
        result = sdk.validate(str(scaffolded_agent))
        assert result.is_valid is False
        assert any("run()" in e for e in result.errors)

    def test_validate_invalid_semver(self, sdk, scaffolded_agent):
        manifest = json.loads((scaffolded_agent / "manifest.json").read_text())
        manifest["version"] = "not-a-version"
        (scaffolded_agent / "manifest.json").write_text(json.dumps(manifest))
        result = sdk.validate(str(scaffolded_agent))
        assert result.is_valid is False
        assert any("semver" in e.lower() or "version" in e.lower() for e in result.errors)

    def test_validate_missing_permissions(self, sdk, scaffolded_agent):
        manifest = json.loads((scaffolded_agent / "manifest.json").read_text())
        del manifest["permissions"]
        (scaffolded_agent / "manifest.json").write_text(json.dumps(manifest))
        result = sdk.validate(str(scaffolded_agent))
        assert result.is_valid is False
        assert any("permission" in e.lower() for e in result.errors)

    def test_validate_action_without_test(self, sdk, scaffolded_agent):
        # Add an action to manifest that has no corresponding test
        manifest = json.loads((scaffolded_agent / "manifest.json").read_text())
        manifest["actions"].append({"name": "untested_action", "description": "No test"})
        (scaffolded_agent / "manifest.json").write_text(json.dumps(manifest))
        result = sdk.validate(str(scaffolded_agent))
        # Should produce a warning about untested action
        assert any("untested_action" in w for w in result.warnings)

    def test_validate_returns_warnings_list(self, sdk, scaffolded_agent):
        result = sdk.validate(str(scaffolded_agent))
        assert isinstance(result.warnings, list)


# ---------- run_tests tests ----------

class TestRunTests:
    def test_run_tests_returns_test_result(self, sdk, scaffolded_agent):
        result = sdk.run_tests(str(scaffolded_agent))
        assert isinstance(result, TestResult)
        assert isinstance(result.passed, int)
        assert isinstance(result.failed, int)
        assert isinstance(result.total, int)
        assert isinstance(result.output, str)

    def test_run_tests_discovers_tests(self, sdk, scaffolded_agent):
        result = sdk.run_tests(str(scaffolded_agent))
        assert result.total >= 1
        assert result.passed >= 1


# ---------- build tests ----------

class TestBuild:
    def test_build_creates_tarball(self, sdk, scaffolded_agent, tmp_dir):
        out_dir = tmp_dir / "dist"
        out_dir.mkdir()
        bundle = sdk.build(str(scaffolded_agent), str(out_dir))
        assert Path(bundle).exists()
        assert bundle.endswith(".tar.gz")

    def test_build_tarball_contains_manifest(self, sdk, scaffolded_agent, tmp_dir):
        out_dir = tmp_dir / "dist"
        out_dir.mkdir()
        bundle = sdk.build(str(scaffolded_agent), str(out_dir))
        with tarfile.open(bundle, "r:gz") as tar:
            names = tar.getnames()
            assert any("MANIFEST.json" in n for n in names)

    def test_build_tarball_contains_checksums(self, sdk, scaffolded_agent, tmp_dir):
        out_dir = tmp_dir / "dist"
        out_dir.mkdir()
        bundle = sdk.build(str(scaffolded_agent), str(out_dir))
        with tarfile.open(bundle, "r:gz") as tar:
            names = tar.getnames()
            assert any("SHA256SUMS" in n for n in names)

    def test_build_checksums_are_valid(self, sdk, scaffolded_agent, tmp_dir):
        out_dir = tmp_dir / "dist"
        out_dir.mkdir()
        bundle = sdk.build(str(scaffolded_agent), str(out_dir))
        with tarfile.open(bundle, "r:gz") as tar:
            sums_member = [m for m in tar.getmembers() if "SHA256SUMS" in m.name][0]
            sums_content = tar.extractfile(sums_member).read().decode()
            assert "agent.py" in sums_content


# ---------- generate_manifest tests ----------

class TestGenerateManifest:
    def test_generate_manifest_detects_actions(self, sdk, scaffolded_agent):
        manifest = sdk.generate_manifest(str(scaffolded_agent))
        assert manifest["name"] == "example_agent"
        assert "actions" in manifest
        assert len(manifest["actions"]) >= 1

    def test_generate_manifest_from_custom_agent(self, sdk, tmp_dir):
        agent_dir = tmp_dir / "custom_agent"
        agent_dir.mkdir()
        (agent_dir / "__init__.py").write_text("")
        (agent_dir / "agent.py").write_text(
            'def run(action: str, **kwargs):\n'
            '    if action == "greet":\n'
            '        return {"message": "hello"}\n'
            '    elif action == "farewell":\n'
            '        return {"message": "bye"}\n'
        )
        manifest = sdk.generate_manifest(str(agent_dir))
        action_names = [a["name"] for a in manifest["actions"]]
        assert "greet" in action_names
        assert "farewell" in action_names


# ---------- edge case tests ----------

class TestEdgeCases:
    def test_build_bundle_name_includes_version(self, sdk, scaffolded_agent, tmp_dir):
        out_dir = tmp_dir / "dist"
        out_dir.mkdir()
        bundle = sdk.build(str(scaffolded_agent), str(out_dir))
        assert "0.1.0" in Path(bundle).name
