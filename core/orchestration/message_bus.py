"""IntentOS Pub-Sub Message Bus for multi-agent orchestration.

Inspired by MetaGPT's publish-subscribe architecture. Agents subscribe to
action types (cause_by) and pull matching messages from the bus.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    """A message exchanged between agents on the bus."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    content: str
    cause_by: str  # action class name that produced this message
    sent_from: str  # source agent name
    send_to: Optional[str] = None  # target agent; None = broadcast
    payload: Any = None  # typed Pydantic model, dict, or None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the message to a plain dict."""
        data = {
            "id": self.id,
            "content": self.content,
            "cause_by": self.cause_by,
            "sent_from": self.sent_from,
            "send_to": self.send_to,
            "timestamp": self.timestamp.isoformat(),
        }
        # Convert Pydantic payload to dict if applicable
        if self.payload is None:
            data["payload"] = None
        elif isinstance(self.payload, BaseModel):
            data["payload"] = self.payload.model_dump()
        else:
            data["payload"] = self.payload
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Reconstruct a Message from a dict produced by to_dict()."""
        ts = data["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            id=data["id"],
            content=data["content"],
            cause_by=data["cause_by"],
            sent_from=data["sent_from"],
            send_to=data.get("send_to"),
            payload=data.get("payload"),
            timestamp=ts,
        )


class MessageBus:
    """Pull-based pub-sub message bus for agent orchestration."""

    def __init__(self) -> None:
        # cause_by action type -> set of agent names subscribed
        self._subscriptions: Dict[str, Set[str]] = {}
        # ordered list of all published messages
        self._history: List[Message] = []
        # agent_name -> index of last read position in _history
        self._read_markers: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(self, agent_name: str, watch: List[str]) -> None:
        """Register *agent_name* to receive messages with the given cause_by types."""
        for cause_by in watch:
            if cause_by not in self._subscriptions:
                self._subscriptions[cause_by] = set()
            self._subscriptions[cause_by].add(agent_name)

    def unsubscribe(self, agent_name: str, cause_by: str) -> None:
        """Remove *agent_name* from subscribers of *cause_by*."""
        if cause_by in self._subscriptions:
            self._subscriptions[cause_by].discard(agent_name)

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(self, message: Message) -> None:
        """Store a message in history (pull model -- no immediate delivery)."""
        self._history.append(message)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_messages_for(
        self, agent_name: str, unread_only: bool = False
    ) -> List[Message]:
        """Return messages matching *agent_name*'s subscriptions.

        A message matches if:
          - cause_by is in the agent's subscribed set, AND
          - send_to is None (broadcast) OR send_to == agent_name
        """
        watched = {
            cause_by
            for cause_by, agents in self._subscriptions.items()
            if agent_name in agents
        }

        start_idx = self._read_markers.get(agent_name, 0) if unread_only else 0
        results: List[Message] = []
        for msg in self._history[start_idx:]:
            if msg.cause_by not in watched:
                continue
            if msg.send_to is not None and msg.send_to != agent_name:
                continue
            results.append(msg)
        return results

    def get_pending_count(self, agent_name: str) -> int:
        """Return the number of unread messages for *agent_name*."""
        return len(self.get_messages_for(agent_name, unread_only=True))

    def mark_read(self, agent_name: str) -> None:
        """Mark all current messages as read for *agent_name*."""
        self._read_markers[agent_name] = len(self._history)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        cause_by: Optional[str] = None,
        sent_from: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[Message]:
        """Return historical messages, optionally filtered."""
        results: List[Message] = []
        for msg in self._history:
            if cause_by is not None and msg.cause_by != cause_by:
                continue
            if sent_from is not None and msg.sent_from != sent_from:
                continue
            if since is not None and msg.timestamp < since:
                continue
            if until is not None and msg.timestamp > until:
                continue
            results.append(msg)
        return results

    def clear_history(self) -> None:
        """Remove all messages and reset read markers."""
        self._history.clear()
        self._read_markers.clear()
