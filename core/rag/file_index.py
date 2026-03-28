"""RAG File Index — semantic understanding layer for the user's filesystem.

Phase 2C.5: In-memory backend for indexing, searching, and classifying files.
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IndexPriority
# ---------------------------------------------------------------------------

class IndexPriority(IntEnum):
    """Priority levels for indexing filesystem paths."""
    IMMEDIATE = 1   # Desktop, Documents, Downloads
    BACKGROUND = 2  # Home subfolders (Pictures, Music, etc.)
    IDLE = 3        # Everything else
    NEVER = 4       # System dirs, .git, node_modules, .ssh


# ---------------------------------------------------------------------------
# FileEntry
# ---------------------------------------------------------------------------

@dataclass
class FileEntry:
    """Represents a single indexed file."""
    id: str
    path: str
    filename: str
    file_type: str
    size_bytes: int
    created: datetime
    modified: datetime
    content_preview: Optional[str]
    semantic_tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "path": self.path,
            "filename": self.filename,
            "file_type": self.file_type,
            "size_bytes": self.size_bytes,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat(),
            "content_preview": self.content_preview,
            "semantic_tags": list(self.semantic_tags),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FileEntry":
        """Deserialize from a dictionary."""
        return cls(
            id=d["id"],
            path=d["path"],
            filename=d["filename"],
            file_type=d["file_type"],
            size_bytes=d["size_bytes"],
            created=datetime.fromisoformat(d["created"]),
            modified=datetime.fromisoformat(d["modified"]),
            content_preview=d.get("content_preview"),
            semantic_tags=d.get("semantic_tags", []),
        )

    @classmethod
    def from_path(cls, path: str) -> "FileEntry":
        """Create a FileEntry from an actual filesystem path."""
        p = Path(path)
        st = os.stat(path)
        return cls(
            id=uuid.uuid4().hex,
            path=str(p),
            filename=p.name,
            file_type=p.suffix.lower(),
            size_bytes=st.st_size,
            created=datetime.fromtimestamp(st.st_birthtime if hasattr(st, "st_birthtime") else st.st_ctime),
            modified=datetime.fromtimestamp(st.st_mtime),
            content_preview=None,
            semantic_tags=[],
        )


# ---------------------------------------------------------------------------
# FileIndex
# ---------------------------------------------------------------------------

class FileIndex:
    """In-memory file index with search, classification, and persistence."""

    TEXT_EXTENSIONS = {
        ".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".html", ".css",
        ".xml", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".sh", ".bash",
        ".rs", ".go", ".java", ".c", ".cpp", ".h",
    }

    # Paths under ~ that get IMMEDIATE priority
    _IMMEDIATE_DIRS = {"Desktop", "Documents", "Downloads"}
    # Paths under ~ that get BACKGROUND priority
    _BACKGROUND_DIRS = {"Pictures", "Music", "Movies", "Library", "Public"}
    # Path components that trigger NEVER
    _NEVER_COMPONENTS = {".git", "node_modules", ".ssh", "__pycache__"}
    # Absolute prefixes that trigger NEVER
    _NEVER_PREFIXES = ("/etc", "/usr", "/bin", "/sbin", "/var", "/System", "/Library")

    def __init__(self) -> None:
        self._entries: Dict[str, FileEntry] = {}

    # -- properties ----------------------------------------------------------

    @property
    def count(self) -> int:
        return len(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    # -- indexing ------------------------------------------------------------

    def add(self, entry: FileEntry) -> None:
        """Add a FileEntry to the index (updates if path already present)."""
        self._entries[entry.path] = entry

    def add_from_path(self, path: str) -> None:
        """Create a FileEntry from *path* and add it to the index."""
        try:
            entry = FileEntry.from_path(path)
        except FileNotFoundError:
            logger.warning("File not found, skipping: %s", path)
            return
        except PermissionError:
            logger.warning("Permission denied, skipping: %s", path)
            return
        except OSError as exc:
            logger.warning("OS error indexing %s: %s", path, exc)
            return

        # Attach content preview for text files
        entry.content_preview = self.extract_preview(path)
        self._entries[entry.path] = entry

    def bulk_add(self, paths: List[str]) -> None:
        """Index multiple files."""
        for p in paths:
            self.add_from_path(p)

    def remove(self, path: str) -> None:
        """Remove an entry by path."""
        self._entries.pop(path, None)

    def update(self, path: str) -> None:
        """Re-index a file (removes old entry, adds fresh one)."""
        self.remove(path)
        self.add_from_path(path)

    # -- search --------------------------------------------------------------

    def search_by_name(self, query: str) -> List[FileEntry]:
        """Substring match on filename (case-insensitive)."""
        q = query.lower()
        return [e for e in self._entries.values() if q in e.filename.lower()]

    def search_by_type(self, file_type: str) -> List[FileEntry]:
        """Filter by file extension."""
        ft = file_type.lower()
        return [e for e in self._entries.values() if e.file_type == ft]

    def search_by_date(
        self,
        after: Optional[datetime] = None,
        before: Optional[datetime] = None,
    ) -> List[FileEntry]:
        """Filter by modified date range."""
        results = []
        for e in self._entries.values():
            if after and e.modified < after:
                continue
            if before and e.modified > before:
                continue
            results.append(e)
        return results

    def search_by_size(
        self,
        min_bytes: Optional[int] = None,
        max_bytes: Optional[int] = None,
    ) -> List[FileEntry]:
        """Filter by file size range."""
        results = []
        for e in self._entries.values():
            if min_bytes is not None and e.size_bytes < min_bytes:
                continue
            if max_bytes is not None and e.size_bytes > max_bytes:
                continue
            results.append(e)
        return results

    def search(self, query: str) -> List[FileEntry]:
        """Combined search: matches filename, content_preview, semantic_tags.

        Results sorted by relevance:
          name match (score 3) > tag match (score 2) > content match (score 1)
        """
        q = query.lower()
        scored: List[tuple] = []
        for e in self._entries.values():
            score = 0
            if q in e.filename.lower():
                score += 3
            if any(q in tag.lower() for tag in e.semantic_tags):
                score += 2
            if e.content_preview and q in e.content_preview.lower():
                score += 1
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored]

    # -- priority classification ---------------------------------------------

    def classify_path(self, path: str) -> IndexPriority:
        """Return the indexing priority for a filesystem path."""
        resolved = os.path.expanduser(path)

        # Check NEVER components
        parts = Path(resolved).parts
        for comp in self._NEVER_COMPONENTS:
            if comp in parts:
                return IndexPriority.NEVER

        # Check NEVER prefixes
        for prefix in self._NEVER_PREFIXES:
            if resolved.startswith(prefix):
                return IndexPriority.NEVER

        # Check home-relative dirs
        home = os.path.expanduser("~")
        if resolved.startswith(home + os.sep):
            relative = resolved[len(home) + 1:]
            top_dir = relative.split(os.sep)[0]
            if top_dir in self._IMMEDIATE_DIRS:
                return IndexPriority.IMMEDIATE
            if top_dir in self._BACKGROUND_DIRS:
                return IndexPriority.BACKGROUND

        return IndexPriority.IDLE

    # -- content extraction --------------------------------------------------

    def extract_preview(self, path: str) -> Optional[str]:
        """Return first 500 characters for text files, None for binary."""
        p = Path(path)
        if p.suffix.lower() not in self.TEXT_EXTENSIONS:
            return None
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(500)
        except (OSError, UnicodeDecodeError):
            return None

    # -- persistence ---------------------------------------------------------

    def save(self, path: str) -> None:
        """Serialize the index to a JSON file."""
        data = [e.to_dict() for e in self._entries.values()]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        """Deserialize index from a JSON file (replaces current entries)."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._entries = {}
        for d in data:
            entry = FileEntry.from_dict(d)
            self._entries[entry.path] = entry

    # -- statistics ----------------------------------------------------------

    def get_stats(self) -> dict:
        """Return index statistics."""
        by_type: Dict[str, int] = {}
        by_priority: Dict[str, int] = {}
        total_size = 0
        for e in self._entries.values():
            by_type[e.file_type] = by_type.get(e.file_type, 0) + 1
            total_size += e.size_bytes
            priority = self.classify_path(e.path).name
            by_priority[priority] = by_priority.get(priority, 0) + 1
        return {
            "total_files": len(self._entries),
            "total_size_bytes": total_size,
            "by_type": by_type,
            "by_priority": by_priority,
        }
