"""Tests for core.rag.file_index — RAG File Index (Phase 2C.5)."""

import json
import os
import stat
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from core.rag.file_index import FileEntry, FileIndex, IndexPriority


# ---------------------------------------------------------------------------
# FileEntry model
# ---------------------------------------------------------------------------

class TestFileEntry:
    """Tests 1-3: FileEntry dataclass."""

    def test_file_entry_fields(self, tmp_path):
        """Test 1: FileEntry contains all required fields."""
        now = datetime.now()
        entry = FileEntry(
            id="abc123",
            path="/tmp/test.txt",
            filename="test.txt",
            file_type=".txt",
            size_bytes=42,
            created=now,
            modified=now,
            content_preview="hello world",
            semantic_tags=["document", "text"],
        )
        assert entry.id == "abc123"
        assert entry.path == "/tmp/test.txt"
        assert entry.filename == "test.txt"
        assert entry.file_type == ".txt"
        assert entry.size_bytes == 42
        assert entry.created == now
        assert entry.modified == now
        assert entry.content_preview == "hello world"
        assert entry.semantic_tags == ["document", "text"]

    def test_file_entry_optional_preview_none(self):
        """Test 1b: content_preview can be None."""
        now = datetime.now()
        entry = FileEntry(
            id="x",
            path="/tmp/img.png",
            filename="img.png",
            file_type=".png",
            size_bytes=1024,
            created=now,
            modified=now,
            content_preview=None,
            semantic_tags=[],
        )
        assert entry.content_preview is None

    def test_file_entry_to_dict(self):
        """Test 2: Serialization to dict."""
        now = datetime.now()
        entry = FileEntry(
            id="abc",
            path="/tmp/test.txt",
            filename="test.txt",
            file_type=".txt",
            size_bytes=10,
            created=now,
            modified=now,
            content_preview="hi",
            semantic_tags=["tag1"],
        )
        d = entry.to_dict()
        assert isinstance(d, dict)
        assert d["id"] == "abc"
        assert d["path"] == "/tmp/test.txt"
        assert d["filename"] == "test.txt"
        assert d["file_type"] == ".txt"
        assert d["size_bytes"] == 10
        assert d["content_preview"] == "hi"
        assert d["semantic_tags"] == ["tag1"]
        # datetimes should be serializable strings
        assert isinstance(d["created"], str)
        assert isinstance(d["modified"], str)

    def test_file_entry_from_path(self, tmp_path):
        """Test 3: from_path() classmethod creates FileEntry from actual file."""
        f = tmp_path / "hello.txt"
        f.write_text("hello world")
        entry = FileEntry.from_path(str(f))
        assert entry.filename == "hello.txt"
        assert entry.file_type == ".txt"
        assert entry.size_bytes == len("hello world")
        assert entry.path == str(f)
        assert isinstance(entry.id, str) and len(entry.id) > 0
        assert isinstance(entry.created, datetime)
        assert isinstance(entry.modified, datetime)


# ---------------------------------------------------------------------------
# IndexPriority enum
# ---------------------------------------------------------------------------

class TestIndexPriority:
    """Test 4: IndexPriority enum values."""

    def test_priority_values(self):
        assert IndexPriority.IMMEDIATE == 1
        assert IndexPriority.BACKGROUND == 2
        assert IndexPriority.IDLE == 3
        assert IndexPriority.NEVER == 4

    def test_priority_ordering(self):
        assert IndexPriority.IMMEDIATE < IndexPriority.BACKGROUND
        assert IndexPriority.BACKGROUND < IndexPriority.IDLE
        assert IndexPriority.IDLE < IndexPriority.NEVER


# ---------------------------------------------------------------------------
# FileIndex — Indexing
# ---------------------------------------------------------------------------

class TestFileIndexIndexing:
    """Tests 5-10: Adding, removing, updating entries."""

    def test_add_entry(self, tmp_path):
        """Test 5: add(file_entry) adds an entry."""
        idx = FileIndex()
        f = tmp_path / "a.txt"
        f.write_text("aaa")
        entry = FileEntry.from_path(str(f))
        idx.add(entry)
        assert len(idx) == 1

    def test_add_from_path(self, tmp_path):
        """Test 6: add_from_path(path) creates FileEntry and adds it."""
        idx = FileIndex()
        f = tmp_path / "b.txt"
        f.write_text("bbb")
        idx.add_from_path(str(f))
        assert len(idx) == 1

    def test_bulk_add(self, tmp_path):
        """Test 7: bulk_add(paths) indexes multiple files."""
        idx = FileIndex()
        files = []
        for i in range(5):
            f = tmp_path / f"file{i}.txt"
            f.write_text(f"content {i}")
            files.append(str(f))
        idx.bulk_add(files)
        assert len(idx) == 5

    def test_remove(self, tmp_path):
        """Test 8: remove(path) removes entry by path."""
        idx = FileIndex()
        f = tmp_path / "rem.txt"
        f.write_text("x")
        idx.add_from_path(str(f))
        assert len(idx) == 1
        idx.remove(str(f))
        assert len(idx) == 0

    def test_update(self, tmp_path):
        """Test 9: update(path) re-indexes a file."""
        idx = FileIndex()
        f = tmp_path / "upd.txt"
        f.write_text("original")
        idx.add_from_path(str(f))
        original_size = idx._entries[str(f)].size_bytes
        f.write_text("updated with more content")
        idx.update(str(f))
        assert len(idx) == 1
        assert idx._entries[str(f)].size_bytes != original_size

    def test_len_and_count(self, tmp_path):
        """Test 10: len() and count property."""
        idx = FileIndex()
        assert len(idx) == 0
        assert idx.count == 0
        f = tmp_path / "c.txt"
        f.write_text("c")
        idx.add_from_path(str(f))
        assert len(idx) == 1
        assert idx.count == 1


# ---------------------------------------------------------------------------
# FileIndex — Search
# ---------------------------------------------------------------------------

class TestFileIndexSearch:
    """Tests 11-17: Search operations."""

    @pytest.fixture()
    def populated_index(self, tmp_path):
        """Create an index with several test files."""
        idx = FileIndex()
        # Text files
        (tmp_path / "report.txt").write_text("quarterly earnings report data")
        (tmp_path / "notes.md").write_text("meeting notes from Tuesday")
        (tmp_path / "data.csv").write_text("col1,col2\n1,2\n3,4")
        (tmp_path / "script.py").write_text("print('hello')")
        # An image-like file (binary-ish)
        (tmp_path / "photo.png").write_bytes(b"\x89PNG\r\n" + b"\x00" * 100)
        for f in tmp_path.iterdir():
            idx.add_from_path(str(f))
        return idx

    def test_search_by_name(self, populated_index):
        """Test 11: substring match on filename."""
        results = populated_index.search_by_name("report")
        assert len(results) == 1
        assert results[0].filename == "report.txt"

    def test_search_by_name_case_insensitive(self, populated_index):
        """Test 11b: name search is case-insensitive."""
        results = populated_index.search_by_name("REPORT")
        assert len(results) == 1

    def test_search_by_type(self, populated_index):
        """Test 12: filter by extension."""
        results = populated_index.search_by_type(".txt")
        assert len(results) == 1
        assert all(r.file_type == ".txt" for r in results)

    def test_search_by_date(self, tmp_path):
        """Test 13: filter by modified date."""
        idx = FileIndex()
        f = tmp_path / "recent.txt"
        f.write_text("fresh")
        idx.add_from_path(str(f))
        yesterday = datetime.now() - timedelta(days=1)
        tomorrow = datetime.now() + timedelta(days=1)
        assert len(idx.search_by_date(after=yesterday)) == 1
        assert len(idx.search_by_date(before=tomorrow)) == 1
        assert len(idx.search_by_date(after=tomorrow)) == 0

    def test_search_by_size(self, populated_index):
        """Test 14: filter by size range."""
        results = populated_index.search_by_size(min_bytes=1, max_bytes=20)
        assert all(1 <= r.size_bytes <= 20 for r in results)

    def test_search_combined(self, populated_index):
        """Test 15: search() matches filename, content_preview, semantic_tags."""
        results = populated_index.search("report")
        assert len(results) >= 1
        # The file named "report.txt" whose content has "report" should rank high
        assert results[0].filename == "report.txt"

    def test_search_relevance_order(self, tmp_path):
        """Test 16: name match > tag match > content match."""
        idx = FileIndex()
        # File whose NAME contains 'budget'
        f1 = tmp_path / "budget.txt"
        f1.write_text("some numbers")
        idx.add_from_path(str(f1))
        # Manually add semantic tag 'budget' to a different file
        f2 = tmp_path / "finance.txt"
        f2.write_text("quarterly overview")
        idx.add_from_path(str(f2))
        idx._entries[str(f2)].semantic_tags.append("budget")
        # File whose CONTENT mentions 'budget'
        f3 = tmp_path / "notes.txt"
        f3.write_text("we discussed the budget today")
        idx.add_from_path(str(f3))

        results = idx.search("budget")
        assert len(results) == 3
        # Name match should be first
        assert results[0].filename == "budget.txt"
        # Tag match second
        assert results[1].filename == "finance.txt"
        # Content match third
        assert results[2].filename == "notes.txt"

    def test_search_no_results(self, populated_index):
        """Test 17: search with no results returns empty list."""
        results = populated_index.search("zzzznonexistent")
        assert results == []


# ---------------------------------------------------------------------------
# Priority-Based Indexing
# ---------------------------------------------------------------------------

class TestPriorityClassification:
    """Tests 18-27: classify_path()."""

    def setup_method(self):
        self.idx = FileIndex()

    def test_classify_path_returns_priority(self):
        """Test 18: classify_path returns IndexPriority."""
        result = self.idx.classify_path(os.path.expanduser("~/Desktop/file.txt"))
        assert isinstance(result, IndexPriority)

    def test_desktop_immediate(self):
        """Test 19."""
        assert self.idx.classify_path(os.path.expanduser("~/Desktop/file.txt")) == IndexPriority.IMMEDIATE

    def test_documents_immediate(self):
        """Test 20."""
        assert self.idx.classify_path(os.path.expanduser("~/Documents/file.txt")) == IndexPriority.IMMEDIATE

    def test_downloads_immediate(self):
        """Test 21."""
        assert self.idx.classify_path(os.path.expanduser("~/Downloads/file.txt")) == IndexPriority.IMMEDIATE

    def test_pictures_background(self):
        """Test 22."""
        assert self.idx.classify_path(os.path.expanduser("~/Pictures/img.png")) == IndexPriority.BACKGROUND

    def test_music_background(self):
        """Test 23."""
        assert self.idx.classify_path(os.path.expanduser("~/Music/song.mp3")) == IndexPriority.BACKGROUND

    def test_etc_never(self):
        """Test 24."""
        assert self.idx.classify_path("/etc/passwd") == IndexPriority.NEVER

    def test_dotgit_never(self):
        """Test 25."""
        assert self.idx.classify_path(os.path.expanduser("~/.git/config")) == IndexPriority.NEVER

    def test_node_modules_never(self):
        """Test 26."""
        assert self.idx.classify_path(os.path.expanduser("~/project/node_modules/pkg/index.js")) == IndexPriority.NEVER

    def test_ssh_never(self):
        """Test 27."""
        assert self.idx.classify_path(os.path.expanduser("~/.ssh/id_rsa")) == IndexPriority.NEVER


# ---------------------------------------------------------------------------
# Content Extraction
# ---------------------------------------------------------------------------

class TestContentExtraction:
    """Tests 28-30: extract_preview()."""

    def setup_method(self):
        self.idx = FileIndex()

    def test_extract_preview_text_file(self, tmp_path):
        """Test 28: returns first 500 chars of text files."""
        f = tmp_path / "readme.md"
        f.write_text("# Title\n\nSome content here.")
        preview = self.idx.extract_preview(str(f))
        assert preview == "# Title\n\nSome content here."

    def test_extract_preview_binary_file(self, tmp_path):
        """Test 29: returns None for binary files."""
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x00\x00")
        preview = self.idx.extract_preview(str(f))
        assert preview is None

    def test_extract_preview_large_file(self, tmp_path):
        """Test 30: only reads first 500 chars."""
        f = tmp_path / "big.txt"
        f.write_text("x" * 10000)
        preview = self.idx.extract_preview(str(f))
        assert len(preview) == 500


# ---------------------------------------------------------------------------
# Index Persistence
# ---------------------------------------------------------------------------

class TestIndexPersistence:
    """Tests 31-33: save/load."""

    def test_save(self, tmp_path):
        """Test 31: save() serializes to JSON."""
        idx = FileIndex()
        f = tmp_path / "a.txt"
        f.write_text("aaa")
        idx.add_from_path(str(f))
        save_path = tmp_path / "index.json"
        idx.save(str(save_path))
        assert save_path.exists()
        data = json.loads(save_path.read_text())
        assert isinstance(data, list)
        assert len(data) == 1

    def test_load(self, tmp_path):
        """Test 32: load() deserializes from JSON."""
        idx = FileIndex()
        f = tmp_path / "a.txt"
        f.write_text("aaa")
        idx.add_from_path(str(f))
        save_path = tmp_path / "index.json"
        idx.save(str(save_path))
        idx2 = FileIndex()
        idx2.load(str(save_path))
        assert len(idx2) == 1

    def test_round_trip(self, tmp_path):
        """Test 33: save then load preserves all entries."""
        idx = FileIndex()
        for i in range(3):
            f = tmp_path / f"file{i}.txt"
            f.write_text(f"content {i}")
            idx.add_from_path(str(f))
        save_path = tmp_path / "index.json"
        idx.save(str(save_path))
        idx2 = FileIndex()
        idx2.load(str(save_path))
        assert len(idx2) == len(idx)
        for path, entry in idx._entries.items():
            assert path in idx2._entries
            e2 = idx2._entries[path]
            assert e2.filename == entry.filename
            assert e2.file_type == entry.file_type
            assert e2.size_bytes == entry.size_bytes
            assert e2.content_preview == entry.content_preview
            assert e2.semantic_tags == entry.semantic_tags


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class TestStatistics:
    """Test 34: get_stats()."""

    def test_get_stats(self, tmp_path):
        idx = FileIndex()
        (tmp_path / "a.txt").write_text("aaa")
        (tmp_path / "b.py").write_text("print(1)")
        (tmp_path / "c.txt").write_text("cc")
        for f in tmp_path.iterdir():
            idx.add_from_path(str(f))
        stats = idx.get_stats()
        assert stats["total_files"] == 3
        assert stats["total_size_bytes"] > 0
        assert ".txt" in stats["by_type"]
        assert stats["by_type"][".txt"] == 2
        assert stats["by_type"][".py"] == 1
        assert isinstance(stats["by_priority"], dict)


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests 35-37."""

    def test_index_nonexistent_file(self, tmp_path):
        """Test 35: non-existent file is skipped gracefully."""
        idx = FileIndex()
        idx.add_from_path(str(tmp_path / "does_not_exist.txt"))
        assert len(idx) == 0

    def test_index_no_read_permission(self, tmp_path):
        """Test 36: file with no read permission is skipped gracefully."""
        f = tmp_path / "secret.txt"
        f.write_text("secret")
        f.chmod(0o000)
        idx = FileIndex()
        idx.add_from_path(str(f))
        # Might be 0 or 1 depending on OS/user; at minimum it shouldn't crash
        # On macOS root can still read, so just verify no exception
        f.chmod(0o644)  # restore for cleanup

    def test_duplicate_path_updates(self, tmp_path):
        """Test 37: duplicate path updates existing entry, no duplicate."""
        idx = FileIndex()
        f = tmp_path / "dup.txt"
        f.write_text("version1")
        idx.add_from_path(str(f))
        assert len(idx) == 1
        f.write_text("version2 longer")
        idx.add_from_path(str(f))
        assert len(idx) == 1
        assert idx._entries[str(f)].size_bytes == len("version2 longer")
