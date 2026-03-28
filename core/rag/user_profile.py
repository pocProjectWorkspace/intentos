"""RAG User Profile Index -- passive preference learning from task history.

Phase 4.1: Builds and maintains a user profile by observing completed tasks.
Detects preferred formats, frequent folders, recurring task patterns, and
provides per-preference confidence scores.
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_FOLDER_THRESHOLD = 3   # Min tasks writing to same folder to be "frequent"
_PATTERN_THRESHOLD = 5  # Min tasks with same intent+param to be a pattern
_PREFERENCE_THRESHOLD = 5  # Min occurrences to infer a preference

# Known preference param keys (detected automatically from task params)
_PREFERENCE_KEYS = frozenset({
    "date_format", "export_format", "image_format",
    "archive_format", "language", "timezone",
})


# ---------------------------------------------------------------------------
# UserProfile
# ---------------------------------------------------------------------------

@dataclass
class UserProfile:
    """Structured representation of learned user preferences and habits."""

    preferences: Dict[str, Any] = field(default_factory=dict)
    frequent_folders: Dict[str, str] = field(default_factory=dict)
    frequent_contacts: List[Dict[str, str]] = field(default_factory=list)
    task_patterns: List[Dict[str, Any]] = field(default_factory=list)
    avoided_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "preferences": dict(self.preferences),
            "frequent_folders": dict(self.frequent_folders),
            "frequent_contacts": list(self.frequent_contacts),
            "task_patterns": list(self.task_patterns),
            "avoided_actions": list(self.avoided_actions),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UserProfile":
        """Deserialize from a dictionary."""
        return cls(
            preferences=d.get("preferences", {}),
            frequent_folders=d.get("frequent_folders", {}),
            frequent_contacts=d.get("frequent_contacts", []),
            task_patterns=d.get("task_patterns", []),
            avoided_actions=d.get("avoided_actions", []),
        )


# ---------------------------------------------------------------------------
# ProfileManager
# ---------------------------------------------------------------------------

class ProfileManager:
    """Learns a UserProfile from observed task records.

    Call ``learn_from_task(record)`` after each completed task.  The manager
    accumulates statistics and rebuilds the profile on every query.
    """

    def __init__(self) -> None:
        # Raw accumulators
        self._folder_counts: Counter = Counter()          # path -> count
        self._intent_counts: Counter = Counter()          # intent -> count
        # intent -> list of param dicts
        self._intent_params: Dict[str, List[dict]] = {}
        # preference key -> list of observed values
        self._pref_observations: Dict[str, List[Any]] = {}
        self._total_tasks: int = 0

    # -- Learning -----------------------------------------------------------

    def learn_from_task(self, task_record: dict) -> None:
        """Ingest a completed task record and update internal statistics."""
        intent = task_record.get("intent", "")
        params = task_record.get("params", {})
        folder = task_record.get("folder", "")
        completed_at = task_record.get("completed_at", "")

        self._total_tasks += 1

        # Track folder usage
        if folder:
            self._folder_counts[folder] += 1

        # Track intent + params
        if intent:
            self._intent_counts[intent] += 1
            self._intent_params.setdefault(intent, []).append({
                "params": dict(params),
                "completed_at": completed_at,
            })

        # Track known preference keys
        for key in _PREFERENCE_KEYS:
            if key in params:
                self._pref_observations.setdefault(key, []).append(params[key])

    # -- Profile construction -----------------------------------------------

    def get_profile(self) -> UserProfile:
        """Build and return the current UserProfile from accumulated data."""
        return UserProfile(
            preferences=self._build_preferences(),
            frequent_folders=self._build_frequent_folders(),
            frequent_contacts=[],  # populated by future phases
            task_patterns=self._build_task_patterns(),
            avoided_actions=[],    # populated by future phases
        )

    # -- Queries ------------------------------------------------------------

    def get_preference(self, key: str) -> Optional[Any]:
        """Return the top preference value for *key*, or None."""
        observations = self._pref_observations.get(key, [])
        if not observations:
            return None
        counter = Counter(str(v) for v in observations)
        top_str, count = counter.most_common(1)[0]
        if count < _PREFERENCE_THRESHOLD:
            return None
        # Return the original (non-stringified) value
        for v in observations:
            if str(v) == top_str:
                return v
        return None  # pragma: no cover

    def confidence(self, key: str) -> Optional[float]:
        """Return confidence score (0..1) for a preference key.

        Confidence = frequency_of_top_value / total_observations.
        Returns None if no observations exist.
        """
        observations = self._pref_observations.get(key, [])
        if not observations:
            return None
        counter = Counter(str(v) for v in observations)
        _, top_count = counter.most_common(1)[0]
        return top_count / len(observations)

    def suggest_for_intent(self, intent: str) -> Dict[str, Any]:
        """Return a dict of suggested preferences/params for *intent*."""
        suggestions: Dict[str, Any] = {}
        snapshots = self._intent_params.get(intent, [])
        if not snapshots:
            return suggestions

        # Aggregate param values across all snapshots for this intent
        param_values: Dict[str, list] = {}
        for snap in snapshots:
            for k, v in snap["params"].items():
                param_values.setdefault(k, []).append(v)

        for k, values in param_values.items():
            counter = Counter(str(v) for v in values)
            top_str, count = counter.most_common(1)[0]
            if count >= 2:  # at least seen twice
                # Recover original value
                for v in values:
                    if str(v) == top_str:
                        suggestions[k] = v
                        break

        # Suggest frequent folder for this intent
        folders = [s["params"].get("folder") or "" for s in snapshots]
        # Also check the folder from the task record itself
        intent_folders: Counter = Counter()
        for snap in snapshots:
            f = snap["params"].get("folder", "")
            if f:
                intent_folders[f] += 1
        # Additionally, look at global folder usage for this intent
        # by checking _folder_counts intersection
        if intent_folders:
            top_folder, fc = intent_folders.most_common(1)[0]
            if fc >= 2:
                suggestions["preferred_folder"] = top_folder

        return suggestions

    # -- Merge --------------------------------------------------------------

    @staticmethod
    def merge_profiles(a: UserProfile, b: UserProfile) -> UserProfile:
        """Combine two profiles; higher frequency / more data wins."""
        # Preferences: b overwrites a (b assumed to be newer/larger)
        merged_prefs = dict(a.preferences)
        merged_prefs.update(b.preferences)

        # Frequent folders: union
        merged_folders = dict(a.frequent_folders)
        merged_folders.update(b.frequent_folders)

        # Contacts: union by name
        seen_names = set()
        merged_contacts = []
        for c in b.frequent_contacts + a.frequent_contacts:
            if c["name"] not in seen_names:
                seen_names.add(c["name"])
                merged_contacts.append(c)

        # Task patterns: keep higher frequency version of each pattern
        pattern_map: Dict[str, Dict[str, Any]] = {}
        for p in a.task_patterns + b.task_patterns:
            key = p["pattern"]
            if key not in pattern_map or p["frequency"] > pattern_map[key]["frequency"]:
                pattern_map[key] = p
        merged_patterns = list(pattern_map.values())

        # Avoided actions: union
        merged_avoided = list(set(a.avoided_actions) | set(b.avoided_actions))

        return UserProfile(
            preferences=merged_prefs,
            frequent_folders=merged_folders,
            frequent_contacts=merged_contacts,
            task_patterns=merged_patterns,
            avoided_actions=merged_avoided,
        )

    # -- Persistence --------------------------------------------------------

    def save(self, path: str) -> None:
        """Persist the current profile and raw accumulators to JSON."""
        data = {
            "profile": self.get_profile().to_dict(),
            "folder_counts": dict(self._folder_counts),
            "intent_counts": dict(self._intent_counts),
            "intent_params": {k: list(v) for k, v in self._intent_params.items()},
            "pref_observations": {k: list(v) for k, v in self._pref_observations.items()},
            "total_tasks": self._total_tasks,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        """Restore state from a previously saved JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._folder_counts = Counter(data.get("folder_counts", {}))
        self._intent_counts = Counter(data.get("intent_counts", {}))
        self._intent_params = {
            k: list(v) for k, v in data.get("intent_params", {}).items()
        }
        self._pref_observations = {
            k: list(v) for k, v in data.get("pref_observations", {}).items()
        }
        self._total_tasks = data.get("total_tasks", 0)

    def reset(self) -> None:
        """Clear all learned data."""
        self._folder_counts = Counter()
        self._intent_counts = Counter()
        self._intent_params = {}
        self._pref_observations = {}
        self._total_tasks = 0

    # -- Private builders ---------------------------------------------------

    def _build_preferences(self) -> Dict[str, Any]:
        """Extract preferences that pass the threshold."""
        prefs: Dict[str, Any] = {}
        for key, observations in self._pref_observations.items():
            if len(observations) < _PREFERENCE_THRESHOLD:
                continue
            counter = Counter(str(v) for v in observations)
            top_str, count = counter.most_common(1)[0]
            # Recover original value
            for v in observations:
                if str(v) == top_str:
                    prefs[key] = v
                    break
        return prefs

    def _build_frequent_folders(self) -> Dict[str, str]:
        """Return folders that have been used >= _FOLDER_THRESHOLD times."""
        folders: Dict[str, str] = {}
        for path, count in self._folder_counts.most_common():
            if count < _FOLDER_THRESHOLD:
                break
            # Auto-label from last path component
            label = path.rstrip("/").rsplit("/", 1)[-1] or path
            # Avoid duplicate labels
            base_label = label
            idx = 1
            while label in folders:
                label = f"{base_label}_{idx}"
                idx += 1
            folders[label] = path
        return folders

    def _build_task_patterns(self) -> List[Dict[str, Any]]:
        """Detect repeated intent+param combinations."""
        patterns: List[Dict[str, Any]] = []
        for intent, snapshots in self._intent_params.items():
            if len(snapshots) < _PATTERN_THRESHOLD:
                continue
            # Find dominant param values
            param_values: Dict[str, list] = {}
            for snap in snapshots:
                for k, v in snap["params"].items():
                    param_values.setdefault(k, []).append(v)

            preferred: Dict[str, Any] = {}
            for k, values in param_values.items():
                counter = Counter(str(v) for v in values)
                top_str, count = counter.most_common(1)[0]
                for v in values:
                    if str(v) == top_str:
                        preferred[k] = v
                        break

            last_used = ""
            for snap in reversed(snapshots):
                if snap.get("completed_at"):
                    last_used = snap["completed_at"]
                    break

            patterns.append({
                "pattern": intent,
                "frequency": len(snapshots),
                "last_used": last_used,
                "preferred_params": preferred,
            })
        return patterns
