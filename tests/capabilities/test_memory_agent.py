"""Tests for the memory_agent capability (Phase 4.5)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import shutil

import pytest

# Ensure project root is on sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from capabilities.memory_agent.agent import run


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def workspace(tmp_path):
    """Provide a fresh temporary workspace for every test."""
    # Reset the agent's internal cache so each test starts clean
    from capabilities.memory_agent import agent as _mod
    _mod._store = None
    return str(tmp_path)


def _run(action, params=None, context_extra=None, workspace=None, dry_run=False):
    ctx = {}
    if workspace:
        ctx["workspace"] = workspace
    if dry_run:
        ctx["dry_run"] = True
    if context_extra:
        ctx.update(context_extra)
    inp = {"action": action, "params": params or {}, "context": ctx}
    return run(inp)


def _ok(res):
    assert res["status"] == "success", f"Expected success, got: {res}"
    assert "action_performed" in res
    assert "result" in res
    assert "metadata" in res
    meta = res["metadata"]
    assert "files_affected" in meta
    assert "bytes_affected" in meta
    assert "duration_ms" in meta
    assert "paths_accessed" in meta


# ===================================================================
# ACP contract tests
# ===================================================================

class TestACPContract:
    """ACP contract: run() returns status/action_performed/result/metadata."""

    def test_success_shape(self, workspace):
        res = _run("remember", {"key": "color", "value": "blue", "category": "preference"}, workspace=workspace)
        _ok(res)

    def test_error_shape_unknown_action(self, workspace):
        res = _run("totally_unknown_action", workspace=workspace)
        assert res["status"] == "error"
        assert res["error"]["code"] == "UNKNOWN_ACTION"
        assert "totally_unknown_action" in res["error"]["message"]
        assert "metadata" in res

    def test_metadata_keys_always_present(self, workspace):
        res = _run("list_memories", workspace=workspace)
        _ok(res)
        for key in ("files_affected", "bytes_affected", "duration_ms", "paths_accessed"):
            assert key in res["metadata"]


# ===================================================================
# remember action
# ===================================================================

class TestRemember:

    def test_remember_basic(self, workspace):
        res = _run("remember", {"key": "lang", "value": "python", "category": "preference"}, workspace=workspace)
        _ok(res)
        assert "lang" in res["action_performed"].lower() or "remember" in res["action_performed"].lower()

    def test_remember_overwrites(self, workspace):
        _run("remember", {"key": "lang", "value": "python", "category": "preference"}, workspace=workspace)
        _run("remember", {"key": "lang", "value": "rust", "category": "preference"}, workspace=workspace)
        res = _run("recall", {"key": "lang"}, workspace=workspace)
        _ok(res)
        assert res["result"]["value"] == "rust"

    def test_remember_default_category(self, workspace):
        """If category omitted, defaults to 'fact'."""
        _run("remember", {"key": "sky", "value": "blue"}, workspace=workspace)
        res = _run("recall", {"key": "sky"}, workspace=workspace)
        _ok(res)
        assert res["result"]["category"] == "fact"

    def test_remember_validates_category(self, workspace):
        res = _run("remember", {"key": "x", "value": "y", "category": "invalid_cat"}, workspace=workspace)
        assert res["status"] == "error"

    def test_remember_requires_key_and_value(self, workspace):
        res = _run("remember", {"key": "only_key"}, workspace=workspace)
        assert res["status"] == "error"


# ===================================================================
# recall action
# ===================================================================

class TestRecall:

    def test_recall_by_key(self, workspace):
        _run("remember", {"key": "editor", "value": "vim", "category": "preference"}, workspace=workspace)
        res = _run("recall", {"key": "editor"}, workspace=workspace)
        _ok(res)
        assert res["result"]["key"] == "editor"
        assert res["result"]["value"] == "vim"

    def test_recall_missing_key(self, workspace):
        res = _run("recall", {"key": "nonexistent"}, workspace=workspace)
        assert res["status"] == "error"
        assert "NOT_FOUND" in res["error"]["code"]

    def test_recall_by_query_fuzzy(self, workspace):
        _run("remember", {"key": "preferred_date_format", "value": "YYYY-MM-DD", "category": "preference"}, workspace=workspace)
        _run("remember", {"key": "color_theme", "value": "dark", "category": "preference"}, workspace=workspace)
        res = _run("recall", {"query": "date format"}, workspace=workspace)
        _ok(res)
        # Should find the date format memory
        matches = res["result"]
        assert isinstance(matches, list)
        assert len(matches) >= 1
        keys = [m["key"] for m in matches]
        assert "preferred_date_format" in keys

    def test_recall_query_no_match(self, workspace):
        _run("remember", {"key": "editor", "value": "vim", "category": "preference"}, workspace=workspace)
        res = _run("recall", {"query": "zzzzxyzzy"}, workspace=workspace)
        _ok(res)
        assert res["result"] == []

    def test_recall_requires_key_or_query(self, workspace):
        res = _run("recall", {}, workspace=workspace)
        assert res["status"] == "error"


# ===================================================================
# forget action
# ===================================================================

class TestForget:

    def test_forget_existing(self, workspace):
        _run("remember", {"key": "tmp", "value": "data", "category": "fact"}, workspace=workspace)
        res = _run("forget", {"key": "tmp"}, workspace=workspace)
        _ok(res)
        # Verify it's gone
        res2 = _run("recall", {"key": "tmp"}, workspace=workspace)
        assert res2["status"] == "error"

    def test_forget_nonexistent_no_error(self, workspace):
        res = _run("forget", {"key": "never_stored"}, workspace=workspace)
        _ok(res)


# ===================================================================
# list_memories action
# ===================================================================

class TestListMemories:

    def test_list_all(self, workspace):
        _run("remember", {"key": "a", "value": "1", "category": "preference"}, workspace=workspace)
        _run("remember", {"key": "b", "value": "2", "category": "fact"}, workspace=workspace)
        res = _run("list_memories", workspace=workspace)
        _ok(res)
        assert isinstance(res["result"], list)
        assert len(res["result"]) == 2

    def test_list_filtered_by_category(self, workspace):
        _run("remember", {"key": "a", "value": "1", "category": "preference"}, workspace=workspace)
        _run("remember", {"key": "b", "value": "2", "category": "fact"}, workspace=workspace)
        _run("remember", {"key": "c", "value": "3", "category": "context"}, workspace=workspace)
        res = _run("list_memories", {"category": "preference"}, workspace=workspace)
        _ok(res)
        assert len(res["result"]) == 1
        assert res["result"][0]["key"] == "a"

    def test_list_empty(self, workspace):
        res = _run("list_memories", workspace=workspace)
        _ok(res)
        assert res["result"] == []


# ===================================================================
# get_context action
# ===================================================================

class TestGetContext:

    def test_get_context_returns_summary(self, workspace):
        _run("remember", {"key": "theme", "value": "dark", "category": "preference"}, workspace=workspace)
        _run("remember", {"key": "project", "value": "intentos", "category": "fact"}, workspace=workspace)
        _run("remember", {"key": "session_goal", "value": "build memory", "category": "context"}, workspace=workspace)
        res = _run("get_context", workspace=workspace)
        _ok(res)
        result = res["result"]
        assert "preferences" in result
        assert "facts" in result
        assert "context" in result
        assert len(result["preferences"]) == 1
        assert len(result["facts"]) == 1

    def test_get_context_empty(self, workspace):
        res = _run("get_context", workspace=workspace)
        _ok(res)
        assert res["result"]["preferences"] == []
        assert res["result"]["facts"] == []
        assert res["result"]["context"] == []


# ===================================================================
# clear_all action (confirmation_required pattern)
# ===================================================================

class TestClearAll:

    def test_clear_all_requires_confirmation(self, workspace):
        _run("remember", {"key": "x", "value": "y", "category": "fact"}, workspace=workspace)
        res = _run("clear_all", workspace=workspace)
        assert res["status"] == "confirmation_required"
        assert "confirm" in res.get("confirmation_message", "").lower() or "clear" in res.get("confirmation_message", "").lower()
        # Data should still be there
        check = _run("list_memories", workspace=workspace)
        assert len(check["result"]) == 1

    def test_clear_all_confirmed(self, workspace):
        _run("remember", {"key": "x", "value": "y", "category": "fact"}, workspace=workspace)
        res = _run("clear_all", {"confirmed": True}, workspace=workspace)
        _ok(res)
        check = _run("list_memories", workspace=workspace)
        assert check["result"] == []


# ===================================================================
# Persistence
# ===================================================================

class TestPersistence:

    def test_survives_restart(self, workspace):
        """Memories persist to disk and survive agent reload."""
        _run("remember", {"key": "persist_me", "value": "hello", "category": "fact"}, workspace=workspace)

        # Simulate restart by clearing the in-memory store
        from capabilities.memory_agent import agent as _mod
        _mod._store = None

        res = _run("recall", {"key": "persist_me"}, workspace=workspace)
        _ok(res)
        assert res["result"]["value"] == "hello"

    def test_memory_file_location(self, workspace):
        _run("remember", {"key": "k", "value": "v", "category": "fact"}, workspace=workspace)
        fpath = os.path.join(workspace, "memory.json")
        assert os.path.isfile(fpath)
        data = json.loads(open(fpath).read())
        assert "k" in data


# ===================================================================
# Dry run
# ===================================================================

class TestDryRun:

    @pytest.mark.parametrize("action,params", [
        ("remember", {"key": "k", "value": "v", "category": "fact"}),
        ("recall", {"key": "k"}),
        ("forget", {"key": "k"}),
        ("list_memories", {}),
        ("get_context", {}),
        ("clear_all", {"confirmed": True}),
    ])
    def test_dry_run_no_side_effects(self, workspace, action, params):
        res = _run(action, params, workspace=workspace, dry_run=True)
        assert res["status"] == "success"
        assert "would" in res["action_performed"].lower()
        # No file should be created
        fpath = os.path.join(workspace, "memory.json")
        assert not os.path.isfile(fpath)
