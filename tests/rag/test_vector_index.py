"""Tests for core.rag.vector_index — Granular Vector Indexing (Phase 4.3)."""

import json
import os
import tempfile

import pytest

from core.rag.vector_index import (
    VectorDocument,
    VectorIndex,
    Vectorizer,
    split_task_record,
    split_file_entry,
)


# ---------------------------------------------------------------------------
# VectorDocument model
# ---------------------------------------------------------------------------

class TestVectorDocument:
    """Tests 1-3: VectorDocument dataclass behaviour."""

    def test_fields_present(self):
        """Test 1: VectorDocument has all required fields."""
        doc = VectorDocument(
            id="doc-1",
            source_id="rec-42",
            field_name="narrative",
            content="User asked to rename files",
            vector=[0.1, 0.2, 0.3],
            metadata={"origin": "task"},
        )
        assert doc.id == "doc-1"
        assert doc.source_id == "rec-42"
        assert doc.field_name == "narrative"
        assert doc.content == "User asked to rename files"
        assert doc.vector == [0.1, 0.2, 0.3]
        assert doc.metadata == {"origin": "task"}

    def test_defaults(self):
        """Test 2: vector defaults to None, metadata to empty dict."""
        doc = VectorDocument(
            id="doc-2",
            source_id="rec-1",
            field_name="title",
            content="Hello",
        )
        assert doc.vector is None
        assert doc.metadata == {}

    def test_serialization_round_trip(self):
        """Test 3: to_dict / from_dict are inverse operations."""
        doc = VectorDocument(
            id="doc-3",
            source_id="rec-5",
            field_name="tags",
            content="Ahmed invoice",
            vector=[1.0, 0.0, 0.5],
            metadata={"priority": "high"},
        )
        d = doc.to_dict()
        restored = VectorDocument.from_dict(d)
        assert restored.id == doc.id
        assert restored.source_id == doc.source_id
        assert restored.field_name == doc.field_name
        assert restored.content == doc.content
        assert restored.vector == doc.vector
        assert restored.metadata == doc.metadata


# ---------------------------------------------------------------------------
# Vectorizer (simple TF-IDF)
# ---------------------------------------------------------------------------

class TestVectorizer:
    """Tests 4-8: TF-IDF vectorizer behaviour."""

    def test_vectorize_returns_list_of_floats(self):
        """Test 4: vectorize produces a list of floats."""
        v = Vectorizer()
        vec = v.vectorize("hello world")
        assert isinstance(vec, list)
        assert all(isinstance(x, float) for x in vec)

    def test_vocabulary_grows(self):
        """Test 5: Vocabulary expands as new words appear."""
        v = Vectorizer()
        vec1 = v.vectorize("hello world")
        vec2 = v.vectorize("hello universe")
        # After second call, vocabulary includes "universe"
        assert len(vec2) > len(vec1) or len(vec2) == len(vec1)
        # Both vectors should share dimension for "hello"
        assert len(v.vocabulary) >= 3  # hello, world, universe

    def test_cosine_similarity_identical(self):
        """Test 6: Cosine similarity of identical texts is 1.0."""
        v = Vectorizer()
        vec_a = v.vectorize("invoice payment due")
        vec_b = v.vectorize("invoice payment due")
        sim = v.cosine_similarity(vec_a, vec_b)
        assert abs(sim - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self):
        """Test 7: Completely different texts have low similarity."""
        v = Vectorizer()
        vec_a = v.vectorize("apple banana cherry")
        vec_b = v.vectorize("xylophone zebra quantum")
        sim = v.cosine_similarity(vec_a, vec_b)
        assert sim < 0.1

    def test_cosine_similarity_empty(self):
        """Test 8: Empty vectors return 0.0 similarity."""
        v = Vectorizer()
        assert v.cosine_similarity([], []) == 0.0


# ---------------------------------------------------------------------------
# VectorIndex — basic operations
# ---------------------------------------------------------------------------

class TestVectorIndex:
    """Tests 9-16: Core index operations."""

    def test_add_document_and_count(self):
        """Test 9: Adding a document increases count."""
        idx = VectorIndex()
        assert idx.count == 0
        doc = VectorDocument(id="d1", source_id="s1", field_name="title", content="Test doc")
        idx.add_document(doc)
        assert idx.count == 1

    def test_add_document_auto_vectorizes(self):
        """Test 10: add_document assigns a vector if None."""
        idx = VectorIndex()
        doc = VectorDocument(id="d1", source_id="s1", field_name="title", content="Hello world")
        assert doc.vector is None
        idx.add_document(doc)
        assert doc.vector is not None
        assert len(doc.vector) > 0

    def test_add_from_record(self):
        """Test 11: add_from_record splits fields into separate docs."""
        idx = VectorIndex()
        idx.add_from_record("rec-1", {
            "narrative": "User requested invoice generation",
            "facts": "Amount: $500, Client: Ahmed",
            "tags": "invoice Ahmed billing",
        })
        assert idx.count == 3
        docs = idx.get_by_source("rec-1")
        field_names = {d.field_name for d in docs}
        assert field_names == {"narrative", "facts", "tags"}

    def test_search_returns_ranked_results(self):
        """Test 12: search returns results ranked by cosine similarity."""
        idx = VectorIndex()
        idx.add_from_record("rec-1", {
            "narrative": "Generate an invoice for the client",
            "tags": "invoice billing",
        })
        idx.add_from_record("rec-2", {
            "narrative": "Rename photo files by date",
            "tags": "photos rename",
        })
        results = idx.search("invoice")
        assert len(results) > 0
        # Top result should be from rec-1 (invoice-related)
        assert results[0].source_id == "rec-1"

    def test_search_by_field(self):
        """Test 13: search_by_field restricts to specific field_name."""
        idx = VectorIndex()
        idx.add_from_record("rec-1", {
            "narrative": "Generate an invoice for the client",
            "tags": "invoice Ahmed billing",
        })
        results = idx.search_by_field("invoice", "tags")
        assert len(results) > 0
        assert all(r.field_name == "tags" for r in results)

    def test_remove_by_source(self):
        """Test 14: remove_by_source removes all field docs for a source."""
        idx = VectorIndex()
        idx.add_from_record("rec-1", {"title": "A", "body": "B"})
        idx.add_from_record("rec-2", {"title": "C", "body": "D"})
        assert idx.count == 4
        idx.remove_by_source("rec-1")
        assert idx.count == 2
        assert idx.get_by_source("rec-1") == []

    def test_get_by_source(self):
        """Test 15: get_by_source returns all field docs for a record."""
        idx = VectorIndex()
        idx.add_from_record("rec-1", {"title": "Hello", "body": "World"})
        docs = idx.get_by_source("rec-1")
        assert len(docs) == 2

    def test_search_result_includes_field_name(self):
        """Test 16: Search results include which field matched."""
        idx = VectorIndex()
        idx.add_from_record("rec-1", {
            "narrative": "Send report to manager",
            "tags": "Ahmed invoice urgent",
        })
        results = idx.search("Ahmed")
        assert len(results) > 0
        # The top result should be the tags field containing Ahmed
        assert results[0].field_name == "tags"


# ---------------------------------------------------------------------------
# Granular splitting
# ---------------------------------------------------------------------------

class TestGranularSplitting:
    """Tests 17-19: split_task_record and split_file_entry."""

    def test_split_task_record(self):
        """Test 17: split_task_record produces docs for instruction, intent, parameters, result_summary."""
        record = {
            "id": "task-1",
            "instruction": "Rename all photos",
            "intent": "file.rename",
            "parameters": "pattern=date, recursive=true",
            "result_summary": "Renamed 42 files successfully",
        }
        docs = split_task_record(record)
        field_names = {d.field_name for d in docs}
        assert field_names == {"instruction", "intent", "parameters", "result_summary"}
        assert all(d.source_id == "task-1" for d in docs)

    def test_split_file_entry(self):
        """Test 18: split_file_entry produces docs for filename, content_preview, tags."""
        entry = {
            "id": "file-1",
            "filename": "invoice_ahmed_2026.pdf",
            "content_preview": "Invoice for consulting services rendered in Q1",
            "tags": "invoice Ahmed Q1 billing",
        }
        docs = split_file_entry(entry)
        field_names = {d.field_name for d in docs}
        assert field_names == {"filename", "content_preview", "tags"}
        assert all(d.source_id == "file-1" for d in docs)

    def test_split_task_record_missing_fields(self):
        """Test 19: split_task_record handles missing optional fields gracefully."""
        record = {
            "id": "task-2",
            "instruction": "Do something",
        }
        docs = split_task_record(record)
        # Should produce at least the instruction doc
        assert len(docs) >= 1
        assert any(d.field_name == "instruction" for d in docs)


# ---------------------------------------------------------------------------
# Precision search
# ---------------------------------------------------------------------------

class TestPrecisionSearch:
    """Tests 20-21: Field-level precision scenarios."""

    def test_find_tag_not_in_narrative(self):
        """Test 20: Searching 'Ahmed invoice' finds 'tags' doc containing Ahmed
        even when narrative does not mention it."""
        idx = VectorIndex()
        idx.add_from_record("rec-1", {
            "narrative": "Generate a billing document for the client",
            "tags": "Ahmed invoice billing",
        })
        idx.add_from_record("rec-2", {
            "narrative": "Organize photo albums",
            "tags": "photos vacation",
        })
        results = idx.search("Ahmed invoice")
        assert len(results) > 0
        top = results[0]
        assert top.source_id == "rec-1"
        assert "Ahmed" in top.content or "invoice" in top.content

    def test_field_level_result_identification(self):
        """Test 21: Results identify which field matched."""
        idx = VectorIndex()
        idx.add_from_record("rec-1", {
            "title": "Quarterly Report",
            "tags": "Q1 finance Ahmed",
        })
        results = idx.search_by_field("Ahmed", "tags")
        assert len(results) > 0
        assert results[0].field_name == "tags"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    """Tests 22-23: save/load JSON serialization."""

    def test_save_and_load(self):
        """Test 22: Round-trip save/load preserves documents and vectors."""
        idx = VectorIndex()
        idx.add_from_record("rec-1", {"title": "Hello", "body": "World of code"})
        idx.add_from_record("rec-2", {"title": "Goodbye", "body": "Moon landing"})

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            idx.save(path)
            idx2 = VectorIndex()
            idx2.load(path)
            assert idx2.count == idx.count
            # Vectors should be preserved
            docs_orig = idx.get_by_source("rec-1")
            docs_loaded = idx2.get_by_source("rec-1")
            assert len(docs_orig) == len(docs_loaded)
            for orig, loaded in zip(
                sorted(docs_orig, key=lambda d: d.field_name),
                sorted(docs_loaded, key=lambda d: d.field_name),
            ):
                assert orig.vector == loaded.vector
                assert orig.content == loaded.content
        finally:
            os.unlink(path)

    def test_load_preserves_search(self):
        """Test 23: After load, search still works correctly."""
        idx = VectorIndex()
        idx.add_from_record("rec-1", {"title": "Invoice for Ahmed", "body": "Payment details"})

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            idx.save(path)
            idx2 = VectorIndex()
            idx2.load(path)
            results = idx2.search("Ahmed")
            assert len(results) > 0
            assert results[0].source_id == "rec-1"
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests 24-28: Edge cases."""

    def test_empty_index_search(self):
        """Test 24: Empty index returns empty results."""
        idx = VectorIndex()
        assert idx.search("anything") == []
        assert idx.search_by_field("anything", "tags") == []

    def test_single_word_query(self):
        """Test 25: Single-word query works."""
        idx = VectorIndex()
        idx.add_from_record("rec-1", {"title": "Invoice"})
        results = idx.search("Invoice")
        assert len(results) == 1

    def test_very_long_document_truncated(self):
        """Test 26: Very long document is truncated before vectorizing."""
        idx = VectorIndex()
        long_text = "word " * 100_000  # 500K chars
        doc = VectorDocument(id="d1", source_id="s1", field_name="body", content=long_text)
        idx.add_document(doc)
        # Should not raise, and vector should exist
        assert doc.vector is not None
        assert idx.count == 1

    def test_duplicate_source_id_updates(self):
        """Test 27: Adding with same source_id via add_from_record replaces old docs."""
        idx = VectorIndex()
        idx.add_from_record("rec-1", {"title": "Old Title", "body": "Old Body"})
        assert idx.count == 2
        idx.add_from_record("rec-1", {"title": "New Title", "body": "New Body", "tags": "new"})
        assert idx.count == 3  # replaced with 3 fields
        docs = idx.get_by_source("rec-1")
        titles = [d for d in docs if d.field_name == "title"]
        assert titles[0].content == "New Title"

    def test_top_k_limits_results(self):
        """Test 28: top_k parameter limits number of results."""
        idx = VectorIndex()
        for i in range(20):
            idx.add_from_record(f"rec-{i}", {"title": f"Document about topic {i}"})
        results = idx.search("Document topic", top_k=3)
        assert len(results) <= 3
