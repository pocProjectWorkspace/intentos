"""Tests for core.rag.suggestions — Proactive Suggestion Engine (Phase 4.2).

Covers: Suggestion model, SuggestionEngine.generate(), related-files logic,
similar-actions logic, optimization suggestions, follow-up suggestions,
scoring/filtering, format_suggestions(), and edge cases.
"""

import os
import uuid
from datetime import datetime

import pytest

from core.rag.suggestions import Suggestion, SuggestionEngine, format_suggestions
from core.rag.file_index import FileEntry, FileIndex
from core.rag.task_index import TaskIndex, TaskRecord
from core.rag.experience import ExperienceRetriever


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file_entry(path: str, size: int = 1000, file_type: str = ".pdf",
                     tags: list = None) -> FileEntry:
    """Build a FileEntry without touching the filesystem."""
    return FileEntry(
        id=uuid.uuid4().hex,
        path=path,
        filename=os.path.basename(path),
        file_type=file_type,
        size_bytes=size,
        created=datetime(2025, 1, 1),
        modified=datetime(2025, 6, 1),
        content_preview=None,
        semantic_tags=tags or [],
    )


def _make_task_record(intent: str, files: list = None, status: str = "success",
                      raw_input: str = "test task", params: dict = None) -> TaskRecord:
    """Build a TaskRecord for testing."""
    return TaskRecord(
        raw_input=raw_input,
        resolved_intent=intent,
        agents_used=["file_agent"],
        files_affected=files or [],
        parameters_used=params or {},
        result_status=status,
        duration_ms=200,
    )


# ---------------------------------------------------------------------------
# 1. Suggestion model tests
# ---------------------------------------------------------------------------

class TestSuggestionModel:
    """Tests for the Suggestion dataclass."""

    def test_suggestion_fields(self):
        s = Suggestion(
            type="related_files",
            description="Found similar files",
            confidence=0.85,
            action_hint={"intent": "list_files", "params": {"folder": "/tmp"}},
        )
        assert s.type == "related_files"
        assert s.description == "Found similar files"
        assert s.confidence == 0.85
        assert s.action_hint["intent"] == "list_files"

    def test_suggestion_valid_types(self):
        for stype in ("related_files", "similar_action", "optimization", "follow_up"):
            s = Suggestion(type=stype, description="d", confidence=0.5, action_hint={})
            assert s.type == stype

    def test_suggestion_confidence_bounds(self):
        s = Suggestion(type="follow_up", description="d", confidence=0.0, action_hint={})
        assert s.confidence == 0.0
        s2 = Suggestion(type="follow_up", description="d", confidence=1.0, action_hint={})
        assert s2.confidence == 1.0


# ---------------------------------------------------------------------------
# 2. SuggestionEngine — related files
# ---------------------------------------------------------------------------

class TestRelatedFiles:
    """After processing files, find similar files in the same folder."""

    def test_related_files_same_folder(self):
        fi = FileIndex()
        # Task processed one invoice; index has others in the same folder
        fi.add(_make_file_entry("/docs/invoices/inv_ahmed_001.pdf", tags=["invoice"]))
        fi.add(_make_file_entry("/docs/invoices/inv_ahmed_002.pdf", tags=["invoice"]))
        fi.add(_make_file_entry("/docs/invoices/inv_ahmed_003.pdf", tags=["invoice"]))
        fi.add(_make_file_entry("/docs/invoices/inv_ahmed_004.pdf", tags=["invoice"]))

        task = _make_task_record(
            intent="process_invoice",
            files=["/docs/invoices/inv_ahmed_001.pdf"],
        )

        engine = SuggestionEngine()
        suggestions = engine.generate(task, file_index=fi)
        related = [s for s in suggestions if s.type == "related_files"]
        assert len(related) >= 1
        assert any("3" in s.description for s in related)  # 3 other files

    def test_related_files_same_type(self):
        fi = FileIndex()
        fi.add(_make_file_entry("/photos/trip/img_001.jpg", file_type=".jpg"))
        fi.add(_make_file_entry("/photos/trip/img_002.jpg", file_type=".jpg"))
        fi.add(_make_file_entry("/photos/trip/notes.txt", file_type=".txt"))

        task = _make_task_record(
            intent="rename_photo",
            files=["/photos/trip/img_001.jpg"],
        )
        engine = SuggestionEngine()
        suggestions = engine.generate(task, file_index=fi)
        related = [s for s in suggestions if s.type == "related_files"]
        assert len(related) >= 1
        # Should mention the 1 other jpg, not the txt
        assert any("1" in s.description for s in related)

    def test_no_related_when_folder_empty(self):
        fi = FileIndex()
        # Only the file that was already processed — no siblings
        fi.add(_make_file_entry("/solo/only_file.pdf"))

        task = _make_task_record(intent="read", files=["/solo/only_file.pdf"])
        engine = SuggestionEngine()
        suggestions = engine.generate(task, file_index=fi)
        related = [s for s in suggestions if s.type == "related_files"]
        assert len(related) == 0


# ---------------------------------------------------------------------------
# 3. SuggestionEngine — similar actions
# ---------------------------------------------------------------------------

class TestSimilarActions:
    """After performing an action, suggest similar items elsewhere."""

    def test_similar_actions_from_task_index(self):
        ti = TaskIndex()
        # Record many past rename tasks in another folder
        for i in range(12):
            ti.record(_make_task_record(
                intent="rename_photo",
                files=[f"/photos/vacation/img_{i:03d}.jpg"],
                raw_input="rename photo",
            ))

        task = _make_task_record(
            intent="rename_photo",
            files=["/photos/trip/img_001.jpg"],
            raw_input="rename photo",
        )

        engine = SuggestionEngine()
        suggestions = engine.generate(task, task_index=ti)
        similar = [s for s in suggestions if s.type == "similar_action"]
        assert len(similar) >= 1

    def test_no_similar_actions_different_intent(self):
        ti = TaskIndex()
        ti.record(_make_task_record(intent="delete_file", files=["/tmp/x.txt"]))

        task = _make_task_record(intent="rename_photo", files=["/photos/a.jpg"])
        engine = SuggestionEngine()
        suggestions = engine.generate(task, task_index=ti)
        similar = [s for s in suggestions if s.type == "similar_action"]
        assert len(similar) == 0


# ---------------------------------------------------------------------------
# 4. SuggestionEngine — optimizations
# ---------------------------------------------------------------------------

class TestOptimizations:
    """After listing large files, suggest duplicates / cleanup."""

    def test_duplicate_detection(self):
        fi = FileIndex()
        # 5 files with identical size (potential duplicates)
        for i in range(5):
            fi.add(_make_file_entry(
                f"/data/backup_{i}.zip",
                size=500_000_000,  # 500 MB each
                file_type=".zip",
            ))

        task = _make_task_record(
            intent="list_large_files",
            files=["/data/backup_0.zip"],
        )

        engine = SuggestionEngine()
        suggestions = engine.generate(task, file_index=fi)
        opts = [s for s in suggestions if s.type == "optimization"]
        assert len(opts) >= 1
        # Should mention size or duplicates
        assert any("duplicate" in s.description.lower() or "GB" in s.description
                    for s in opts)

    def test_no_optimization_when_no_duplicates(self):
        fi = FileIndex()
        fi.add(_make_file_entry("/data/a.zip", size=100))
        fi.add(_make_file_entry("/data/b.txt", size=200, file_type=".txt"))

        task = _make_task_record(intent="list_large_files", files=["/data/a.zip"])
        engine = SuggestionEngine()
        suggestions = engine.generate(task, file_index=fi)
        opts = [s for s in suggestions if s.type == "optimization"]
        assert len(opts) == 0


# ---------------------------------------------------------------------------
# 5. SuggestionEngine — follow-ups
# ---------------------------------------------------------------------------

class TestFollowUps:
    """After creating/editing a document, suggest next steps."""

    def test_follow_up_after_create(self):
        task = _make_task_record(
            intent="create_document",
            files=["/docs/report.md"],
        )
        engine = SuggestionEngine()
        suggestions = engine.generate(task)
        follow = [s for s in suggestions if s.type == "follow_up"]
        assert len(follow) >= 1

    def test_follow_up_after_rename(self):
        task = _make_task_record(
            intent="rename_file",
            files=["/docs/old_name.txt"],
        )
        engine = SuggestionEngine()
        suggestions = engine.generate(task)
        follow = [s for s in suggestions if s.type == "follow_up"]
        assert len(follow) >= 1

    def test_follow_up_suggests_pdf_export(self):
        task = _make_task_record(
            intent="create_document",
            files=["/docs/report.md"],
        )
        engine = SuggestionEngine()
        suggestions = engine.generate(task)
        follow = [s for s in suggestions if s.type == "follow_up"]
        assert any("pdf" in s.description.lower() or "export" in s.description.lower()
                    for s in follow)


# ---------------------------------------------------------------------------
# 6. Scoring and filtering
# ---------------------------------------------------------------------------

class TestScoringAndFiltering:
    """Suggestions ranked by confidence, filtered > 0.3, max 5."""

    def test_sorted_by_confidence(self):
        fi = FileIndex()
        for i in range(5):
            fi.add(_make_file_entry(
                f"/data/dup_{i}.zip", size=500_000_000, file_type=".zip",
            ))
        for i in range(4):
            fi.add(_make_file_entry(
                f"/data/inv_{i}.pdf", tags=["invoice"],
            ))

        task = _make_task_record(
            intent="list_large_files",
            files=["/data/dup_0.zip"],
        )
        engine = SuggestionEngine()
        suggestions = engine.generate(task, file_index=fi)
        confidences = [s.confidence for s in suggestions]
        assert confidences == sorted(confidences, reverse=True)

    def test_no_low_confidence_suggestions(self):
        engine = SuggestionEngine()
        task = _make_task_record(intent="unknown_intent", files=[])
        suggestions = engine.generate(task)
        for s in suggestions:
            assert s.confidence > 0.3

    def test_max_five_suggestions(self):
        fi = FileIndex()
        ti = TaskIndex()
        # Populate heavily to generate many suggestions
        for i in range(20):
            fi.add(_make_file_entry(
                f"/bulk/file_{i}.pdf", size=500_000_000, tags=["invoice"],
            ))
        for i in range(20):
            ti.record(_make_task_record(
                intent="create_document",
                files=[f"/bulk/file_{i}.pdf"],
                raw_input="create document",
            ))

        task = _make_task_record(
            intent="create_document",
            files=["/bulk/file_0.pdf"],
        )
        engine = SuggestionEngine()
        suggestions = engine.generate(task, file_index=fi, task_index=ti)
        assert len(suggestions) <= 5


# ---------------------------------------------------------------------------
# 7. format_suggestions()
# ---------------------------------------------------------------------------

class TestFormatSuggestions:
    """format_suggestions returns CLI-friendly text."""

    def test_format_empty(self):
        result = format_suggestions([])
        assert result == ""

    def test_format_single(self):
        s = Suggestion(
            type="follow_up",
            description="Want me to export this as PDF?",
            confidence=0.9,
            action_hint={"intent": "export_pdf"},
        )
        result = format_suggestions([s])
        assert "PDF" in result
        assert isinstance(result, str)

    def test_format_multiple(self):
        suggestions = [
            Suggestion(type="related_files", description="Found 3 similar files",
                       confidence=0.8, action_hint={}),
            Suggestion(type="follow_up", description="Export as PDF?",
                       confidence=0.7, action_hint={}),
        ]
        result = format_suggestions(suggestions)
        lines = [l for l in result.strip().split("\n") if l.strip()]
        assert len(lines) >= 2


# ---------------------------------------------------------------------------
# 8. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """No indexes, no files, failed tasks."""

    def test_no_indexes_returns_empty(self):
        task = _make_task_record(intent="list_files", files=["/tmp/a.txt"])
        engine = SuggestionEngine()
        # No file_index, no task_index, no experience — only follow-ups possible
        suggestions = engine.generate(task)
        # Should not crash; may have follow-ups but no related/similar/opt
        related = [s for s in suggestions if s.type == "related_files"]
        similar = [s for s in suggestions if s.type == "similar_action"]
        opts = [s for s in suggestions if s.type == "optimization"]
        assert len(related) == 0
        assert len(similar) == 0
        assert len(opts) == 0

    def test_task_with_no_files_only_followups(self):
        task = _make_task_record(intent="create_document", files=[])
        engine = SuggestionEngine()
        suggestions = engine.generate(task)
        for s in suggestions:
            assert s.type == "follow_up"

    def test_failed_task_no_suggestions(self):
        fi = FileIndex()
        fi.add(_make_file_entry("/docs/a.pdf"))
        task = _make_task_record(
            intent="process_invoice",
            files=["/docs/a.pdf"],
            status="failed",
        )
        engine = SuggestionEngine()
        suggestions = engine.generate(task, file_index=fi)
        assert len(suggestions) == 0

    def test_experience_integration(self):
        exp = ExperienceRetriever()
        task = _make_task_record(intent="rename_photo", files=["/a.jpg"])
        engine = SuggestionEngine()
        # Should not crash even with empty experience
        suggestions = engine.generate(task, experience=exp)
        assert isinstance(suggestions, list)
