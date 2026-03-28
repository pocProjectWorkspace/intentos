"""RAG Progressive Disclosure Retrieval — 3-layer token-efficient retrieval.

Phase 4.4: Inspired by Claude-Mem. Provides:
  Layer 1 — Search (compact): ~50-100 tokens per hit
  Layer 2 — Timeline (context): chronological neighbors around a hit
  Layer 3 — Get (full details): ~500-1000 tokens per record

The 3-layer approach yields ~10x token savings vs fetching full details
for every search result.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.rag.file_index import FileEntry, FileIndex
from core.rag.task_index import TaskIndex, TaskRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SearchHit:
    """Layer 1 result — compact summary of a matching item."""
    id: str
    source_type: str          # "file", "task", or "experience"
    title: str
    relevance_score: float
    token_estimate: int       # ~50-100 per hit


@dataclass
class TimelineView:
    """Layer 2 result — chronological context around an anchor item."""
    anchor: Optional[Dict[str, Any]]
    items_before: List[Dict[str, Any]] = field(default_factory=list)
    items_after: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DetailedRecord:
    """Layer 3 result — full content for a specific item."""
    id: str
    source_type: str
    title: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    token_estimate: int = 750  # ~500-1000 per record


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_file(query: str, entry: FileEntry) -> float:
    """Compute relevance score for a file entry against a query."""
    q = query.lower()
    score = 0.0
    if q in entry.filename.lower():
        score += 3.0
    if any(q in tag.lower() for tag in entry.semantic_tags):
        score += 2.0
    if entry.content_preview and q in entry.content_preview.lower():
        score += 1.0
    return score


def _score_task(query: str, record: TaskRecord) -> float:
    """Compute relevance score for a task record against a query."""
    q = query.lower()
    score = 0.0
    combined = f"{record.raw_input} {record.resolved_intent}".lower()
    # Word overlap
    q_words = set(q.split())
    c_words = set(combined.split())
    if q_words and c_words:
        overlap = len(q_words & c_words) / len(q_words | c_words)
        score += overlap * 3.0
    # Substring bonus
    if q in combined:
        score += 1.5
    return score


def _file_to_compact(entry: FileEntry) -> Dict[str, Any]:
    """Convert a FileEntry to a compact timeline dict."""
    return {
        "id": entry.id,
        "source_type": "file",
        "title": entry.filename,
        "modified": entry.modified.isoformat(),
    }


def _task_to_compact(record: TaskRecord) -> Dict[str, Any]:
    """Convert a TaskRecord to a compact timeline dict."""
    return {
        "id": record.id,
        "source_type": "task",
        "title": record.raw_input[:80],
        "timestamp": record.timestamp.isoformat(),
    }


def _file_to_detailed(entry: FileEntry) -> DetailedRecord:
    """Convert a FileEntry to a full DetailedRecord."""
    content_parts = [
        f"File: {entry.filename}",
        f"Path: {entry.path}",
        f"Type: {entry.file_type}",
        f"Size: {entry.size_bytes} bytes",
        f"Modified: {entry.modified.isoformat()}",
        f"Tags: {', '.join(entry.semantic_tags)}",
    ]
    if entry.content_preview:
        content_parts.append(f"Preview:\n{entry.content_preview}")
    content = "\n".join(content_parts)
    # Estimate tokens: ~4 chars per token, clamped to 500-1000
    est = max(500, min(1000, len(content) // 4))
    return DetailedRecord(
        id=entry.id,
        source_type="file",
        title=entry.filename,
        content=content,
        metadata={
            "path": entry.path,
            "file_type": entry.file_type,
            "size_bytes": entry.size_bytes,
            "tags": entry.semantic_tags,
        },
        token_estimate=est,
    )


def _task_to_detailed(record: TaskRecord) -> DetailedRecord:
    """Convert a TaskRecord to a full DetailedRecord."""
    content_parts = [
        f"Input: {record.raw_input}",
        f"Intent: {record.resolved_intent}",
        f"Agents: {', '.join(record.agents_used)}",
        f"Files: {', '.join(record.files_affected)}",
        f"Parameters: {record.parameters_used}",
        f"Status: {record.result_status}",
        f"Duration: {record.duration_ms}ms",
        f"Timestamp: {record.timestamp.isoformat()}",
    ]
    if record.user_feedback:
        content_parts.append(f"Feedback: {record.user_feedback}")
    content = "\n".join(content_parts)
    est = max(500, min(1000, len(content) // 4))
    return DetailedRecord(
        id=record.id,
        source_type="task",
        title=record.raw_input[:80],
        content=content,
        metadata={
            "intent": record.resolved_intent,
            "status": record.result_status,
            "agents": record.agents_used,
        },
        token_estimate=est,
    )


# ---------------------------------------------------------------------------
# ProgressiveRetriever
# ---------------------------------------------------------------------------

class ProgressiveRetriever:
    """Orchestrates 3-layer progressive disclosure retrieval.

    Layer 1: search()   — compact hits, ~75 tokens each
    Layer 2: timeline() — chronological context around a hit
    Layer 3: details()  — full content, ~750 tokens each

    Auto mode: retrieve() runs L1 → selects top N within budget → L3
    """

    def __init__(self, file_index: FileIndex, task_index: TaskIndex) -> None:
        self._file_index = file_index
        self._task_index = task_index

        # Internal lookup tables (populated during search)
        self._file_entries: Dict[str, FileEntry] = {}
        self._task_records: Dict[str, TaskRecord] = {}

        # Cache: query string -> list of SearchHit
        self._cache: Dict[str, List[SearchHit]] = {}

        # Statistics
        self._queries_served = 0
        self._cache_hits = 0
        self._tokens_saved = 0

        # Build internal lookup tables from indexes
        self._rebuild_lookups()

    def _rebuild_lookups(self) -> None:
        """Populate id-based lookup dicts from the underlying indexes."""
        for entry in self._file_index._entries.values():
            self._file_entries[entry.id] = entry
        for record in self._task_index._tasks.values():
            self._task_records[record.id] = record

    # -- Layer 1: Search (compact) ------------------------------------------

    def search(self, query: str, limit: int = 20) -> List[SearchHit]:
        """Layer 1 — return compact search hits sorted by relevance.

        Each hit costs ~75 tokens. 20 results ~ 1500 tokens.
        """
        if not query.strip():
            return []

        # Check cache
        cache_key = f"{query}|{limit}"
        if cache_key in self._cache:
            self._cache_hits += 1
            self._queries_served += 1
            return self._cache[cache_key]

        self._queries_served += 1
        scored: List[tuple] = []  # (score, SearchHit)

        # Search files
        for entry in self._file_index._entries.values():
            score = _score_file(query, entry)
            if score > 0:
                hit = SearchHit(
                    id=entry.id,
                    source_type="file",
                    title=entry.filename,
                    relevance_score=round(score, 4),
                    token_estimate=75,
                )
                scored.append((score, hit))

        # Search tasks
        for record in self._task_index._tasks.values():
            score = _score_task(query, record)
            if score > 0:
                hit = SearchHit(
                    id=record.id,
                    source_type="task",
                    title=record.raw_input[:80],
                    relevance_score=round(score, 4),
                    token_estimate=75,
                )
                scored.append((score, hit))

        # Sort by score descending, then limit
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [hit for _, hit in scored[:limit]]

        # Cache results
        self._cache[cache_key] = results
        return results

    # -- Layer 2: Timeline (context) ----------------------------------------

    def timeline(
        self, anchor_id: str, before: int = 5, after: int = 5
    ) -> TimelineView:
        """Layer 2 — return chronological context around an anchor item.

        Shows items created before/after the anchor in time.
        """
        # Find the anchor
        anchor_entry = self._file_entries.get(anchor_id)
        anchor_task = self._task_records.get(anchor_id)

        if anchor_entry is None and anchor_task is None:
            return TimelineView(anchor=None, items_before=[], items_after=[])

        if anchor_entry is not None:
            anchor_dict = _file_to_compact(anchor_entry)
            anchor_time = anchor_entry.modified
            source_type = "file"
        else:
            anchor_dict = _task_to_compact(anchor_task)
            anchor_time = anchor_task.timestamp
            source_type = "task"

        # Build a time-sorted list of all items (same source type)
        timed_items: List[tuple] = []  # (datetime, compact_dict)

        if source_type == "file":
            for entry in self._file_entries.values():
                if entry.id != anchor_id:
                    timed_items.append((entry.modified, _file_to_compact(entry)))
        else:
            for record in self._task_records.values():
                if record.id != anchor_id:
                    timed_items.append((record.timestamp, _task_to_compact(record)))

        timed_items.sort(key=lambda x: x[0])

        items_before = []
        items_after = []
        for ts, item in timed_items:
            if ts < anchor_time:
                items_before.append(item)
            elif ts > anchor_time:
                items_after.append(item)

        # Take the closest N before and after
        items_before = items_before[-before:] if items_before else []
        items_after = items_after[:after] if items_after else []

        return TimelineView(
            anchor=anchor_dict,
            items_before=items_before,
            items_after=items_after,
        )

    # -- Layer 3: Get (full details) ----------------------------------------

    def details(self, ids: List[str]) -> List[DetailedRecord]:
        """Layer 3 — return full detailed records for specific IDs.

        Each record costs ~500-1000 tokens. Only fetch what you need.
        """
        results: List[DetailedRecord] = []
        for item_id in ids:
            entry = self._file_entries.get(item_id)
            if entry is not None:
                results.append(_file_to_detailed(entry))
                continue
            record = self._task_records.get(item_id)
            if record is not None:
                results.append(_task_to_detailed(record))
        return results

    # -- Token estimation ---------------------------------------------------

    def estimate_tokens(self, items: list) -> int:
        """Estimate total tokens for a list of SearchHit or DetailedRecord."""
        total = 0
        for item in items:
            if hasattr(item, "token_estimate"):
                total += item.token_estimate
        return total

    # -- Auto mode ----------------------------------------------------------

    def retrieve(self, query: str, max_tokens: int = 2000) -> Dict[str, Any]:
        """Auto mode: L1 search -> pick top N within budget -> L3 details.

        Returns dict with keys: hits, details, tokens_used.
        """
        hits = self.search(query)
        if not hits:
            return {"hits": [], "details": [], "tokens_used": 0}

        search_tokens = self.estimate_tokens(hits)
        remaining_budget = max_tokens - search_tokens

        if remaining_budget <= 0:
            # Budget exhausted by search alone — trim hits to fit
            fitted_hits: List[SearchHit] = []
            used = 0
            for h in hits:
                if used + h.token_estimate > max_tokens:
                    break
                fitted_hits.append(h)
                used += h.token_estimate
            # No budget for details
            total_tokens = used
            # Track savings: full details would cost ~750 * len(fitted_hits)
            full_cost = 750 * len(fitted_hits)
            self._tokens_saved += max(0, full_cost - total_tokens)
            return {"hits": fitted_hits, "details": [], "tokens_used": total_tokens}

        # Pick top N details that fit in remaining budget
        detail_ids: List[str] = []
        budget_left = remaining_budget
        avg_detail_cost = 750  # estimated tokens per detail
        for h in hits:
            if budget_left < avg_detail_cost:
                break
            detail_ids.append(h.id)
            budget_left -= avg_detail_cost

        details = self.details(detail_ids) if detail_ids else []
        detail_tokens = self.estimate_tokens(details)
        total_tokens = search_tokens + detail_tokens

        # Track savings: full details for ALL hits would be expensive
        full_cost = 750 * len(hits)
        actual_cost = total_tokens
        self._tokens_saved += max(0, full_cost - actual_cost)

        return {
            "hits": hits,
            "details": details,
            "tokens_used": total_tokens,
        }

    # -- Statistics ---------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return retrieval statistics."""
        return {
            "tokens_saved": self._tokens_saved,
            "queries_served": self._queries_served,
            "cache_hits": self._cache_hits,
        }
