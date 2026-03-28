"""RAG Proactive Suggestions — suggests related actions after task completion.

Phase 4.2: After a task completes, the SuggestionEngine analyses file indexes,
task history, and learned experience to propose follow-up actions the user
might want to take next.
"""

import logging
import os
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular dependencies — the actual types are only
# needed at runtime inside generate().
# from core.rag.file_index import FileIndex
# from core.rag.task_index import TaskIndex, TaskRecord
# from core.rag.experience import ExperienceRetriever

_MIN_CONFIDENCE = 0.3
_MAX_SUGGESTIONS = 5

# Maps intent keywords to suggested follow-up actions.
_FOLLOW_UP_MAP: Dict[str, List[dict]] = {
    "create_document": [
        {
            "description": "Want me to export this as PDF?",
            "confidence": 0.75,
            "action_hint": {"intent": "export_pdf"},
        },
        {
            "description": "Want me to back up this document?",
            "confidence": 0.5,
            "action_hint": {"intent": "backup_file"},
        },
    ],
    "rename_file": [
        {
            "description": "Want me to update any references to the old filename?",
            "confidence": 0.65,
            "action_hint": {"intent": "update_references"},
        },
    ],
    "rename_photo": [
        {
            "description": "Want me to organise these photos into date-based folders?",
            "confidence": 0.6,
            "action_hint": {"intent": "organise_photos"},
        },
    ],
    "process_invoice": [
        {
            "description": "Want me to add this to your expense tracker?",
            "confidence": 0.6,
            "action_hint": {"intent": "track_expense"},
        },
    ],
    "list_large_files": [
        {
            "description": "Want me to move old files to archive?",
            "confidence": 0.5,
            "action_hint": {"intent": "archive_files"},
        },
    ],
}

# Size threshold (bytes) above which files are considered "large" for
# duplicate detection purposes.
_DUPLICATE_SIZE_THRESHOLD = 1_000_000  # 1 MB


# ---------------------------------------------------------------------------
# Suggestion dataclass
# ---------------------------------------------------------------------------

@dataclass
class Suggestion:
    """A single proactive suggestion."""
    type: str          # "related_files" | "similar_action" | "optimization" | "follow_up"
    description: str
    confidence: float  # 0.0 – 1.0
    action_hint: dict  # suggested intent + params if user accepts


# ---------------------------------------------------------------------------
# SuggestionEngine
# ---------------------------------------------------------------------------

class SuggestionEngine:
    """Generates ranked proactive suggestions after a task completes."""

    def generate(
        self,
        completed_task,
        file_index=None,
        task_index=None,
        experience=None,
    ) -> List[Suggestion]:
        """Return a list of suggestions based on the completed task and indexes.

        Parameters
        ----------
        completed_task : TaskRecord
            The task that just finished executing.
        file_index : FileIndex | None
            Optional file index for related-file discovery.
        task_index : TaskIndex | None
            Optional task index for similar-action discovery.
        experience : ExperienceRetriever | None
            Optional experience retriever for pattern-based suggestions.

        Returns
        -------
        list[Suggestion]
            Ranked suggestions with confidence > 0.3, at most 5.
        """
        # Failed tasks get no suggestions.
        if completed_task.result_status != "success":
            return []

        suggestions: List[Suggestion] = []

        files = completed_task.files_affected or []

        # --- Related files ---------------------------------------------------
        if file_index is not None and files:
            suggestions.extend(self._related_files(files, file_index))

        # --- Similar actions -------------------------------------------------
        if task_index is not None and files:
            suggestions.extend(
                self._similar_actions(completed_task, task_index)
            )

        # --- Optimizations ---------------------------------------------------
        if file_index is not None and files:
            suggestions.extend(self._optimizations(files, file_index))

        # --- Follow-ups (always available) -----------------------------------
        suggestions.extend(self._follow_ups(completed_task))

        # --- Experience-based suggestions ------------------------------------
        if experience is not None:
            suggestions.extend(
                self._experience_suggestions(completed_task, experience)
            )

        # --- Filtering and ranking -------------------------------------------
        suggestions = [s for s in suggestions if s.confidence > _MIN_CONFIDENCE]
        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        return suggestions[:_MAX_SUGGESTIONS]

    # -- private helpers -----------------------------------------------------

    def _related_files(self, files: List[str], file_index) -> List[Suggestion]:
        """Find files in the same folder with the same extension."""
        suggestions: List[Suggestion] = []
        seen_folders: set = set()

        for fpath in files:
            folder = os.path.dirname(fpath)
            ext = os.path.splitext(fpath)[1].lower()
            if not folder or (folder, ext) in seen_folders:
                continue
            seen_folders.add((folder, ext))

            # Find siblings: same folder, same type, excluding already-processed
            siblings = [
                e for e in file_index._entries.values()
                if os.path.dirname(e.path) == folder
                and e.file_type == ext
                and e.path not in files
            ]

            if siblings:
                count = len(siblings)
                desc = (
                    f"I found {count} other {ext} file{'s' if count != 1 else ''} "
                    f"in {folder} — want me to do anything with them?"
                )
                suggestions.append(Suggestion(
                    type="related_files",
                    description=desc,
                    confidence=min(0.5 + count * 0.1, 0.95),
                    action_hint={
                        "intent": "process_files",
                        "params": {"folder": folder, "type": ext},
                    },
                ))

        return suggestions

    def _similar_actions(self, completed_task, task_index) -> List[Suggestion]:
        """Find past tasks with the same intent affecting different folders."""
        suggestions: List[Suggestion] = []
        intent = completed_task.resolved_intent
        current_folders = {
            os.path.dirname(f) for f in completed_task.files_affected if f
        }

        past = task_index.search_by_intent(intent)
        # Group past task files by folder, excluding current folders
        other_folders: Counter = Counter()
        for rec in past:
            for f in rec.files_affected:
                folder = os.path.dirname(f)
                if folder and folder not in current_folders:
                    other_folders[folder] += 1

        if other_folders:
            top_folder, count = other_folders.most_common(1)[0]
            if count >= 2:
                desc = (
                    f"You have {count} more files from similar tasks "
                    f"in {top_folder}."
                )
                suggestions.append(Suggestion(
                    type="similar_action",
                    description=desc,
                    confidence=min(0.4 + count * 0.05, 0.9),
                    action_hint={
                        "intent": intent,
                        "params": {"folder": top_folder},
                    },
                ))

        return suggestions

    def _optimizations(self, files: List[str], file_index) -> List[Suggestion]:
        """Detect potential duplicates (same size + same extension in folder)."""
        suggestions: List[Suggestion] = []
        seen_folders: set = set()

        for fpath in files:
            folder = os.path.dirname(fpath)
            if not folder or folder in seen_folders:
                continue
            seen_folders.add(folder)

            # Group files in folder by (size, extension)
            folder_entries = [
                e for e in file_index._entries.values()
                if os.path.dirname(e.path) == folder
                and e.size_bytes >= _DUPLICATE_SIZE_THRESHOLD
            ]

            size_groups: Dict[tuple, list] = {}
            for e in folder_entries:
                key = (e.size_bytes, e.file_type)
                size_groups.setdefault(key, []).append(e)

            for (size, ext), group in size_groups.items():
                if len(group) >= 2:
                    total_bytes = size * len(group)
                    size_str = _human_size(total_bytes)
                    desc = (
                        f"These {len(group)} files are potential duplicates "
                        f"taking {size_str} — want to clean them up?"
                    )
                    suggestions.append(Suggestion(
                        type="optimization",
                        description=desc,
                        confidence=min(0.5 + len(group) * 0.08, 0.92),
                        action_hint={
                            "intent": "deduplicate",
                            "params": {"folder": folder, "type": ext},
                        },
                    ))

        return suggestions

    def _follow_ups(self, completed_task) -> List[Suggestion]:
        """Return intent-based follow-up suggestions."""
        suggestions: List[Suggestion] = []
        intent = completed_task.resolved_intent

        entries = _FOLLOW_UP_MAP.get(intent, [])
        for entry in entries:
            suggestions.append(Suggestion(
                type="follow_up",
                description=entry["description"],
                confidence=entry["confidence"],
                action_hint=entry["action_hint"],
            ))

        return suggestions

    def _experience_suggestions(self, completed_task, experience) -> List[Suggestion]:
        """Pull suggestions from the ExperienceRetriever."""
        suggestions: List[Suggestion] = []
        try:
            exp_suggestions = experience.suggest(
                completed_task.raw_input, completed_task.resolved_intent
            )
        except Exception:
            logger.debug("Experience retriever returned no suggestions", exc_info=True)
            return []

        for es in exp_suggestions:
            conf = es.get("confidence", 0.4)
            if conf <= _MIN_CONFIDENCE:
                continue
            suggestions.append(Suggestion(
                type="follow_up",
                description=es.get("description", str(es)),
                confidence=conf,
                action_hint=es.get("parameters", {}),
            ))

        return suggestions


# ---------------------------------------------------------------------------
# format_suggestions
# ---------------------------------------------------------------------------

def format_suggestions(suggestions: List[Suggestion]) -> str:
    """Format a list of suggestions as plain-language text for CLI display.

    Returns an empty string when there are no suggestions.
    """
    if not suggestions:
        return ""

    lines: List[str] = []
    for i, s in enumerate(suggestions, 1):
        lines.append(f"  {i}. {s.description}")

    header = "Suggestions:"
    return header + "\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _human_size(nbytes: int) -> str:
    """Convert byte count to a human-readable string."""
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024  # type: ignore[assignment]
    return f"{nbytes:.1f} PB"
