"""RAG Experience Retriever — learns from past task executions.

Phase 3D.2: Detects patterns and infers preferences from completed tasks
to improve future routing and suggest user preferences.
Inspired by MetaGPT's Experience Retriever.
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PATTERN_THRESHOLD = 3     # Min tasks with same intent to detect a pattern
_PREFERENCE_THRESHOLD = 5  # Min tasks with same param value for preference
_SUGGESTION_CONFIDENCE_THRESHOLD = 0.5
_PREFERENCE_CONSISTENCY_THRESHOLD = 0.6  # 60%+ of instances


# ---------------------------------------------------------------------------
# LearnedPattern
# ---------------------------------------------------------------------------

@dataclass
class LearnedPattern:
    """A pattern extracted from repeated task executions."""
    pattern_type: str
    description: str
    confidence: float
    frequency: int
    last_seen: datetime
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "pattern_type": self.pattern_type,
            "description": self.description,
            "confidence": self.confidence,
            "frequency": self.frequency,
            "last_seen": self.last_seen.isoformat(),
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LearnedPattern":
        """Deserialize from a dictionary."""
        return cls(
            pattern_type=d["pattern_type"],
            description=d["description"],
            confidence=d["confidence"],
            frequency=d["frequency"],
            last_seen=datetime.fromisoformat(d["last_seen"]),
            parameters=d.get("parameters", {}),
        )


# ---------------------------------------------------------------------------
# UserPreference
# ---------------------------------------------------------------------------

@dataclass
class UserPreference:
    """A user preference inferred from repeated behaviour."""
    key: str
    value: Any
    confidence: float
    source_count: int

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "source_count": self.source_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UserPreference":
        """Deserialize from a dictionary."""
        return cls(
            key=d["key"],
            value=d["value"],
            confidence=d["confidence"],
            source_count=d["source_count"],
        )


# ---------------------------------------------------------------------------
# ExperienceRetriever
# ---------------------------------------------------------------------------

class ExperienceRetriever:
    """Learns from completed tasks to detect patterns and infer preferences."""

    def __init__(self) -> None:
        self._patterns: List[LearnedPattern] = []
        self._preferences: List[UserPreference] = []
        # intent -> list of task snapshots (params + metadata)
        self._intent_history: Dict[str, List[dict]] = {}
        # folder path -> usage count
        self._folder_history: Dict[str, int] = {}

    # -- Learning -----------------------------------------------------------

    def learn(self, task_record: dict) -> None:
        """Extract and update patterns from a completed task record."""
        intent = task_record.get("intent", "")
        params = task_record.get("params", {})
        folder = task_record.get("folder", "")
        completed_at = task_record.get("completed_at", datetime.now().isoformat())

        # Store in intent history
        snapshot = {
            "params": dict(params),
            "folder": folder,
            "completed_at": completed_at,
        }
        if intent not in self._intent_history:
            self._intent_history[intent] = []
        self._intent_history[intent].append(snapshot)

        # Track folder usage
        if folder:
            self._folder_history[folder] = self._folder_history.get(folder, 0) + 1

        # Re-detect patterns and preferences
        self._detect_patterns()
        self._infer_preferences()

    def learn_batch(self, task_records: List[dict]) -> None:
        """Process multiple task records."""
        for record in task_records:
            intent = record.get("intent", "")
            params = record.get("params", {})
            folder = record.get("folder", "")
            completed_at = record.get("completed_at", datetime.now().isoformat())

            snapshot = {
                "params": dict(params),
                "folder": folder,
                "completed_at": completed_at,
            }
            if intent not in self._intent_history:
                self._intent_history[intent] = []
            self._intent_history[intent].append(snapshot)

            if folder:
                self._folder_history[folder] = self._folder_history.get(folder, 0) + 1

        self._detect_patterns()
        self._infer_preferences()

    # -- Pattern Detection --------------------------------------------------

    def _recency_weight(self, dt_iso: str) -> float:
        """Compute recency weight: 1.0 for <7d, 0.8 for <30d, 0.5 for older."""
        try:
            dt = datetime.fromisoformat(dt_iso)
        except (ValueError, TypeError):
            return 0.5
        age = datetime.now() - dt
        if age <= timedelta(days=7):
            return 1.0
        elif age <= timedelta(days=30):
            return 0.8
        else:
            return 0.5

    def _detect_patterns(self) -> None:
        """Scan intent history and build patterns for intents with 3+ tasks."""
        new_patterns: List[LearnedPattern] = []

        for intent, snapshots in self._intent_history.items():
            if len(snapshots) < _PATTERN_THRESHOLD:
                continue

            total = len(snapshots)

            # Find the most common value for each parameter key
            param_keys = set()
            for s in snapshots:
                param_keys.update(s["params"].keys())

            # Compute consistency for each param
            preferred_params: Dict[str, Any] = {}
            max_consistency = 0.0
            for key in param_keys:
                values = [s["params"].get(key) for s in snapshots
                          if key in s["params"]]
                if not values:
                    continue
                counter = Counter(str(v) for v in values)
                most_common_str, count = counter.most_common(1)[0]
                consistency = count / total
                if consistency > max_consistency:
                    max_consistency = consistency
                # Find the actual value (not str-converted)
                for s in snapshots:
                    if key in s["params"] and str(s["params"][key]) == most_common_str:
                        preferred_params[key] = s["params"][key]
                        break

            # Find preferred folder
            folders = [s["folder"] for s in snapshots if s.get("folder")]
            preferred_folder = None
            if folders:
                folder_counter = Counter(folders)
                preferred_folder, _ = folder_counter.most_common(1)[0]

            # Compute average recency weight
            recency_weights = [self._recency_weight(s["completed_at"])
                               for s in snapshots]
            avg_recency = sum(recency_weights) / len(recency_weights) if recency_weights else 0.5

            # Confidence = consistency * recency * coverage
            # coverage: how many param keys are consistent
            if param_keys:
                consistencies = []
                for key in param_keys:
                    values = [str(s["params"].get(key)) for s in snapshots
                              if key in s["params"]]
                    if values:
                        counter = Counter(values)
                        _, count = counter.most_common(1)[0]
                        consistencies.append(count / total)
                avg_consistency = sum(consistencies) / len(consistencies) if consistencies else 0.5
            else:
                avg_consistency = 0.5

            # Frequency factor: scales from 0.5 at threshold to ~1.0 at 20+
            freq_factor = min(total / 20.0, 1.0) * 0.5 + 0.5
            confidence = avg_consistency * avg_recency * freq_factor
            confidence = min(round(confidence, 4), 1.0)

            # Build the last_seen from most recent snapshot
            last_seen_iso = max(s["completed_at"] for s in snapshots)
            try:
                last_seen = datetime.fromisoformat(last_seen_iso)
            except (ValueError, TypeError):
                last_seen = datetime.now()

            pattern_params = dict(preferred_params)
            pattern_params["intent"] = intent
            if preferred_folder:
                pattern_params["preferred_folder"] = preferred_folder

            pattern = LearnedPattern(
                pattern_type="intent_preference",
                description="Detected pattern for intent: %s" % intent,
                confidence=round(confidence, 4),
                frequency=total,
                last_seen=last_seen,
                parameters=pattern_params,
            )
            new_patterns.append(pattern)

        self._patterns = new_patterns

    def _infer_preferences(self) -> None:
        """Infer user preferences from repeated parameter values."""
        new_preferences: List[UserPreference] = []
        seen_keys = set()

        for intent, snapshots in self._intent_history.items():
            total = len(snapshots)

            # Parameter-based preferences
            param_keys = set()
            for s in snapshots:
                param_keys.update(s["params"].keys())

            for key in param_keys:
                values = [s["params"][key] for s in snapshots
                          if key in s["params"]]
                if not values:
                    continue
                counter = Counter(str(v) for v in values)
                most_common_str, count = counter.most_common(1)[0]
                consistency = count / total

                if total >= _PREFERENCE_THRESHOLD and consistency >= _PREFERENCE_CONSISTENCY_THRESHOLD:
                    # Find actual value
                    actual_value = most_common_str
                    for s in snapshots:
                        if key in s["params"] and str(s["params"][key]) == most_common_str:
                            actual_value = s["params"][key]
                            break

                    pref_key = "%s.%s" % (intent, key)
                    if pref_key not in seen_keys:
                        seen_keys.add(pref_key)
                        new_preferences.append(UserPreference(
                            key=pref_key,
                            value=actual_value,
                            confidence=round(consistency, 4),
                            source_count=count,
                        ))

            # Folder-based preferences
            folders = [s["folder"] for s in snapshots if s.get("folder")]
            if folders:
                folder_counter = Counter(folders)
                top_folder, folder_count = folder_counter.most_common(1)[0]
                folder_consistency = folder_count / total
                pref_key = "%s.preferred_folder" % intent
                if (folder_count >= _PATTERN_THRESHOLD
                        and folder_consistency >= _PREFERENCE_CONSISTENCY_THRESHOLD
                        and pref_key not in seen_keys):
                    seen_keys.add(pref_key)
                    new_preferences.append(UserPreference(
                        key=pref_key,
                        value=top_folder,
                        confidence=round(folder_consistency, 4),
                        source_count=folder_count,
                    ))

        self._preferences = new_preferences

    def get_patterns(self) -> List[LearnedPattern]:
        """Return all detected patterns."""
        return list(self._patterns)

    def get_patterns_for_intent(self, intent: str) -> List[LearnedPattern]:
        """Return patterns relevant to a specific intent."""
        return [p for p in self._patterns
                if p.parameters.get("intent") == intent]

    def get_preferences(self) -> List[UserPreference]:
        """Return all inferred preferences."""
        return list(self._preferences)

    # -- Suggestions --------------------------------------------------------

    def suggest(self, raw_input: str, intent: str) -> List[dict]:
        """Return suggestions based on experience for the given intent.

        Each suggestion is a dict with keys like:
          type, value, confidence, source
        """
        suggestions: List[dict] = []

        # Gather relevant patterns
        patterns = self.get_patterns_for_intent(intent)
        for p in patterns:
            if p.confidence < _SUGGESTION_CONFIDENCE_THRESHOLD:
                continue
            suggestion = {
                "type": "pattern",
                "description": p.description,
                "confidence": p.confidence,
                "parameters": {k: v for k, v in p.parameters.items()
                               if k != "intent"},
            }
            if suggestion["parameters"]:
                suggestions.append(suggestion)

        # Gather relevant preferences
        for pref in self._preferences:
            if not pref.key.startswith(intent + "."):
                continue
            if pref.confidence < _SUGGESTION_CONFIDENCE_THRESHOLD:
                continue
            param_name = pref.key[len(intent) + 1:]
            suggestions.append({
                "type": "preference",
                "key": param_name,
                "value": pref.value,
                "confidence": pref.confidence,
                "source_count": pref.source_count,
            })

        return suggestions

    # -- Profile Building ---------------------------------------------------

    def build_profile(self) -> dict:
        """Build a UserProfile dict with preferences, folders, and patterns.

        Mirrors the User Profile Index schema from RAG_SYSTEM.md.
        """
        # Frequent folders sorted by count descending
        frequent_folders = sorted(
            [{"path": path, "count": count}
             for path, count in self._folder_history.items()],
            key=lambda x: x["count"],
            reverse=True,
        )

        return {
            "preferences": [p.to_dict() for p in self._preferences],
            "frequent_folders": frequent_folders,
            "task_patterns": [p.to_dict() for p in self._patterns],
        }

    # -- Persistence --------------------------------------------------------

    def save(self, path: str) -> None:
        """Serialize all state to a JSON file."""
        data = {
            "patterns": [p.to_dict() for p in self._patterns],
            "preferences": [p.to_dict() for p in self._preferences],
            "intent_history": self._intent_history,
            "folder_history": self._folder_history,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        """Load state from a JSON file (replaces current state)."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._patterns = [LearnedPattern.from_dict(d)
                          for d in data.get("patterns", [])]
        self._preferences = [UserPreference.from_dict(d)
                             for d in data.get("preferences", [])]
        self._intent_history = data.get("intent_history", {})
        self._folder_history = data.get("folder_history", {})
