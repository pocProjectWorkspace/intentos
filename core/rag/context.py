"""RAG Context Assembler — unified context system for the IntentOS kernel.

Wires TaskIndex, ExperienceRetriever, FileIndex, and ChatStore into a single
query interface that builds rich context before every task execution.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.rag.experience import ExperienceRetriever
from core.rag.file_index import FileIndex
from core.rag.task_index import TaskIndex, TaskRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Budget allocation fractions
# ---------------------------------------------------------------------------
_FILE_BUDGET_FRAC = 0.40
_PREF_BUDGET_FRAC = 0.10
_TASK_BUDGET_FRAC = 0.30
_SUGGEST_BUDGET_FRAC = 0.20


# ---------------------------------------------------------------------------
# AssembledContext
# ---------------------------------------------------------------------------

@dataclass
class AssembledContext:
    """Container for all context gathered before task execution."""

    relevant_files: List[Dict[str, Any]] = field(default_factory=list)
    recent_tasks: List[Dict[str, Any]] = field(default_factory=list)
    related_conversations: List[Dict[str, Any]] = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[Dict[str, Any]] = field(default_factory=list)
    context_text: str = ""
    token_estimate: int = 0


# ---------------------------------------------------------------------------
# ContextAssembler
# ---------------------------------------------------------------------------

class ContextAssembler:
    """Builds unified context for the kernel by querying all RAG indexes."""

    def __init__(
        self,
        task_index: Optional[TaskIndex] = None,
        file_index: Optional[FileIndex] = None,
        experience: Optional[ExperienceRetriever] = None,
        chat_store: Optional[Any] = None,
        storage_dir: Optional[str] = None,
    ) -> None:
        self.storage_dir: Path = (
            Path(storage_dir) if storage_dir else Path.home() / ".intentos" / "rag"
        )

        self.task_index: TaskIndex = task_index or TaskIndex()
        self.file_index: FileIndex = file_index or FileIndex()
        self.experience: ExperienceRetriever = experience or ExperienceRetriever()
        self.chat_store: Optional[Any] = chat_store

        # Auto-load ChatStore if not provided
        if self.chat_store is None:
            try:
                from core.storage.chat_store import ChatStore
                self.chat_store = ChatStore()
            except Exception:
                pass

        # Auto-load from storage_dir when no explicit indexes supplied
        if task_index is None and file_index is None and experience is None:
            self._try_auto_load()

    # -- public API ---------------------------------------------------------

    def build_context(
        self,
        user_input: Optional[str],
        max_tokens: int = 2000,
    ) -> AssembledContext:
        """Assemble context from all indexes for the given user input."""
        if user_input is None:
            ctx = AssembledContext(user_preferences=self._default_preferences())
            ctx.context_text = self.format_context(ctx)
            ctx.token_estimate = self.get_token_estimate(ctx.context_text)
            return ctx

        # Compute per-section budgets (in tokens)
        file_budget = int(max_tokens * _FILE_BUDGET_FRAC)
        pref_budget = int(max_tokens * _PREF_BUDGET_FRAC)
        task_budget = int(max_tokens * _TASK_BUDGET_FRAC)
        suggest_budget = int(max_tokens * _SUGGEST_BUDGET_FRAC)

        # 1. Files (always)
        relevant_files = self._query_files(user_input, file_budget)

        # 2. Preferences (always, small)
        user_preferences = self._query_experience_prefs()

        # 3. Tasks (if budget allows)
        recent_tasks = self._query_tasks(user_input, task_budget)

        # 4. Suggestions
        suggestions = self._query_experience(user_input, suggest_budget)

        # 5. Past conversations (search ChatStore)
        related_conversations = self._query_chat_history(user_input)

        # 6. Cross-reference: enrich with files from matching tasks
        relevant_files = self._enrich_files_from_tasks(
            relevant_files, recent_tasks,
        )

        # Build the context object
        ctx = AssembledContext(
            relevant_files=relevant_files,
            recent_tasks=recent_tasks,
            related_conversations=related_conversations,
            user_preferences=user_preferences,
            suggestions=suggestions,
        )

        # Format and enforce total budget
        ctx.context_text = self.format_context(ctx)
        ctx.token_estimate = self.get_token_estimate(ctx.context_text)

        # Truncate if over budget
        if ctx.token_estimate > max_tokens:
            ctx = self._truncate_to_budget(ctx, max_tokens)

        return ctx

    def record_task(
        self,
        raw_input: str,
        intent: str,
        agents: List[str],
        files: List[str],
        params: Dict,
        status: str,
        duration: int,
    ) -> TaskRecord:
        """Record a completed task and feed it to experience learning."""
        rec = self.task_index.record_from_execution(
            raw_input=raw_input,
            intent=intent,
            agents=agents,
            files=files,
            params=params,
            status=status,
            duration=duration,
        )

        # Feed to experience retriever
        self.experience.learn({
            "intent": intent,
            "params": params,
            "folder": os.path.dirname(files[0]) if files else "",
            "completed_at": rec.timestamp.isoformat(),
        })

        # Auto-save task index
        self._ensure_storage_dir()
        task_path = str(self.storage_dir / "task_index.jsonl")
        self.task_index.save(task_path)

        return rec

    def save_all(self) -> None:
        """Persist all indexes to storage_dir."""
        self._ensure_storage_dir()
        self.task_index.save(str(self.storage_dir / "task_index.jsonl"))
        self.file_index.save(str(self.storage_dir / "file_index.json"))
        self.experience.save(str(self.storage_dir / "experience.json"))

    def load_all(self) -> None:
        """Load all indexes from storage_dir."""
        ti_path = self.storage_dir / "task_index.jsonl"
        fi_path = self.storage_dir / "file_index.json"
        er_path = self.storage_dir / "experience.json"
        if ti_path.exists():
            self.task_index.load(str(ti_path))
        if fi_path.exists():
            self.file_index.load(str(fi_path))
        if er_path.exists():
            self.experience.load(str(er_path))

    def format_context(self, assembled: AssembledContext) -> str:
        """Format an AssembledContext into a human/LLM-readable string."""
        sections: List[str] = []

        # Relevant files
        lines = ["Relevant files:"]
        if assembled.relevant_files:
            for f in assembled.relevant_files:
                lines.append(
                    f"  - {f.get('name', '?')} ({f.get('type', '?')}, "
                    f"{f.get('size', 0)} bytes) — {f.get('path', '?')}"
                )
        else:
            lines.append("  (none)")
        sections.append("\n".join(lines))

        # Recent similar tasks
        lines = ["Recent similar tasks:"]
        if assembled.recent_tasks:
            for t in assembled.recent_tasks:
                lines.append(
                    f"  - Input: {t.get('raw_input', '?')}\n"
                    f"    Agents: {', '.join(t.get('agents', []))}\n"
                    f"    Status: {t.get('status', '?')}\n"
                    f"    Parameters: {_format_params(t.get('parameters', {}))}"
                )
        else:
            lines.append("  (none)")
        sections.append("\n".join(lines))

        # User preferences
        pref_lines = ["User preferences:"]
        prefs = assembled.user_preferences
        if prefs.get("preferences"):
            for p in prefs["preferences"]:
                pref_lines.append(f"  - {p.get('key', '?')}: {p.get('value', '?')}")
        if prefs.get("frequent_folders"):
            folders = prefs["frequent_folders"]
            folder_strs = [ff.get("path", "?") for ff in folders[:3]]
            pref_lines.append(f"  - Frequent folders: {', '.join(folder_strs)}")
        if len(pref_lines) == 1:
            pref_lines.append("  (none detected yet)")
        sections.append("\n".join(pref_lines))

        # Related past conversations
        if assembled.related_conversations:
            lines = ["Related past conversations:"]
            for conv in assembled.related_conversations:
                session_title = conv.get("session_title", "")
                lines.append(f"  Session: {session_title}")
                for msg in conv.get("messages", []):
                    role = msg.get("role", "?")
                    content = msg.get("content", "")[:200]
                    lines.append(f"    [{role}] {content}")
            sections.append("\n".join(lines))

        # Suggestions
        if assembled.suggestions:
            lines = ["Suggestions:"]
            for s in assembled.suggestions:
                desc = s.get("description", s.get("key", "suggestion"))
                conf = s.get("confidence", 0)
                lines.append(f"  - {desc} (confidence: {conf:.0%})")
            sections.append("\n".join(lines))

        return "\n\n".join(sections)

    @staticmethod
    def get_token_estimate(text: str) -> int:
        """Approximate token count (chars / 4)."""
        return len(text) // 4

    # -- private helpers ----------------------------------------------------

    def _query_files(self, user_input: str, budget: int) -> List[Dict[str, Any]]:
        """Search FileIndex and return top 3 matching file dicts."""
        if self.file_index.count == 0:
            return []
        results = self.file_index.search(user_input)[:3]
        file_dicts: List[Dict[str, Any]] = []
        for entry in results:
            fd = {
                "path": entry.path,
                "name": entry.filename,
                "type": entry.file_type,
                "size": entry.size_bytes,
                "modified": entry.modified.isoformat(),
            }
            file_dicts.append(fd)
        return file_dicts

    def _query_tasks(self, user_input: str, budget: int) -> List[Dict[str, Any]]:
        """Find similar past tasks and return summary dicts."""
        if self.task_index.count == 0:
            return []
        similar = self.task_index.find_similar(user_input)
        task_dicts: List[Dict[str, Any]] = []
        for rec in similar:
            td = {
                "raw_input": rec.raw_input,
                "intent": rec.resolved_intent,
                "agents": list(rec.agents_used),
                "parameters": dict(rec.parameters_used),
                "status": rec.result_status,
            }
            task_dicts.append(td)
        return task_dicts

    def _query_experience(self, user_input: str, budget: int) -> List[Dict[str, Any]]:
        """Get suggestions from experience retriever."""
        # Try to infer intent from task history
        intent = self._guess_intent(user_input)
        return self.experience.suggest(user_input, intent)

    def _query_experience_prefs(self) -> Dict[str, Any]:
        """Build user preferences dict from experience retriever."""
        profile = self.experience.build_profile()
        return {
            "preferences": profile.get("preferences", []),
            "frequent_folders": profile.get("frequent_folders", []),
        }

    def _query_chat_history(self, user_input: str) -> List[Dict[str, Any]]:
        """Search past chat sessions for messages relevant to the query."""
        if not self.chat_store:
            return []

        try:
            # Extract key words (skip common filler words)
            stop_words = {
                "the", "a", "an", "is", "was", "were", "are", "in", "on", "at",
                "to", "for", "of", "with", "and", "or", "but", "not", "it", "my",
                "we", "i", "you", "that", "this", "where", "what", "how", "can",
                "do", "did", "about", "from", "last", "week", "file", "find",
                "worked", "remember", "me", "have", "had", "has",
            }
            words = [
                w for w in user_input.lower().split()
                if w not in stop_words and len(w) > 2
            ]

            if not words:
                return []

            # Search for each meaningful word in chat history
            all_matches = []
            seen_sessions = set()
            for word in words[:5]:  # limit to 5 keywords
                matches = self.chat_store.search_messages(word, limit=5)
                for msg in matches:
                    if msg.session_id not in seen_sessions:
                        seen_sessions.add(msg.session_id)
                        all_matches.append(msg)

            if not all_matches:
                return []

            # For each matching session, get a summary
            results = []
            for msg in all_matches[:3]:  # top 3 sessions
                session = self.chat_store.get_session(msg.session_id)
                if not session:
                    continue
                # Get first few messages for context
                session_msgs = self.chat_store.get_messages(msg.session_id, limit=6)
                results.append({
                    "session_id": session.id,
                    "session_title": session.title,
                    "date": session.updated_at,
                    "messages": [
                        {"role": m.role, "content": m.content[:200]}
                        for m in session_msgs
                    ],
                })

            return results
        except Exception:
            return []

    def _enrich_files_from_tasks(
        self,
        files: List[Dict[str, Any]],
        tasks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Cross-reference: add files mentioned in matching tasks."""
        existing_paths = {f.get("path", "") for f in files}

        for task in tasks:
            # TaskRecord stores files_affected — pull from task_index
            raw_input = task.get("raw_input", "")
            if not raw_input:
                continue

            # Find the actual TaskRecord to get files_affected
            similar = self.task_index.find_similar(raw_input)
            for rec in similar[:2]:
                for fpath in rec.files_affected:
                    if fpath and fpath not in existing_paths and os.path.exists(fpath):
                        existing_paths.add(fpath)
                        files.append({
                            "path": fpath,
                            "name": os.path.basename(fpath),
                            "type": os.path.splitext(fpath)[1],
                            "size": os.path.getsize(fpath) if os.path.exists(fpath) else 0,
                            "source": "task_history",
                        })

        return files

    def _default_preferences(self) -> Dict[str, Any]:
        """Return default (empty) preferences structure."""
        return {
            "preferences": [],
            "frequent_folders": [],
        }

    def _guess_intent(self, user_input: str) -> str:
        """Best-effort intent guess from task history."""
        if self.task_index.count == 0:
            return ""
        similar = self.task_index.find_similar(user_input)
        if similar:
            return similar[0].resolved_intent
        return ""

    def _truncate_to_budget(
        self, ctx: AssembledContext, max_tokens: int
    ) -> AssembledContext:
        """Progressively drop content to fit within max_tokens.

        Drop order: suggestions -> older tasks -> files (trim list).
        Preferences are always kept (small).
        """
        # Try dropping suggestions first
        ctx.suggestions = []
        ctx.context_text = self.format_context(ctx)
        ctx.token_estimate = self.get_token_estimate(ctx.context_text)
        if ctx.token_estimate <= max_tokens:
            return ctx

        # Drop tasks
        while ctx.recent_tasks and ctx.token_estimate > max_tokens:
            ctx.recent_tasks.pop()
            ctx.context_text = self.format_context(ctx)
            ctx.token_estimate = self.get_token_estimate(ctx.context_text)
        if ctx.token_estimate <= max_tokens:
            return ctx

        # Trim files
        while ctx.relevant_files and ctx.token_estimate > max_tokens:
            ctx.relevant_files.pop()
            ctx.context_text = self.format_context(ctx)
            ctx.token_estimate = self.get_token_estimate(ctx.context_text)
        if ctx.token_estimate <= max_tokens:
            return ctx

        # Last resort: hard truncate the text
        char_limit = max_tokens * 4
        ctx.context_text = ctx.context_text[:char_limit]
        ctx.token_estimate = self.get_token_estimate(ctx.context_text)
        return ctx

    def _try_auto_load(self) -> None:
        """Attempt to load indexes from storage_dir if files exist."""
        try:
            self.load_all()
        except Exception:
            pass  # No persisted state yet — that's fine

    def _ensure_storage_dir(self) -> None:
        """Create storage directory if it doesn't exist."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_params(params: Dict) -> str:
    """Format parameters dict into a readable string."""
    if not params:
        return "(none)"
    return ", ".join(f"{k}={v}" for k, v in params.items())
