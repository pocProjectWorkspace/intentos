"""RAG Task Index — stores every completed task with full context.

Phase 3D.1: Enables replay, pattern detection, and history queries.
"""

import json
import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TaskRecord
# ---------------------------------------------------------------------------

@dataclass
class TaskRecord:
    """A single recorded task execution."""

    raw_input: str
    resolved_intent: str
    agents_used: List[str]
    files_affected: List[str]
    parameters_used: Dict
    result_status: str
    duration_ms: int
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    user_feedback: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "raw_input": self.raw_input,
            "resolved_intent": self.resolved_intent,
            "agents_used": list(self.agents_used),
            "files_affected": list(self.files_affected),
            "parameters_used": dict(self.parameters_used),
            "result_status": self.result_status,
            "duration_ms": self.duration_ms,
            "user_feedback": self.user_feedback,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskRecord":
        """Deserialize from a dictionary."""
        return cls(
            id=d["id"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            raw_input=d["raw_input"],
            resolved_intent=d["resolved_intent"],
            agents_used=d.get("agents_used", []),
            files_affected=d.get("files_affected", []),
            parameters_used=d.get("parameters_used", {}),
            result_status=d["result_status"],
            duration_ms=d["duration_ms"],
            user_feedback=d.get("user_feedback"),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set:
    """Split text into lowercase word tokens."""
    return set(text.lower().split())


def _jaccard(a: str, b: str) -> float:
    """Jaccard similarity between two strings (word-level)."""
    sa, sb = _tokenize(a), _tokenize(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# ---------------------------------------------------------------------------
# TaskIndex
# ---------------------------------------------------------------------------

class TaskIndex:
    """In-memory task index with search, replay, pattern detection, and persistence."""

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskRecord] = {}

    # -- properties ----------------------------------------------------------

    @property
    def count(self) -> int:
        return len(self._tasks)

    # -- recording -----------------------------------------------------------

    def record(self, task_record: TaskRecord) -> None:
        """Add (or update) a task in the index."""
        self._tasks[task_record.id] = task_record

    def record_from_execution(
        self,
        raw_input: str,
        intent: str,
        agents: List[str],
        files: List[str],
        params: Dict,
        status: str,
        duration: int,
    ) -> TaskRecord:
        """Convenience builder: create a TaskRecord and record it."""
        rec = TaskRecord(
            raw_input=raw_input,
            resolved_intent=intent,
            agents_used=agents,
            files_affected=files,
            parameters_used=params,
            result_status=status,
            duration_ms=duration,
        )
        self.record(rec)
        return rec

    def get(self, task_id: str) -> Optional[TaskRecord]:
        """Retrieve a specific task by id, or None."""
        return self._tasks.get(task_id)

    # -- search --------------------------------------------------------------

    def search(
        self,
        query: str,
        status: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> List[TaskRecord]:
        """Semantic search over raw_input + resolved_intent, with optional filters.

        Results ranked by word-overlap score (Jaccard similarity).
        """
        q = query.lower()
        scored: List[Tuple[float, TaskRecord]] = []
        for rec in self._tasks.values():
            if status and rec.result_status != status:
                continue
            if agent and agent not in rec.agents_used:
                continue
            combined = f"{rec.raw_input} {rec.resolved_intent}".lower()
            # Score: Jaccard on full text + bonus for substring match
            score = _jaccard(q, combined)
            if q in combined:
                score += 0.5
            if score > 0:
                scored.append((score, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [rec for _, rec in scored]

    def search_by_intent(self, intent: str) -> List[TaskRecord]:
        """Exact or prefix match on resolved_intent."""
        return [
            rec for rec in self._tasks.values()
            if rec.resolved_intent == intent or rec.resolved_intent.startswith(intent)
        ]

    def search_by_agent(self, agent_name: str) -> List[TaskRecord]:
        """All tasks that used a specific agent."""
        return [
            rec for rec in self._tasks.values()
            if agent_name in rec.agents_used
        ]

    def search_by_date(
        self,
        after: Optional[datetime] = None,
        before: Optional[datetime] = None,
    ) -> List[TaskRecord]:
        """Filter by timestamp range."""
        results = []
        for rec in self._tasks.values():
            if after and rec.timestamp < after:
                continue
            if before and rec.timestamp > before:
                continue
            results.append(rec)
        return results

    def search_by_status(self, status: str) -> List[TaskRecord]:
        """Filter by result_status."""
        return [rec for rec in self._tasks.values() if rec.result_status == status]

    def recent(self, n: int = 10) -> List[TaskRecord]:
        """Last N tasks in reverse chronological order."""
        all_tasks = sorted(self._tasks.values(), key=lambda r: r.timestamp, reverse=True)
        return all_tasks[:n]

    # -- replay --------------------------------------------------------------

    def get_replay_data(self, task_id: str) -> Optional[Dict]:
        """Return dict with raw_input, intent, params needed to replay."""
        rec = self.get(task_id)
        if rec is None:
            return None
        return {
            "raw_input": rec.raw_input,
            "resolved_intent": rec.resolved_intent,
            "parameters_used": rec.parameters_used,
        }

    def find_similar(self, raw_input: str) -> List[TaskRecord]:
        """Return top-3 most similar past tasks by input text similarity (Jaccard)."""
        if not self._tasks:
            return []
        scored: List[Tuple[float, TaskRecord]] = []
        for rec in self._tasks.values():
            score = _jaccard(raw_input, rec.raw_input)
            if score > 0:
                scored.append((score, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [rec for _, rec in scored[:3]]

    # -- pattern detection ---------------------------------------------------

    def get_frequent_intents(self, min_count: int = 2) -> List[Tuple[str, int]]:
        """Return list of (intent, count) tuples sorted by frequency desc."""
        counts = Counter(rec.resolved_intent for rec in self._tasks.values())
        result = [(intent, cnt) for intent, cnt in counts.items() if cnt >= min_count]
        result.sort(key=lambda x: x[1], reverse=True)
        return result

    def get_frequent_agents(self, min_count: int = 2) -> List[Tuple[str, int]]:
        """Return list of (agent, count) tuples sorted by frequency desc."""
        counts: Counter = Counter()
        for rec in self._tasks.values():
            for agent in rec.agents_used:
                counts[agent] += 1
        result = [(agent, cnt) for agent, cnt in counts.items() if cnt >= min_count]
        result.sort(key=lambda x: x[1], reverse=True)
        return result

    def get_task_patterns(self) -> Dict[str, List[Tuple[tuple, int]]]:
        """Return dict of repeated parameter patterns keyed by intent.

        For each intent, returns sorted list of (param_keys_tuple, count)
        where param_keys_tuple represents a set of parameter keys used together.
        """
        # Group by intent -> list of param key tuples
        intent_params: Dict[str, Counter] = {}
        for rec in self._tasks.values():
            key = tuple(sorted(rec.parameters_used.keys()))
            if not key:
                continue
            if rec.resolved_intent not in intent_params:
                intent_params[rec.resolved_intent] = Counter()
            intent_params[rec.resolved_intent][key] += 1

        result: Dict[str, List[Tuple[tuple, int]]] = {}
        for intent, counter in intent_params.items():
            patterns = [(k, c) for k, c in counter.items() if c >= 1]
            patterns.sort(key=lambda x: x[1], reverse=True)
            if patterns:
                result[intent] = patterns
        return result

    # -- persistence (JSONL) -------------------------------------------------

    def save(self, path: str) -> None:
        """Serialize to JSONL (one JSON line per task)."""
        with open(path, "w", encoding="utf-8") as f:
            for rec in self._tasks.values():
                f.write(json.dumps(rec.to_dict()) + "\n")

    def load(self, path: str) -> None:
        """Read from JSONL (replaces current entries)."""
        self._tasks = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                rec = TaskRecord.from_dict(d)
                self._tasks[rec.id] = rec

    @staticmethod
    def append(path: str, task_record: TaskRecord) -> None:
        """Append a single task to an existing JSONL file."""
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(task_record.to_dict()) + "\n")

    # -- statistics ----------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return aggregate statistics."""
        total = len(self._tasks)
        if total == 0:
            return {
                "total_tasks": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "most_used_agents": [],
                "most_used_intents": [],
            }

        successes = sum(1 for r in self._tasks.values() if r.result_status == "success")
        avg_dur = sum(r.duration_ms for r in self._tasks.values()) / total

        agent_counts = Counter()
        intent_counts = Counter()
        for rec in self._tasks.values():
            for agent in rec.agents_used:
                agent_counts[agent] += 1
            intent_counts[rec.resolved_intent] += 1

        return {
            "total_tasks": total,
            "success_rate": successes / total,
            "avg_duration_ms": avg_dur,
            "most_used_agents": agent_counts.most_common(),
            "most_used_intents": intent_counts.most_common(),
        }
