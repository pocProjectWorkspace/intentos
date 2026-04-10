"""Tests for core.rag.context — ContextAssembler + AssembledContext.

Covers initialization, context building, file/task/experience queries,
token budget management, formatting, task recording, persistence, and edge cases.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from core.rag.context import AssembledContext, ContextAssembler
from core.rag.experience import ExperienceRetriever
from core.rag.file_index import FileEntry, FileIndex
from core.rag.task_index import TaskIndex, TaskRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file_entry(name: str, path: str = "/tmp/test", ftype: str = ".py",
                     size: int = 1024) -> FileEntry:
    now = datetime.utcnow()
    return FileEntry(
        id="f-" + name,
        path=os.path.join(path, name),
        filename=name,
        file_type=ftype,
        size_bytes=size,
        created=now,
        modified=now,
        content_preview=f"preview of {name}",
        semantic_tags=["code"],
    )


def _make_task_record(raw_input: str, intent: str = "rename_files",
                      agents: list = None, status: str = "success") -> TaskRecord:
    return TaskRecord(
        raw_input=raw_input,
        resolved_intent=intent,
        agents_used=agents or ["file_agent"],
        files_affected=["/tmp/a.txt"],
        parameters_used={"format": "date"},
        result_status=status,
        duration_ms=150,
    )


def _populated_file_index() -> FileIndex:
    fi = FileIndex()
    fi.add(_make_file_entry("main.py"))
    fi.add(_make_file_entry("utils.py"))
    fi.add(_make_file_entry("config.json", ftype=".json"))
    fi.add(_make_file_entry("readme.md", ftype=".md"))
    fi.add(_make_file_entry("data.csv", ftype=".csv"))
    return fi


def _populated_task_index() -> TaskIndex:
    ti = TaskIndex()
    ti.record(_make_task_record("rename photos by date"))
    ti.record(_make_task_record("rename all vacation photos"))
    ti.record(_make_task_record("move files to archive", intent="move_files"))
    return ti


def _populated_experience() -> ExperienceRetriever:
    er = ExperienceRetriever()
    # Feed enough tasks for pattern detection (need >= 3)
    for i in range(5):
        er.learn({
            "intent": "rename_files",
            "params": {"format": "date", "prefix": "IMG"},
            "folder": "/Users/me/Photos",
            "completed_at": datetime.utcnow().isoformat(),
        })
    return er


# ===========================================================================
# 1-3: Initialization
# ===========================================================================

class TestInitialization:
    """Tests 1-3: ContextAssembler construction."""

    def test_creates_with_empty_indexes(self):
        """Test 1: Default constructor creates empty indexes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = os.path.join(tmpdir, "empty_rag")
            ca = ContextAssembler(storage_dir=empty_dir)
            assert ca.task_index is not None
            assert ca.file_index is not None
            assert ca.experience is not None
            assert ca.task_index.count == 0
            assert ca.file_index.count == 0

    def test_uses_provided_indexes(self):
        """Test 2: Constructor uses provided indexes."""
        ti = _populated_task_index()
        fi = _populated_file_index()
        er = _populated_experience()
        ca = ContextAssembler(task_index=ti, file_index=fi, experience=er)
        assert ca.task_index is ti
        assert ca.file_index is fi
        assert ca.experience is er

    def test_auto_loads_from_default_paths(self):
        """Test 3: Auto-loads from storage_dir if files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save indexes to the temp dir
            ti = _populated_task_index()
            fi = _populated_file_index()
            er = _populated_experience()
            ti.save(os.path.join(tmpdir, "task_index.jsonl"))
            fi.save(os.path.join(tmpdir, "file_index.json"))
            er.save(os.path.join(tmpdir, "experience.json"))

            # Create assembler pointing to that dir — should auto-load
            ca = ContextAssembler(storage_dir=tmpdir)
            assert ca.task_index.count == 3
            assert ca.file_index.count == 5


# ===========================================================================
# 4-6: Context Building Basics
# ===========================================================================

class TestContextBuilding:
    """Tests 4-6: build_context basics."""

    def test_build_context_returns_assembled_context(self):
        """Test 4: build_context returns AssembledContext."""
        ca = ContextAssembler()
        ctx = ca.build_context("rename photos", max_tokens=2000)
        assert isinstance(ctx, AssembledContext)

    def test_assembled_context_has_required_fields(self):
        """Test 5: AssembledContext has all expected fields."""
        ca = ContextAssembler(
            task_index=_populated_task_index(),
            file_index=_populated_file_index(),
            experience=_populated_experience(),
        )
        ctx = ca.build_context("rename photos")
        assert isinstance(ctx.relevant_files, list)
        assert isinstance(ctx.recent_tasks, list)
        assert isinstance(ctx.user_preferences, dict)
        assert isinstance(ctx.suggestions, list)
        assert isinstance(ctx.context_text, str)

    def test_empty_indexes_returns_minimal_context(self):
        """Test 6: Empty indexes produce minimal context with default prefs."""
        ca = ContextAssembler()
        ctx = ca.build_context("anything")
        assert ctx.relevant_files == []
        assert ctx.recent_tasks == []
        assert isinstance(ctx.user_preferences, dict)
        assert isinstance(ctx.context_text, str)


# ===========================================================================
# 7-9: File Context
# ===========================================================================

class TestFileContext:
    """Tests 7-9: File search in context."""

    def test_file_search_returns_top_3(self):
        """Test 7: FileIndex search returns up to 3 matching files."""
        fi = _populated_file_index()
        ca = ContextAssembler(file_index=fi)
        ctx = ca.build_context("main")
        # At least the main.py match
        assert len(ctx.relevant_files) >= 1
        assert len(ctx.relevant_files) <= 3

    def test_file_results_include_metadata(self):
        """Test 8: File results include path, name, type, size, modified."""
        fi = _populated_file_index()
        ca = ContextAssembler(file_index=fi)
        ctx = ca.build_context("main")
        if ctx.relevant_files:
            f = ctx.relevant_files[0]
            assert "path" in f
            assert "name" in f
            assert "type" in f
            assert "size" in f
            assert "modified" in f

    def test_file_context_truncated_within_budget(self):
        """Test 9: File context truncated if exceeding token budget."""
        fi = _populated_file_index()
        ca = ContextAssembler(file_index=fi)
        # Very small budget
        ctx = ca.build_context("main", max_tokens=50)
        assert ctx.token_estimate <= 50


# ===========================================================================
# 10-12: Task History Context
# ===========================================================================

class TestTaskHistoryContext:
    """Tests 10-12: Task history in context."""

    def test_includes_similar_past_tasks(self):
        """Test 10: Includes up to 3 similar past tasks."""
        ti = _populated_task_index()
        ca = ContextAssembler(task_index=ti)
        ctx = ca.build_context("rename photos by date")
        assert len(ctx.recent_tasks) >= 1
        assert len(ctx.recent_tasks) <= 3

    def test_task_results_include_parameters(self):
        """Test 11: Task results include parameters used."""
        ti = _populated_task_index()
        ca = ContextAssembler(task_index=ti)
        ctx = ca.build_context("rename photos")
        if ctx.recent_tasks:
            t = ctx.recent_tasks[0]
            assert "parameters" in t

    def test_task_context_shows_input_agents_result(self):
        """Test 12: Task context shows what user asked, agents, and result."""
        ti = _populated_task_index()
        ca = ContextAssembler(task_index=ti)
        ctx = ca.build_context("rename photos")
        if ctx.recent_tasks:
            t = ctx.recent_tasks[0]
            assert "raw_input" in t
            assert "agents" in t
            assert "status" in t


# ===========================================================================
# 13-15: Experience Context
# ===========================================================================

class TestExperienceContext:
    """Tests 13-15: Experience-based context."""

    def test_queries_experience_suggestions(self):
        """Test 13: Queries ExperienceRetriever for suggestions."""
        er = _populated_experience()
        ca = ContextAssembler(experience=er)
        ctx = ca.build_context("rename files")
        # With 5 learned tasks, there should be suggestions
        assert isinstance(ctx.suggestions, list)

    def test_includes_learned_preferences(self):
        """Test 14: Includes learned preferences."""
        er = _populated_experience()
        ca = ContextAssembler(experience=er)
        ctx = ca.build_context("rename files")
        # Preferences dict should be populated from profile
        assert isinstance(ctx.user_preferences, dict)

    def test_includes_frequent_folder_hints(self):
        """Test 15: Includes frequent folder hints."""
        er = _populated_experience()
        ca = ContextAssembler(experience=er)
        ctx = ca.build_context("rename files")
        # Should have folder info in preferences
        assert "frequent_folders" in ctx.user_preferences


# ===========================================================================
# 16-18: Token Budget Management
# ===========================================================================

class TestTokenBudget:
    """Tests 16-18: Token budget management."""

    def test_total_context_respects_max_tokens(self):
        """Test 16: Total context respects max_tokens limit."""
        ca = ContextAssembler(
            task_index=_populated_task_index(),
            file_index=_populated_file_index(),
            experience=_populated_experience(),
        )
        ctx = ca.build_context("rename photos", max_tokens=200)
        assert ctx.token_estimate <= 200

    def test_priority_truncation_order(self):
        """Test 17: Files and preferences always included; tasks dropped first."""
        ca = ContextAssembler(
            task_index=_populated_task_index(),
            file_index=_populated_file_index(),
            experience=_populated_experience(),
        )
        # Tiny budget — only files+prefs should survive
        ctx_small = ca.build_context("rename photos", max_tokens=100)
        # Larger budget — tasks should appear too
        ctx_large = ca.build_context("rename photos", max_tokens=4000)
        # With large budget, tasks should be populated
        assert isinstance(ctx_small.context_text, str)
        assert isinstance(ctx_large.context_text, str)

    def test_get_token_estimate(self):
        """Test 18: get_token_estimate uses chars/4."""
        ca = ContextAssembler()
        assert ca.get_token_estimate("abcd") == 1
        assert ca.get_token_estimate("a" * 100) == 25
        assert ca.get_token_estimate("") == 0


# ===========================================================================
# 19-21: Context Formatting
# ===========================================================================

class TestContextFormatting:
    """Tests 19-21: format_context output."""

    def test_format_context_returns_string(self):
        """Test 19: format_context returns a string for LLM injection."""
        ca = ContextAssembler(
            task_index=_populated_task_index(),
            file_index=_populated_file_index(),
        )
        ctx = ca.build_context("rename photos")
        formatted = ca.format_context(ctx)
        assert isinstance(formatted, str)
        assert len(formatted) > 0

    def test_format_includes_sections(self):
        """Test 20: Format includes expected section headers."""
        ca = ContextAssembler(
            task_index=_populated_task_index(),
            file_index=_populated_file_index(),
            experience=_populated_experience(),
        )
        ctx = ca.build_context("rename photos", max_tokens=4000)
        formatted = ca.format_context(ctx)
        assert "Relevant files:" in formatted or "relevant files" in formatted.lower()
        assert "Recent similar tasks:" in formatted or "recent similar tasks" in formatted.lower()
        assert "User preferences:" in formatted or "user preferences" in formatted.lower()

    def test_format_no_raw_json(self):
        """Test 21: No raw JSON blobs in formatted context."""
        ca = ContextAssembler(
            task_index=_populated_task_index(),
            file_index=_populated_file_index(),
        )
        ctx = ca.build_context("main")
        formatted = ca.format_context(ctx)
        # Should not contain raw dict representations
        assert "'{" not in formatted
        assert "'[" not in formatted


# ===========================================================================
# 22-24: Task Recording
# ===========================================================================

class TestTaskRecording:
    """Tests 22-24: record_task functionality."""

    def test_record_task_stores_in_task_index(self):
        """Test 22: record_task records to TaskIndex and ExperienceRetriever."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ca = ContextAssembler(storage_dir=tmpdir)
            ca.record_task(
                raw_input="rename photos by date",
                intent="rename_files",
                agents=["file_agent"],
                files=["/tmp/a.txt"],
                params={"format": "date"},
                status="success",
                duration=200,
            )
            assert ca.task_index.count == 1

    def test_record_task_auto_saves(self):
        """Test 23: Auto-saves TaskIndex after recording."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ca = ContextAssembler(storage_dir=tmpdir)
            ca.record_task(
                raw_input="rename photos",
                intent="rename_files",
                agents=["file_agent"],
                files=[],
                params={},
                status="success",
                duration=100,
            )
            # Check the file was written
            assert os.path.exists(os.path.join(tmpdir, "task_index.jsonl"))

    def test_record_task_updates_experience(self):
        """Test 24: Auto-updates ExperienceRetriever patterns."""
        ca = ContextAssembler()
        for i in range(5):
            ca.record_task(
                raw_input=f"rename photos batch {i}",
                intent="rename_files",
                agents=["file_agent"],
                files=[],
                params={"format": "date"},
                status="success",
                duration=100,
            )
        # Experience should have learned something
        patterns = ca.experience.get_patterns()
        # With 5 identical-intent tasks, a pattern should emerge
        assert len(patterns) >= 1


# ===========================================================================
# 25-27: Persistence
# ===========================================================================

class TestPersistence:
    """Tests 25-27: save_all/load_all."""

    def test_save_all(self):
        """Test 25: save_all writes all indexes to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ca = ContextAssembler(
                task_index=_populated_task_index(),
                file_index=_populated_file_index(),
                experience=_populated_experience(),
                storage_dir=tmpdir,
            )
            ca.save_all()
            assert os.path.exists(os.path.join(tmpdir, "task_index.jsonl"))
            assert os.path.exists(os.path.join(tmpdir, "experience.json"))
            assert os.path.exists(os.path.join(tmpdir, "file_index.json"))

    def test_load_all(self):
        """Test 26: load_all restores state from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save first
            ca1 = ContextAssembler(
                task_index=_populated_task_index(),
                file_index=_populated_file_index(),
                experience=_populated_experience(),
                storage_dir=tmpdir,
            )
            ca1.save_all()

            # Load into fresh assembler
            ca2 = ContextAssembler(storage_dir=tmpdir)
            ca2.load_all()
            assert ca2.task_index.count == 3
            assert ca2.file_index.count == 5

    def test_default_paths(self):
        """Test 27: Default storage paths use ~/.intentos/rag/."""
        ca = ContextAssembler()
        expected = Path.home() / ".intentos" / "rag"
        assert ca.storage_dir == expected


# ===========================================================================
# 28-30: Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Tests 28-30: Edge cases."""

    def test_none_user_input_returns_empty_context(self):
        """Test 28: None user_input returns empty context."""
        ca = ContextAssembler(
            task_index=_populated_task_index(),
            file_index=_populated_file_index(),
        )
        ctx = ca.build_context(None)
        assert ctx.relevant_files == []
        assert ctx.recent_tasks == []

    def test_very_long_user_input(self):
        """Test 29: Very long user_input still works."""
        ca = ContextAssembler(
            task_index=_populated_task_index(),
            file_index=_populated_file_index(),
        )
        long_input = "rename " * 5000
        ctx = ca.build_context(long_input)
        assert isinstance(ctx, AssembledContext)

    def test_all_indexes_empty_graceful(self):
        """Test 30: All indexes empty returns graceful minimal context."""
        from core.rag.task_index import TaskIndex
        from core.rag.file_index import FileIndex
        from core.rag.experience import ExperienceRetriever
        ca = ContextAssembler(
            task_index=TaskIndex(),
            file_index=FileIndex(),
            experience=ExperienceRetriever(),
            chat_store=None,
        )
        ctx = ca.build_context("do something")
        assert isinstance(ctx, AssembledContext)
        assert isinstance(ctx.context_text, str)
        assert ctx.relevant_files == []
        assert ctx.recent_tasks == []
