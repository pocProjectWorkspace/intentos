"""Tests for core.config — IntentOS Configuration System."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base(tmp_path):
    """Return a temporary base_path that acts like ~/.intentos."""
    return tmp_path / ".intentos"


# ===========================================================================
# WorkspaceManager — Directory Structure (tests 1-7)
# ===========================================================================

class TestWorkspaceManagerDirectories:
    """Tests 1-7: directory creation and path accessors."""

    def test_ensure_workspace_creates_full_tree(self, base):
        """Test 1: ensure_workspace creates the full directory tree."""
        from core.config import WorkspaceManager

        wm = WorkspaceManager(base_path=base)
        wm.ensure_workspace()

        expected_dirs = [
            base,
            base / "workspace" / "outputs",
            base / "workspace" / "temp",
            base / "workspace" / "exports",
            base / "rag",
            base / "logs",
            base / "cache" / "thumbs",
        ]
        for d in expected_dirs:
            assert d.is_dir(), f"Expected directory missing: {d}"

    def test_ensure_workspace_idempotent(self, base):
        """Test 2: calling ensure_workspace twice does not error."""
        from core.config import WorkspaceManager

        wm = WorkspaceManager(base_path=base)
        wm.ensure_workspace()
        wm.ensure_workspace()  # should not raise

    def test_get_workspace_path(self, base):
        """Test 3: get_workspace_path returns base/workspace."""
        from core.config import WorkspaceManager

        wm = WorkspaceManager(base_path=base)
        assert wm.get_workspace_path() == base / "workspace"

    def test_get_outputs_path(self, base):
        """Test 4: get_outputs_path returns base/workspace/outputs."""
        from core.config import WorkspaceManager

        wm = WorkspaceManager(base_path=base)
        assert wm.get_outputs_path() == base / "workspace" / "outputs"

    def test_get_logs_path(self, base):
        """Test 5: get_logs_path returns base/logs."""
        from core.config import WorkspaceManager

        wm = WorkspaceManager(base_path=base)
        assert wm.get_logs_path() == base / "logs"

    def test_get_rag_path(self, base):
        """Test 6: get_rag_path returns base/rag."""
        from core.config import WorkspaceManager

        wm = WorkspaceManager(base_path=base)
        assert wm.get_rag_path() == base / "rag"

    def test_paths_use_base_path_parameter(self, tmp_path):
        """Test 7: all paths are rooted under the given base_path."""
        from core.config import WorkspaceManager

        custom = tmp_path / "custom_base"
        wm = WorkspaceManager(base_path=custom)
        wm.ensure_workspace()

        assert str(wm.get_workspace_path()).startswith(str(custom))
        assert str(wm.get_outputs_path()).startswith(str(custom))
        assert str(wm.get_logs_path()).startswith(str(custom))
        assert str(wm.get_rag_path()).startswith(str(custom))


# ===========================================================================
# Settings (tests 8-15)
# ===========================================================================

class TestSettings:
    """Tests 8-15: Settings model and persistence."""

    def test_settings_defaults(self, base):
        """Test 8: Settings has correct default values."""
        from core.config import Settings

        s = Settings()
        assert s.privacy_mode == "smart_routing"
        assert s.local_model == "phi3:mini"
        assert s.cloud_model == "claude-sonnet-4-20250514"
        assert s.cloud_provider == "anthropic"
        assert s.auto_compact_threshold == 50
        assert s.max_context_tokens == 4000
        assert s.theme == "dark"
        assert s.language == "en"
        assert s.verbose is False

    def test_load_settings_returns_defaults_when_missing(self, base):
        """Test 9/13: load_settings with no file returns defaults."""
        from core.config import load_settings, Settings

        base.mkdir(parents=True, exist_ok=True)
        s = load_settings(base_path=base)
        default = Settings()
        assert s.privacy_mode == default.privacy_mode
        assert s.cloud_model == default.cloud_model

    def test_save_settings_writes_file(self, base):
        """Test 10: save_settings writes settings.json."""
        from core.config import Settings, save_settings

        base.mkdir(parents=True, exist_ok=True)
        s = Settings()
        save_settings(s, base_path=base)
        assert (base / "settings.json").is_file()

    def test_update_settings_merges(self, base):
        """Test 11: update_settings merges partial updates."""
        from core.config import Settings, save_settings, update_settings, load_settings

        base.mkdir(parents=True, exist_ok=True)
        save_settings(Settings(), base_path=base)
        update_settings({"theme": "light", "verbose": True}, base_path=base)
        s = load_settings(base_path=base)
        assert s.theme == "light"
        assert s.verbose is True
        # untouched fields keep defaults
        assert s.language == "en"

    def test_settings_round_trip(self, base):
        """Test 12: save then load preserves all values."""
        from core.config import Settings, save_settings, load_settings

        base.mkdir(parents=True, exist_ok=True)
        original = Settings(
            privacy_mode="local_only",
            local_model="llama3",
            cloud_model="gpt-4",
            cloud_provider="openai",
            auto_compact_threshold=100,
            max_context_tokens=8000,
            theme="light",
            language="fr",
            verbose=True,
        )
        save_settings(original, base_path=base)
        loaded = load_settings(base_path=base)
        assert loaded.privacy_mode == original.privacy_mode
        assert loaded.local_model == original.local_model
        assert loaded.cloud_model == original.cloud_model
        assert loaded.cloud_provider == original.cloud_provider
        assert loaded.auto_compact_threshold == original.auto_compact_threshold
        assert loaded.max_context_tokens == original.max_context_tokens
        assert loaded.theme == original.theme
        assert loaded.language == original.language
        assert loaded.verbose == original.verbose

    def test_corrupted_settings_returns_defaults(self, base, caplog):
        """Test 14: corrupted settings.json returns defaults with warning."""
        from core.config import load_settings, Settings

        base.mkdir(parents=True, exist_ok=True)
        (base / "settings.json").write_text("{this is not valid json!!!")
        with caplog.at_level(logging.WARNING):
            s = load_settings(base_path=base)
        default = Settings()
        assert s.privacy_mode == default.privacy_mode
        assert any("settings" in r.message.lower() or "corrupt" in r.message.lower()
                    or "default" in r.message.lower() for r in caplog.records)

    def test_partial_settings_fills_defaults(self, base):
        """Test 15: partial settings.json fills missing fields with defaults."""
        from core.config import load_settings, Settings

        base.mkdir(parents=True, exist_ok=True)
        (base / "settings.json").write_text(json.dumps({"theme": "solarized"}))
        s = load_settings(base_path=base)
        assert s.theme == "solarized"
        # missing fields → defaults
        default = Settings()
        assert s.privacy_mode == default.privacy_mode
        assert s.verbose == default.verbose


# ===========================================================================
# Grants (tests 16-28)
# ===========================================================================

class TestGrants:
    """Tests 16-28: Grants model, persistence, and path checks."""

    def test_granted_path_model(self):
        """Test 17: GrantedPath has required fields."""
        from core.config import GrantedPath

        gp = GrantedPath(
            path="/tmp/test",
            access="read_write",
            recursive=True,
            granted_at=datetime.now(),
        )
        assert gp.path == "/tmp/test"
        assert gp.access == "read_write"
        assert gp.recursive is True
        assert isinstance(gp.granted_at, datetime)

    def test_grants_model(self):
        """Test 16: Grants model has expected fields."""
        from core.config import Grants, GrantedPath

        g = Grants(
            version="1.0",
            user="tester",
            granted_paths=[
                GrantedPath(path="/tmp", access="read", recursive=True,
                            granted_at=datetime.now())
            ],
            denied_paths=["~/.ssh"],
            allow_external_drives=False,
            allow_network_drives=False,
        )
        assert g.version == "1.0"
        assert len(g.granted_paths) == 1
        assert g.denied_paths == ["~/.ssh"]

    def test_load_grants_returns_defaults(self, base):
        """Test 18: load_grants with no file returns defaults."""
        from core.config import load_grants

        base.mkdir(parents=True, exist_ok=True)
        g = load_grants(base_path=base)
        assert g.version
        assert isinstance(g.granted_paths, list)
        assert isinstance(g.denied_paths, list)

    def test_default_granted_paths(self, base):
        """Test 19: default grants include ~/Documents, ~/Downloads, ~/Desktop (read) and workspace (read_write)."""
        from core.config import load_grants

        base.mkdir(parents=True, exist_ok=True)
        g = load_grants(base_path=base)
        paths_and_access = {gp.path: gp.access for gp in g.granted_paths}

        assert "~/Documents" in paths_and_access
        assert paths_and_access["~/Documents"] == "read"
        assert "~/Downloads" in paths_and_access
        assert paths_and_access["~/Downloads"] == "read"
        assert "~/Desktop" in paths_and_access
        assert paths_and_access["~/Desktop"] == "read"

        # workspace entry should be read_write
        workspace_entries = [gp for gp in g.granted_paths
                            if "workspace" in gp.path]
        assert len(workspace_entries) >= 1
        assert workspace_entries[0].access == "read_write"

    def test_default_denied_paths(self, base):
        """Test 20: default denied includes ~/.ssh, ~/.aws, ~/.gnupg, ~/.env."""
        from core.config import load_grants

        base.mkdir(parents=True, exist_ok=True)
        g = load_grants(base_path=base)
        for p in ["~/.ssh", "~/.aws", "~/.gnupg", "~/.env"]:
            assert p in g.denied_paths, f"{p} should be in denied_paths"

    def test_save_grants(self, base):
        """Test 21: save_grants writes grants.json."""
        from core.config import load_grants, save_grants

        base.mkdir(parents=True, exist_ok=True)
        g = load_grants(base_path=base)
        save_grants(g, base_path=base)
        assert (base / "grants.json").is_file()

    def test_add_grant(self, base):
        """Test 22: add_grant adds a new granted path."""
        from core.config import load_grants, save_grants, add_grant

        base.mkdir(parents=True, exist_ok=True)
        g = load_grants(base_path=base)
        save_grants(g, base_path=base)
        add_grant("/tmp/new_data", "read_write", base_path=base)
        g2 = load_grants(base_path=base)
        paths = [gp.path for gp in g2.granted_paths]
        assert "/tmp/new_data" in paths

    def test_remove_grant(self, base):
        """Test 23: remove_grant removes a granted path."""
        from core.config import load_grants, save_grants, add_grant, remove_grant

        base.mkdir(parents=True, exist_ok=True)
        g = load_grants(base_path=base)
        save_grants(g, base_path=base)
        add_grant("/tmp/removable", "read", base_path=base)
        remove_grant("/tmp/removable", base_path=base)
        g2 = load_grants(base_path=base)
        paths = [gp.path for gp in g2.granted_paths]
        assert "/tmp/removable" not in paths

    def test_is_path_granted(self, base):
        """Test 24: is_path_granted returns True for granted paths."""
        from core.config import load_grants, is_path_granted

        base.mkdir(parents=True, exist_ok=True)
        g = load_grants(base_path=base)
        home = str(Path.home())
        # ~/Documents should be granted
        assert is_path_granted(os.path.join(home, "Documents", "file.txt"), g) is True

    def test_is_path_denied(self, base):
        """Test 25: is_path_denied returns True for denied paths."""
        from core.config import load_grants, is_path_denied

        base.mkdir(parents=True, exist_ok=True)
        g = load_grants(base_path=base)
        home = str(Path.home())
        assert is_path_denied(os.path.join(home, ".ssh", "id_rsa"), g) is True

    def test_denied_takes_priority(self, base):
        """Test 26: denied paths always take priority over granted."""
        from core.config import Grants, GrantedPath, is_path_granted, is_path_denied

        home = str(Path.home())
        g = Grants(
            version="1.0",
            user="tester",
            granted_paths=[
                GrantedPath(path="~/.ssh", access="read_write", recursive=True,
                            granted_at=datetime.now()),
            ],
            denied_paths=["~/.ssh"],
            allow_external_drives=False,
            allow_network_drives=False,
        )
        target = os.path.join(home, ".ssh", "id_rsa")
        assert is_path_denied(target, g) is True
        # Even though granted, denied takes priority — so is_path_granted should return False
        assert is_path_granted(target, g) is False

    def test_get_granted_paths(self, base):
        """Test 27: get_granted_paths returns resolved path strings."""
        from core.config import load_grants, get_granted_paths

        base.mkdir(parents=True, exist_ok=True)
        g = load_grants(base_path=base)
        paths = get_granted_paths(g)
        assert isinstance(paths, list)
        assert all(isinstance(p, str) for p in paths)
        # Should be resolved (no ~)
        for p in paths:
            assert "~" not in p

    def test_get_denied_paths(self, base):
        """Test 28: get_denied_paths returns resolved path strings."""
        from core.config import load_grants, get_denied_paths

        base.mkdir(parents=True, exist_ok=True)
        g = load_grants(base_path=base)
        paths = get_denied_paths(g)
        assert isinstance(paths, list)
        assert all(isinstance(p, str) for p in paths)
        for p in paths:
            assert "~" not in p


# ===========================================================================
# IntentOSConfig — top-level bundle (tests 29-34)
# ===========================================================================

class TestIntentOSConfig:
    """Tests 29-34: IntentOSConfig bundles everything together."""

    def test_config_creates_workspace(self, base):
        """Test 29: IntentOSConfig(base_path) sets up workspace + settings + grants."""
        from core.config import IntentOSConfig

        cfg = IntentOSConfig(base_path=base)
        assert cfg.workspace is not None
        assert cfg.settings is not None
        assert cfg.grants is not None

    def test_config_settings_access(self, base):
        """Test 30: config.settings accesses settings."""
        from core.config import IntentOSConfig, Settings

        cfg = IntentOSConfig(base_path=base)
        assert cfg.settings.privacy_mode == Settings().privacy_mode

    def test_config_grants_access(self, base):
        """Test 31: config.grants accesses grants."""
        from core.config import IntentOSConfig

        cfg = IntentOSConfig(base_path=base)
        assert isinstance(cfg.grants.denied_paths, list)

    def test_config_workspace_access(self, base):
        """Test 32: config.workspace accesses workspace manager."""
        from core.config import IntentOSConfig

        cfg = IntentOSConfig(base_path=base)
        assert cfg.workspace.get_workspace_path() == base / "workspace"

    def test_config_save_all(self, base):
        """Test 33: config.save_all() persists settings and grants."""
        from core.config import IntentOSConfig

        cfg = IntentOSConfig(base_path=base)
        cfg.settings.theme = "light"
        cfg.save_all()
        assert (base / "settings.json").is_file()
        assert (base / "grants.json").is_file()

        # Reload and verify
        cfg2 = IntentOSConfig(base_path=base)
        assert cfg2.settings.theme == "light"

    def test_config_is_first_run(self, base):
        """Test 34: is_first_run is True when settings.json doesn't exist."""
        from core.config import IntentOSConfig

        cfg = IntentOSConfig(base_path=base)
        assert cfg.is_first_run is True

        cfg.save_all()
        cfg2 = IntentOSConfig(base_path=base)
        assert cfg2.is_first_run is False
