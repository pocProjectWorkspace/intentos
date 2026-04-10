"""SQLite-backed chat session persistence for IntentOS.

Stores conversation sessions and messages so users can resume chats
days or months later. Uses only stdlib (sqlite3).

Schema:
    sessions: id, title, created_at, updated_at
    messages: id, session_id, role, content, file_name, cost_usd, duration_ms, model, created_at
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ChatMessage:
    id: str
    session_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    file_name: Optional[str] = None
    cost_usd: float = 0.0
    duration_ms: int = 0
    model: str = ""
    created_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "file_name": self.file_name,
            "cost_usd": self.cost_usd,
            "duration_ms": self.duration_ms,
            "model": self.model,
            "created_at": self.created_at,
        }


@dataclass
class ChatSession:
    id: str
    title: str
    created_at: float
    updated_at: float
    message_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
        }


# ---------------------------------------------------------------------------
# ChatStore
# ---------------------------------------------------------------------------

class ChatStore:
    """SQLite-backed store for chat sessions and messages."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.expanduser("~"), ".intentos", "chat.db"
            )
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    file_name TEXT,
                    cost_usd REAL DEFAULT 0.0,
                    duration_ms INTEGER DEFAULT 0,
                    model TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id, created_at);
            """)

    # -- Sessions -----------------------------------------------------------

    def create_session(self, title: str = "New conversation") -> ChatSession:
        session_id = str(uuid.uuid4())
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title, now, now),
            )
        return ChatSession(id=session_id, title=title, created_at=now, updated_at=now)

    def list_sessions(self, limit: int = 50, offset: int = 0) -> List[ChatSession]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       COUNT(m.id) as message_count
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset)).fetchall()
        return [
            ChatSession(
                id=r["id"], title=r["title"],
                created_at=r["created_at"], updated_at=r["updated_at"],
                message_count=r["message_count"],
            )
            for r in rows
        ]

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        with self._conn() as conn:
            row = conn.execute("""
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       COUNT(m.id) as message_count
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                WHERE s.id = ?
                GROUP BY s.id
            """, (session_id,)).fetchone()
        if not row:
            return None
        return ChatSession(
            id=row["id"], title=row["title"],
            created_at=row["created_at"], updated_at=row["updated_at"],
            message_count=row["message_count"],
        )

    def update_session_title(self, session_id: str, title: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, time.time(), session_id),
            )

    def delete_session(self, session_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def _touch_session(self, session_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (time.time(), session_id),
            )

    # -- Messages -----------------------------------------------------------

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        file_name: Optional[str] = None,
        cost_usd: float = 0.0,
        duration_ms: int = 0,
        model: str = "",
    ) -> ChatMessage:
        msg_id = str(uuid.uuid4())
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO messages
                   (id, session_id, role, content, file_name, cost_usd, duration_ms, model, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (msg_id, session_id, role, content, file_name, cost_usd, duration_ms, model, now),
            )
        self._touch_session(session_id)

        # Auto-title: use first user message as title
        session = self.get_session(session_id)
        if session and session.message_count <= 1 and role == "user":
            title = content[:80] + ("..." if len(content) > 80 else "")
            self.update_session_title(session_id, title)

        return ChatMessage(
            id=msg_id, session_id=session_id, role=role, content=content,
            file_name=file_name, cost_usd=cost_usd, duration_ms=duration_ms,
            model=model, created_at=now,
        )

    def get_messages(self, session_id: str, limit: int = 200) -> List[ChatMessage]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id, session_id, role, content, file_name,
                          cost_usd, duration_ms, model, created_at
                   FROM messages
                   WHERE session_id = ?
                   ORDER BY created_at ASC
                   LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        return [
            ChatMessage(
                id=r["id"], session_id=r["session_id"], role=r["role"],
                content=r["content"], file_name=r["file_name"],
                cost_usd=r["cost_usd"], duration_ms=r["duration_ms"],
                model=r["model"], created_at=r["created_at"],
            )
            for r in rows
        ]

    def search_messages(self, query: str, limit: int = 20) -> List[ChatMessage]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id, session_id, role, content, file_name,
                          cost_usd, duration_ms, model, created_at
                   FROM messages
                   WHERE content LIKE ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (f"%{query}%", limit),
            ).fetchall()
        return [
            ChatMessage(
                id=r["id"], session_id=r["session_id"], role=r["role"],
                content=r["content"], file_name=r["file_name"],
                cost_usd=r["cost_usd"], duration_ms=r["duration_ms"],
                model=r["model"], created_at=r["created_at"],
            )
            for r in rows
        ]

    # -- Stats --------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        with self._conn() as conn:
            session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            message_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            total_cost = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM messages"
            ).fetchone()[0]
        return {
            "total_sessions": session_count,
            "total_messages": message_count,
            "total_cost_usd": total_cost,
        }
