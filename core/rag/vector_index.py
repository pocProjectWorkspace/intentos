"""RAG Granular Vector Index — field-level document chunking for precision search.

Phase 4.3: Inspired by Claude-Mem's granular indexing. Stores per-field
vector documents with in-memory TF-IDF vectorization and cosine similarity.
"""

import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Maximum number of characters to vectorize (truncation guard).
MAX_CONTENT_LENGTH = 10_000


# ---------------------------------------------------------------------------
# VectorDocument
# ---------------------------------------------------------------------------

@dataclass
class VectorDocument:
    """A single field-level document chunk with optional vector embedding."""

    id: str
    source_id: str
    field_name: str
    content: str
    vector: Optional[List[float]] = None
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "field_name": self.field_name,
            "content": self.content,
            "vector": self.vector,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VectorDocument":
        return cls(
            id=d["id"],
            source_id=d["source_id"],
            field_name=d["field_name"],
            content=d["content"],
            vector=d.get("vector"),
            metadata=d.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Vectorizer (simple TF-IDF over shared vocabulary)
# ---------------------------------------------------------------------------

class Vectorizer:
    """Simple TF-IDF vectorizer with a growing vocabulary."""

    def __init__(self) -> None:
        self._vocab: Dict[str, int] = {}  # word -> index

    @property
    def vocabulary(self) -> Dict[str, int]:
        return dict(self._vocab)

    def _tokenize(self, text: str) -> List[str]:
        """Lowercase split into word tokens."""
        return text.lower().split()

    def _ensure_vocab(self, tokens: List[str]) -> None:
        """Expand vocabulary with any new tokens."""
        for tok in tokens:
            if tok not in self._vocab:
                self._vocab[tok] = len(self._vocab)

    def vectorize(self, text: str) -> List[float]:
        """Return a term-frequency vector over the shared vocabulary.

        Vocabulary grows as new words are encountered.
        Text is truncated to MAX_CONTENT_LENGTH before processing.
        """
        text = text[:MAX_CONTENT_LENGTH]
        tokens = self._tokenize(text)
        self._ensure_vocab(tokens)

        vec = [0.0] * len(self._vocab)
        for tok in tokens:
            idx = self._vocab[tok]
            vec[idx] += 1.0

        # Normalize to unit length (L2)
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def _pad(self, vec: List[float], size: int) -> List[float]:
        """Pad vector to *size* dimensions (0.0 fill)."""
        if len(vec) >= size:
            return vec
        return vec + [0.0] * (size - len(vec))

    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Cosine similarity between two vectors (possibly different lengths)."""
        if not a or not b:
            return 0.0
        dim = max(len(a), len(b))
        a = self._pad(a, dim)
        b = self._pad(b, dim)
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# VectorIndex
# ---------------------------------------------------------------------------

class VectorIndex:
    """In-memory vector index with field-level granular search."""

    def __init__(self) -> None:
        self._docs: Dict[str, VectorDocument] = {}  # doc.id -> doc
        self._vectorizer = Vectorizer()

    # -- properties ----------------------------------------------------------

    @property
    def count(self) -> int:
        return len(self._docs)

    # -- adding documents ----------------------------------------------------

    def add_document(self, doc: VectorDocument) -> None:
        """Store a document, auto-vectorizing if needed."""
        if doc.vector is None:
            doc.vector = self._vectorizer.vectorize(doc.content)
        self._docs[doc.id] = doc

    def add_from_record(self, record_id: str, fields: Dict[str, str]) -> None:
        """Split a record into per-field documents and add them.

        If record_id already exists, its previous docs are removed first.
        """
        self.remove_by_source(record_id)
        for field_name, content in fields.items():
            doc = VectorDocument(
                id=f"{record_id}::{field_name}::{uuid.uuid4().hex[:8]}",
                source_id=record_id,
                field_name=field_name,
                content=content,
            )
            self.add_document(doc)

    # -- retrieval -----------------------------------------------------------

    def get_by_source(self, source_id: str) -> List[VectorDocument]:
        """Return all field docs for a given source record."""
        return [d for d in self._docs.values() if d.source_id == source_id]

    def remove_by_source(self, source_id: str) -> None:
        """Remove all field docs for a source record."""
        to_remove = [did for did, d in self._docs.items() if d.source_id == source_id]
        for did in to_remove:
            del self._docs[did]

    # -- search --------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> List[VectorDocument]:
        """Search all documents by cosine similarity to query."""
        if not self._docs:
            return []
        query_vec = self._vectorizer.vectorize(query)
        scored: List[Tuple[float, VectorDocument]] = []
        for doc in self._docs.values():
            sim = self._vectorizer.cosine_similarity(query_vec, doc.vector or [])
            if sim > 0:
                scored.append((sim, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]

    def search_by_field(
        self, query: str, field_name: str, top_k: int = 5
    ) -> List[VectorDocument]:
        """Search restricted to documents of a specific field_name."""
        if not self._docs:
            return []
        query_vec = self._vectorizer.vectorize(query)
        scored: List[Tuple[float, VectorDocument]] = []
        for doc in self._docs.values():
            if doc.field_name != field_name:
                continue
            sim = self._vectorizer.cosine_similarity(query_vec, doc.vector or [])
            if sim > 0:
                scored.append((sim, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]

    # -- persistence ---------------------------------------------------------

    def save(self, path: str) -> None:
        """Serialize entire index (documents + vectors + vocabulary) to JSON."""
        data = {
            "documents": [d.to_dict() for d in self._docs.values()],
            "vocabulary": self._vectorizer._vocab,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path: str) -> None:
        """Deserialize from JSON, restoring documents and vectorizer state."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._docs = {}
        for d in data["documents"]:
            doc = VectorDocument.from_dict(d)
            self._docs[doc.id] = doc
        self._vectorizer._vocab = data.get("vocabulary", {})


# ---------------------------------------------------------------------------
# Granular splitting helpers
# ---------------------------------------------------------------------------

_TASK_FIELDS = ("instruction", "intent", "parameters", "result_summary")
_FILE_FIELDS = ("filename", "content_preview", "tags")


def split_task_record(record: dict) -> List[VectorDocument]:
    """Split a task record dict into per-field VectorDocuments.

    Expected keys: id, instruction, intent, parameters, result_summary.
    Missing optional fields are silently skipped.
    """
    source_id = record.get("id", uuid.uuid4().hex)
    docs: List[VectorDocument] = []
    for fname in _TASK_FIELDS:
        value = record.get(fname)
        if value is not None:
            docs.append(
                VectorDocument(
                    id=f"{source_id}::{fname}::{uuid.uuid4().hex[:8]}",
                    source_id=source_id,
                    field_name=fname,
                    content=str(value),
                )
            )
    return docs


def split_file_entry(entry: dict) -> List[VectorDocument]:
    """Split a file entry dict into per-field VectorDocuments.

    Expected keys: id, filename, content_preview, tags.
    """
    source_id = entry.get("id", uuid.uuid4().hex)
    docs: List[VectorDocument] = []
    for fname in _FILE_FIELDS:
        value = entry.get(fname)
        if value is not None:
            docs.append(
                VectorDocument(
                    id=f"{source_id}::{fname}::{uuid.uuid4().hex[:8]}",
                    source_id=source_id,
                    field_name=fname,
                    content=str(value),
                )
            )
    return docs
