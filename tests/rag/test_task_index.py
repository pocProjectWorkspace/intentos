"""Tests for core.rag.task_index — RAG Task Index (Phase 3D.1)."""

import json
import os
import tempfile
from datetime import datetime, timedelta

import pytest

from core.rag.task_index import TaskIndex, TaskRecord


# ---------------------------------------------------------------------------
# TaskRecord model
# ---------------------------------------------------------------------------

class TestTaskRecord:
    """Tests 1-3: TaskRecord dataclass behaviour."""

    def test_fields_present(self):
        """Test 1: TaskRecord contains all required fields."""
        rec = TaskRecord(
            id="abc-123",
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            raw_input="rename my files",
            resolved_intent="file.rename",
            agents_used=["file_agent"],
            files_affected=["/tmp/a.txt"],
            parameters_used={"pattern": "date"},
            result_status="success",
            duration_ms=150,
            user_feedback="great",
        )
        assert rec.id == "abc-123"
        assert rec.timestamp == datetime(2026, 1, 1, 12, 0, 0)
        assert rec.raw_input == "rename my files"
        assert rec.resolved_intent == "file.rename"
        assert rec.agents_used == ["file_agent"]
        assert rec.files_affected == ["/tmp/a.txt"]
        assert rec.parameters_used == {"pattern": "date"}
        assert rec.result_status == "success"
        assert rec.duration_ms == 150
        assert rec.user_feedback == "great"

    def test_serialization_round_trip(self):
        """Test 2: to_dict and from_dict are inverse operations."""
        rec = TaskRecord(
            id="xyz",
            timestamp=datetime(2026, 3, 15, 9, 30, 0),
            raw_input="move photos",
            resolved_intent="file.move",
            agents_used=["file_agent", "photo_agent"],
            files_affected=["/tmp/photo.jpg"],
            parameters_used={"dest": "/archive"},
            result_status="success",
            duration_ms=200,
            user_feedback=None,
        )
        d = rec.to_dict()
        restored = TaskRecord.from_dict(d)
        assert restored.id == rec.id
        assert restored.timestamp == rec.timestamp
        assert restored.raw_input == rec.raw_input
        assert restored.resolved_intent == rec.resolved_intent
        assert restored.agents_used == rec.agents_used
        assert restored.files_affected == rec.files_affected
        assert restored.parameters_used == rec.parameters_used
        assert restored.result_status == rec.result_status
        assert restored.duration_ms == rec.duration_ms
        assert restored.user_feedback == rec.user_feedback

    def test_auto_generated_id_and_timestamp(self):
        """Test 3: id and timestamp are auto-generated when omitted."""
        rec = TaskRecord(
            raw_input="do something",
            resolved_intent="misc.action",
            agents_used=[],
            files_affected=[],
            parameters_used={},
            result_status="success",
            duration_ms=10,
        )
        assert rec.id is not None and len(rec.id) > 0
        assert isinstance(rec.timestamp, datetime)

        # Two auto-generated records should have different ids
        rec2 = TaskRecord(
            raw_input="another thing",
            resolved_intent="misc.other",
            agents_used=[],
            files_affected=[],
            parameters_used={},
            result_status="success",
            duration_ms=5,
        )
        assert rec.id != rec2.id


# ---------------------------------------------------------------------------
# TaskIndex — Recording
# ---------------------------------------------------------------------------

class TestTaskIndexRecording:
    """Tests 4-8: recording and retrieval."""

    def _make_record(self, **overrides):
        defaults = dict(
            raw_input="test input",
            resolved_intent="test.intent",
            agents_used=["agent_a"],
            files_affected=["/tmp/f.txt"],
            parameters_used={"key": "val"},
            result_status="success",
            duration_ms=100,
        )
        defaults.update(overrides)
        return TaskRecord(**defaults)

    def test_record_adds_task(self):
        """Test 4: record() adds a task to the index."""
        idx = TaskIndex()
        rec = self._make_record()
        idx.record(rec)
        assert idx.count == 1

    def test_record_from_execution(self):
        """Test 5: record_from_execution convenience builder."""
        idx = TaskIndex()
        rec = idx.record_from_execution(
            raw_input="rename files",
            intent="file.rename",
            agents=["file_agent"],
            files=["/tmp/a.txt"],
            params={"pattern": "date"},
            status="success",
            duration=250,
        )
        assert idx.count == 1
        assert rec.raw_input == "rename files"
        assert rec.resolved_intent == "file.rename"
        assert rec.duration_ms == 250

    def test_get_retrieves_task(self):
        """Test 6: get(task_id) retrieves a specific task."""
        idx = TaskIndex()
        rec = self._make_record()
        idx.record(rec)
        fetched = idx.get(rec.id)
        assert fetched is not None
        assert fetched.id == rec.id
        assert fetched.raw_input == rec.raw_input

    def test_get_returns_none_for_unknown(self):
        """Test 7: get returns None for unknown id."""
        idx = TaskIndex()
        assert idx.get("nonexistent-id") is None

    def test_count_property(self):
        """Test 8: count property returns total tasks."""
        idx = TaskIndex()
        assert idx.count == 0
        idx.record(self._make_record(raw_input="a"))
        assert idx.count == 1
        idx.record(self._make_record(raw_input="b"))
        assert idx.count == 2


# ---------------------------------------------------------------------------
# TaskIndex — Search
# ---------------------------------------------------------------------------

class TestTaskIndexSearch:
    """Tests 9-15: search functionality."""

    @pytest.fixture()
    def populated_index(self):
        idx = TaskIndex()
        now = datetime(2026, 3, 1, 12, 0, 0)
        tasks = [
            TaskRecord(
                id="t1", timestamp=now,
                raw_input="rename my vacation photos",
                resolved_intent="file.rename",
                agents_used=["file_agent"],
                files_affected=["/tmp/photo1.jpg"],
                parameters_used={"pattern": "date"},
                result_status="success", duration_ms=100,
            ),
            TaskRecord(
                id="t2", timestamp=now + timedelta(hours=1),
                raw_input="move documents to archive",
                resolved_intent="file.move",
                agents_used=["file_agent", "archive_agent"],
                files_affected=["/tmp/doc.pdf"],
                parameters_used={"dest": "/archive"},
                result_status="success", duration_ms=200,
            ),
            TaskRecord(
                id="t3", timestamp=now + timedelta(hours=2),
                raw_input="delete old logs",
                resolved_intent="file.delete",
                agents_used=["cleanup_agent"],
                files_affected=["/var/log/old.log"],
                parameters_used={},
                result_status="error", duration_ms=50,
            ),
            TaskRecord(
                id="t4", timestamp=now + timedelta(days=5),
                raw_input="rename report files by date",
                resolved_intent="file.rename",
                agents_used=["file_agent"],
                files_affected=["/tmp/report.csv"],
                parameters_used={"pattern": "date"},
                result_status="success", duration_ms=120,
            ),
        ]
        for t in tasks:
            idx.record(t)
        return idx

    def test_search_semantic(self, populated_index):
        """Test 9: search(query) does semantic search over raw_input + resolved_intent."""
        results = populated_index.search("rename")
        assert len(results) >= 2
        # Results with "rename" should appear
        ids = [r.id for r in results]
        assert "t1" in ids
        assert "t4" in ids

    def test_search_by_intent(self, populated_index):
        """Test 10: search_by_intent — exact or prefix match."""
        exact = populated_index.search_by_intent("file.rename")
        assert len(exact) == 2
        prefix = populated_index.search_by_intent("file.")
        assert len(prefix) >= 3  # rename, move, delete all start with file.

    def test_search_by_agent(self, populated_index):
        """Test 11: search_by_agent — all tasks using a specific agent."""
        results = populated_index.search_by_agent("file_agent")
        assert len(results) == 3  # t1, t2, t4
        results2 = populated_index.search_by_agent("cleanup_agent")
        assert len(results2) == 1

    def test_search_by_date(self, populated_index):
        """Test 12: search_by_date — date range filter."""
        after = datetime(2026, 3, 1, 13, 30, 0)
        results = populated_index.search_by_date(after=after)
        assert len(results) == 2  # t3 (14:00), t4 (day+5)

        before = datetime(2026, 3, 1, 12, 30, 0)
        results2 = populated_index.search_by_date(before=before)
        assert len(results2) == 1  # t1 (12:00)

    def test_search_by_status(self, populated_index):
        """Test 13: search_by_status — filter by success/error."""
        successes = populated_index.search_by_status("success")
        assert len(successes) == 3
        errors = populated_index.search_by_status("error")
        assert len(errors) == 1
        assert errors[0].id == "t3"

    def test_recent(self, populated_index):
        """Test 14: recent(n) — last N tasks in reverse chronological order."""
        results = populated_index.recent(2)
        assert len(results) == 2
        assert results[0].id == "t4"  # most recent
        assert results[1].id == "t3"

    def test_combined_search(self, populated_index):
        """Test 15: combined search with multiple filters."""
        results = populated_index.search(
            "rename",
            status="success",
            agent="file_agent",
        )
        ids = [r.id for r in results]
        assert "t1" in ids
        assert "t4" in ids
        assert "t3" not in ids  # error status


# ---------------------------------------------------------------------------
# TaskIndex — Replay
# ---------------------------------------------------------------------------

class TestTaskIndexReplay:
    """Tests 16-18: replay and similarity."""

    def _make_index_with_tasks(self):
        idx = TaskIndex()
        idx.record(TaskRecord(
            id="r1",
            raw_input="rename my vacation photos by date",
            resolved_intent="file.rename",
            agents_used=["file_agent"],
            files_affected=["/tmp/photo.jpg"],
            parameters_used={"pattern": "date", "prefix": "vacation"},
            result_status="success", duration_ms=100,
        ))
        idx.record(TaskRecord(
            id="r2",
            raw_input="move documents to the archive folder",
            resolved_intent="file.move",
            agents_used=["file_agent"],
            files_affected=["/tmp/doc.pdf"],
            parameters_used={"dest": "/archive"},
            result_status="success", duration_ms=200,
        ))
        idx.record(TaskRecord(
            id="r3",
            raw_input="rename all report files using date pattern",
            resolved_intent="file.rename",
            agents_used=["file_agent"],
            files_affected=["/tmp/report.csv"],
            parameters_used={"pattern": "date"},
            result_status="success", duration_ms=150,
        ))
        return idx

    def test_get_replay_data(self):
        """Test 16: get_replay_data returns raw_input, intent, params."""
        idx = self._make_index_with_tasks()
        data = idx.get_replay_data("r1")
        assert data is not None
        assert data["raw_input"] == "rename my vacation photos by date"
        assert data["resolved_intent"] == "file.rename"
        assert data["parameters_used"] == {"pattern": "date", "prefix": "vacation"}

    def test_find_similar(self):
        """Test 17: find_similar returns top-3 most similar past tasks."""
        idx = self._make_index_with_tasks()
        similar = idx.find_similar("rename photos by date")
        assert len(similar) <= 3
        # The rename tasks should rank higher than the move task
        ids = [s.id for s in similar]
        assert ids[0] in ("r1", "r3")  # rename tasks should be top

    def test_find_similar_empty(self):
        """Test 18: find_similar returns empty list if no tasks stored."""
        idx = TaskIndex()
        assert idx.find_similar("anything") == []


# ---------------------------------------------------------------------------
# TaskIndex — Pattern Detection
# ---------------------------------------------------------------------------

class TestTaskIndexPatterns:
    """Tests 19-21: pattern detection."""

    @pytest.fixture()
    def pattern_index(self):
        idx = TaskIndex()
        for i in range(5):
            idx.record(TaskRecord(
                raw_input=f"rename files {i}",
                resolved_intent="file.rename",
                agents_used=["file_agent"],
                files_affected=[f"/tmp/f{i}.txt"],
                parameters_used={"pattern": "date"},
                result_status="success", duration_ms=100,
            ))
        for i in range(3):
            idx.record(TaskRecord(
                raw_input=f"move docs {i}",
                resolved_intent="file.move",
                agents_used=["file_agent", "archive_agent"],
                files_affected=[f"/tmp/d{i}.pdf"],
                parameters_used={"dest": "/archive"},
                result_status="success", duration_ms=200,
            ))
        idx.record(TaskRecord(
            raw_input="delete temp",
            resolved_intent="file.delete",
            agents_used=["cleanup_agent"],
            files_affected=[],
            parameters_used={},
            result_status="success", duration_ms=50,
        ))
        return idx

    def test_get_frequent_intents(self, pattern_index):
        """Test 19: frequent intents sorted by count."""
        intents = pattern_index.get_frequent_intents(min_count=2)
        assert len(intents) == 2  # rename (5) and move (3), not delete (1)
        assert intents[0] == ("file.rename", 5)
        assert intents[1] == ("file.move", 3)

    def test_get_frequent_agents(self, pattern_index):
        """Test 20: frequent agents sorted by count."""
        agents = pattern_index.get_frequent_agents(min_count=2)
        agent_names = [a for a, _ in agents]
        assert "file_agent" in agent_names
        assert "archive_agent" in agent_names

    def test_get_task_patterns(self, pattern_index):
        """Test 21: repeated parameter patterns."""
        patterns = pattern_index.get_task_patterns()
        # Should detect that file.rename is commonly used with {"pattern": "date"}
        assert isinstance(patterns, dict)
        assert len(patterns) > 0
        # Check that the most frequent pattern is file.rename with pattern key
        assert "file.rename" in patterns


# ---------------------------------------------------------------------------
# TaskIndex — Persistence
# ---------------------------------------------------------------------------

class TestTaskIndexPersistence:
    """Tests 22-25: JSONL persistence."""

    def _make_record(self, raw_input="test", intent="test.intent"):
        return TaskRecord(
            raw_input=raw_input,
            resolved_intent=intent,
            agents_used=["agent_a"],
            files_affected=["/tmp/f.txt"],
            parameters_used={"k": "v"},
            result_status="success",
            duration_ms=100,
        )

    def test_save_jsonl(self, tmp_path):
        """Test 22: save serializes to JSONL format."""
        idx = TaskIndex()
        idx.record(self._make_record("task1", "intent1"))
        idx.record(self._make_record("task2", "intent2"))
        path = str(tmp_path / "tasks.jsonl")
        idx.save(path)

        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        # Each line should be valid JSON
        for line in lines:
            obj = json.loads(line)
            assert "raw_input" in obj

    def test_load_jsonl(self, tmp_path):
        """Test 23: load reads from JSONL."""
        idx = TaskIndex()
        idx.record(self._make_record("task1", "intent1"))
        idx.record(self._make_record("task2", "intent2"))
        path = str(tmp_path / "tasks.jsonl")
        idx.save(path)

        idx2 = TaskIndex()
        idx2.load(path)
        assert idx2.count == 2

    def test_append_single_record(self, tmp_path):
        """Test 24: append adds single task to existing JSONL file."""
        path = str(tmp_path / "tasks.jsonl")
        idx = TaskIndex()
        idx.record(self._make_record("task1"))
        idx.save(path)

        new_rec = self._make_record("task2")
        TaskIndex.append(path, new_rec)

        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_round_trip(self, tmp_path):
        """Test 25: save then load preserves all records."""
        idx = TaskIndex()
        for i in range(5):
            idx.record(self._make_record(f"task{i}", f"intent.{i}"))
        path = str(tmp_path / "tasks.jsonl")
        idx.save(path)

        idx2 = TaskIndex()
        idx2.load(path)
        assert idx2.count == idx.count
        for task_id in [r.id for r in idx.recent(10)]:
            original = idx.get(task_id)
            loaded = idx2.get(task_id)
            assert loaded is not None
            assert loaded.raw_input == original.raw_input
            assert loaded.resolved_intent == original.resolved_intent


# ---------------------------------------------------------------------------
# TaskIndex — Statistics
# ---------------------------------------------------------------------------

class TestTaskIndexStatistics:
    """Test 26: get_stats()."""

    def test_get_stats(self):
        """Test 26: stats returns expected fields."""
        idx = TaskIndex()
        idx.record(TaskRecord(
            raw_input="a", resolved_intent="file.rename",
            agents_used=["file_agent"], files_affected=[], parameters_used={},
            result_status="success", duration_ms=100,
        ))
        idx.record(TaskRecord(
            raw_input="b", resolved_intent="file.rename",
            agents_used=["file_agent"], files_affected=[], parameters_used={},
            result_status="success", duration_ms=200,
        ))
        idx.record(TaskRecord(
            raw_input="c", resolved_intent="file.move",
            agents_used=["file_agent", "archive_agent"], files_affected=[],
            parameters_used={}, result_status="error", duration_ms=50,
        ))
        stats = idx.get_stats()
        assert stats["total_tasks"] == 3
        assert abs(stats["success_rate"] - 2 / 3) < 0.01
        assert stats["avg_duration_ms"] == pytest.approx((100 + 200 + 50) / 3, abs=1)
        assert ("file_agent", 3) in stats["most_used_agents"]
        assert ("file.rename", 2) in stats["most_used_intents"]


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestTaskIndexEdgeCases:
    """Tests 27-28."""

    def test_empty_index_defaults(self):
        """Test 27: empty index returns sensible defaults."""
        idx = TaskIndex()
        assert idx.count == 0
        assert idx.search("anything") == []
        assert idx.recent() == []
        assert idx.find_similar("anything") == []
        stats = idx.get_stats()
        assert stats["total_tasks"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["avg_duration_ms"] == 0.0
        assert idx.get_frequent_intents() == []
        assert idx.get_frequent_agents() == []

    def test_duplicate_task_id_updates(self):
        """Test 28: duplicate task_id updates existing record."""
        idx = TaskIndex()
        rec1 = TaskRecord(
            id="dup-id",
            raw_input="original",
            resolved_intent="test.original",
            agents_used=[], files_affected=[], parameters_used={},
            result_status="success", duration_ms=100,
        )
        idx.record(rec1)
        assert idx.count == 1
        assert idx.get("dup-id").raw_input == "original"

        rec2 = TaskRecord(
            id="dup-id",
            raw_input="updated",
            resolved_intent="test.updated",
            agents_used=[], files_affected=[], parameters_used={},
            result_status="error", duration_ms=200,
        )
        idx.record(rec2)
        assert idx.count == 1  # still 1, not 2
        assert idx.get("dup-id").raw_input == "updated"
