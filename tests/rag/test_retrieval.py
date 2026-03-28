"""Tests for Progressive Disclosure Retrieval (Phase 4.4).

3-layer token-efficient retrieval inspired by Claude-Mem.
Layer 1: Search (compact)
Layer 2: Timeline (context)
Layer 3: Get (full details)
"""

import uuid
from datetime import datetime, timedelta

import pytest

from core.rag.file_index import FileEntry, FileIndex
from core.rag.task_index import TaskIndex, TaskRecord
from core.rag.retrieval import (
    DetailedRecord,
    ProgressiveRetriever,
    SearchHit,
    TimelineView,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_file_entry(name: str, tags=None, preview=None, modified=None) -> FileEntry:
    """Helper to create a FileEntry with sensible defaults."""
    now = modified or datetime.now()
    return FileEntry(
        id=uuid.uuid4().hex,
        path=f"/tmp/test/{name}",
        filename=name,
        file_type="." + name.rsplit(".", 1)[-1] if "." in name else "",
        size_bytes=1024,
        created=now - timedelta(hours=1),
        modified=now,
        content_preview=preview or f"Content of {name}",
        semantic_tags=tags or [],
    )


def _make_task_record(raw_input: str, intent: str, ts=None) -> TaskRecord:
    """Helper to create a TaskRecord with sensible defaults."""
    return TaskRecord(
        raw_input=raw_input,
        resolved_intent=intent,
        agents_used=["test_agent"],
        files_affected=["/tmp/test/file.py"],
        parameters_used={"key": "value"},
        result_status="success",
        duration_ms=100,
        timestamp=ts or datetime.utcnow(),
    )


@pytest.fixture
def populated_indexes():
    """Return (file_index, task_index) pre-populated with test data."""
    fi = FileIndex()
    ti = TaskIndex()

    base = datetime(2025, 6, 1, 12, 0, 0)
    for i in range(10):
        fe = _make_file_entry(
            f"report_{i}.py",
            tags=["python", "report"],
            preview=f"Python report script number {i}",
            modified=base + timedelta(hours=i),
        )
        fi.add(fe)

    for i in range(10):
        tr = _make_task_record(
            f"generate report {i}",
            "generate_report",
            ts=base + timedelta(hours=i),
        )
        ti.record(tr)

    return fi, ti


@pytest.fixture
def retriever(populated_indexes):
    fi, ti = populated_indexes
    return ProgressiveRetriever(file_index=fi, task_index=ti)


@pytest.fixture
def empty_retriever():
    return ProgressiveRetriever(file_index=FileIndex(), task_index=TaskIndex())


# ---------------------------------------------------------------------------
# Layer 1 -- Search (compact)
# ---------------------------------------------------------------------------

class TestLayer1Search:
    def test_search_returns_search_hits(self, retriever):
        results = retriever.search("report")
        assert len(results) > 0
        assert all(isinstance(r, SearchHit) for r in results)

    def test_search_hit_fields(self, retriever):
        results = retriever.search("report")
        hit = results[0]
        assert isinstance(hit.id, str)
        assert hit.source_type in ("file", "task", "experience")
        assert isinstance(hit.title, str)
        assert isinstance(hit.relevance_score, float)
        assert isinstance(hit.token_estimate, int)
        assert 50 <= hit.token_estimate <= 100

    def test_search_respects_limit(self, retriever):
        results = retriever.search("report", limit=3)
        assert len(results) <= 3

    def test_search_default_limit_20(self, retriever):
        results = retriever.search("report")
        assert len(results) <= 20

    def test_search_includes_file_hits(self, retriever):
        results = retriever.search("report")
        file_hits = [r for r in results if r.source_type == "file"]
        assert len(file_hits) > 0

    def test_search_includes_task_hits(self, retriever):
        results = retriever.search("report")
        task_hits = [r for r in results if r.source_type == "task"]
        assert len(task_hits) > 0

    def test_search_sorted_by_relevance(self, retriever):
        results = retriever.search("report")
        scores = [r.relevance_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_token_estimate_range(self, retriever):
        results = retriever.search("report")
        for hit in results:
            assert 50 <= hit.token_estimate <= 100

    def test_search_empty_query_returns_empty(self, retriever):
        results = retriever.search("")
        assert results == []


# ---------------------------------------------------------------------------
# Layer 2 -- Timeline (context)
# ---------------------------------------------------------------------------

class TestLayer2Timeline:
    def test_timeline_returns_timeline_view(self, retriever):
        hits = retriever.search("report", limit=5)
        assert len(hits) > 0
        view = retriever.timeline(hits[0].id)
        assert isinstance(view, TimelineView)

    def test_timeline_has_anchor(self, retriever):
        hits = retriever.search("report", limit=5)
        view = retriever.timeline(hits[0].id)
        assert view.anchor is not None
        assert view.anchor["id"] == hits[0].id

    def test_timeline_has_before_and_after(self, retriever):
        hits = retriever.search("report", limit=5)
        view = retriever.timeline(hits[0].id)
        assert isinstance(view.items_before, list)
        assert isinstance(view.items_after, list)

    def test_timeline_respects_before_after_counts(self, retriever):
        hits = retriever.search("report", limit=5)
        view = retriever.timeline(hits[0].id, before=2, after=2)
        assert len(view.items_before) <= 2
        assert len(view.items_after) <= 2

    def test_timeline_unknown_id_returns_empty(self, retriever):
        view = retriever.timeline("nonexistent_id_xyz")
        assert view.anchor is None
        assert view.items_before == []
        assert view.items_after == []


# ---------------------------------------------------------------------------
# Layer 3 -- Get (full details)
# ---------------------------------------------------------------------------

class TestLayer3Details:
    def test_get_details_returns_detailed_records(self, retriever):
        hits = retriever.search("report", limit=3)
        ids = [h.id for h in hits]
        details = retriever.details(ids)
        assert len(details) > 0
        assert all(isinstance(d, DetailedRecord) for d in details)

    def test_detailed_record_has_full_content(self, retriever):
        hits = retriever.search("report", limit=1)
        details = retriever.details([hits[0].id])
        assert len(details) == 1
        rec = details[0]
        assert isinstance(rec.content, str)
        assert len(rec.content) > 0
        assert isinstance(rec.token_estimate, int)
        assert 500 <= rec.token_estimate <= 1000

    def test_get_details_unknown_ids_skipped(self, retriever):
        details = retriever.details(["nonexistent_abc", "nonexistent_xyz"])
        assert details == []

    def test_get_details_mixed_ids(self, retriever):
        hits = retriever.search("report", limit=2)
        ids = [hits[0].id, "nonexistent_abc"]
        details = retriever.details(ids)
        assert len(details) == 1


# ---------------------------------------------------------------------------
# ProgressiveRetriever orchestration
# ---------------------------------------------------------------------------

class TestProgressiveRetriever:
    def test_init_with_indexes(self, populated_indexes):
        fi, ti = populated_indexes
        pr = ProgressiveRetriever(file_index=fi, task_index=ti)
        assert pr is not None

    def test_estimate_tokens_search_hits(self, retriever):
        hits = retriever.search("report", limit=20)
        tokens = retriever.estimate_tokens(hits)
        assert 0 < tokens <= 2000

    def test_estimate_tokens_detailed_records(self, retriever):
        hits = retriever.search("report", limit=3)
        details = retriever.details([h.id for h in hits])
        tokens = retriever.estimate_tokens(details)
        assert tokens > 0


# ---------------------------------------------------------------------------
# Auto mode -- retrieve()
# ---------------------------------------------------------------------------

class TestAutoMode:
    def test_retrieve_returns_within_budget(self, retriever):
        result = retriever.retrieve("report", max_tokens=2000)
        assert "hits" in result
        assert "details" in result
        assert "tokens_used" in result
        assert result["tokens_used"] <= 2000

    def test_retrieve_fetches_details_for_top_hits(self, retriever):
        result = retriever.retrieve("report", max_tokens=3000)
        assert len(result["details"]) > 0

    def test_retrieve_budget_too_small(self, retriever):
        result = retriever.retrieve("report", max_tokens=10)
        # Should still return hits but no details
        assert result["details"] == []
        assert result["tokens_used"] <= 10


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

class TestCaching:
    def test_search_results_cached(self, retriever):
        r1 = retriever.search("report")
        r2 = retriever.search("report")
        assert [h.id for h in r1] == [h.id for h in r2]
        stats = retriever.get_stats()
        assert stats["cache_hits"] >= 1

    def test_different_queries_no_cache(self, retriever):
        retriever.search("report")
        retriever.search("python")
        stats = retriever.get_stats()
        assert stats["queries_served"] >= 2


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class TestStatistics:
    def test_get_stats_structure(self, retriever):
        retriever.search("report")
        stats = retriever.get_stats()
        assert "tokens_saved" in stats
        assert "queries_served" in stats
        assert "cache_hits" in stats

    def test_tokens_saved_positive_after_retrieve(self, retriever):
        retriever.retrieve("report", max_tokens=2000)
        stats = retriever.get_stats()
        assert stats["tokens_saved"] >= 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_indexes_search(self, empty_retriever):
        results = empty_retriever.search("anything")
        assert results == []

    def test_empty_indexes_timeline(self, empty_retriever):
        view = empty_retriever.timeline("some_id")
        assert view.anchor is None

    def test_empty_indexes_details(self, empty_retriever):
        details = empty_retriever.details(["some_id"])
        assert details == []

    def test_single_result(self):
        fi = FileIndex()
        fi.add(_make_file_entry("solo.py", tags=["solo"], preview="The only file"))
        ti = TaskIndex()
        pr = ProgressiveRetriever(file_index=fi, task_index=ti)
        results = pr.search("solo")
        assert len(results) == 1

    def test_empty_indexes_retrieve(self, empty_retriever):
        result = empty_retriever.retrieve("anything", max_tokens=2000)
        assert result["hits"] == []
        assert result["details"] == []
        assert result["tokens_used"] == 0
