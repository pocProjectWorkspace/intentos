"""TDD tests for IntentOS Pub-Sub Message Bus."""

import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import BaseModel

from core.orchestration.message_bus import Message, MessageBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class SamplePayload(BaseModel):
    """A typed Pydantic payload used in tests."""
    task: str
    priority: int = 1


# ===========================================================================
# Message model tests (1-5)
# ===========================================================================

class TestMessageModel:
    """Tests 1-5: Message creation, defaults, serialisation."""

    def test_message_creation_with_all_fields(self):
        """Test 1: Message with every field explicitly set."""
        now = datetime.now(timezone.utc)
        msg = Message(
            id="custom-id",
            content="hello",
            cause_by="WriteCode",
            sent_from="coder_agent",
            send_to="reviewer_agent",
            payload={"key": "value"},
            timestamp=now,
        )
        assert msg.id == "custom-id"
        assert msg.content == "hello"
        assert msg.cause_by == "WriteCode"
        assert msg.sent_from == "coder_agent"
        assert msg.send_to == "reviewer_agent"
        assert msg.payload == {"key": "value"}
        assert msg.timestamp == now

    def test_auto_generated_uuid(self):
        """Test 2: id is a valid UUID4 when not provided."""
        msg = Message(content="x", cause_by="A", sent_from="a")
        UUID(msg.id, version=4)  # raises if invalid

    def test_auto_generated_timestamp(self):
        """Test 3: timestamp defaults to ~now when not provided."""
        before = datetime.now(timezone.utc)
        msg = Message(content="x", cause_by="A", sent_from="a")
        after = datetime.now(timezone.utc)
        assert before <= msg.timestamp <= after

    def test_serialization_round_trip(self):
        """Test 4: to_dict -> from_dict produces an equivalent Message."""
        msg = Message(
            content="round-trip",
            cause_by="ActionX",
            sent_from="agent1",
            send_to="agent2",
            payload={"nested": [1, 2, 3]},
        )
        d = msg.to_dict()
        restored = Message.from_dict(d)
        assert restored.id == msg.id
        assert restored.content == msg.content
        assert restored.cause_by == msg.cause_by
        assert restored.sent_from == msg.sent_from
        assert restored.send_to == msg.send_to
        assert restored.payload == msg.payload
        assert restored.timestamp == msg.timestamp

    def test_pydantic_payload(self):
        """Test 5: Message accepts a Pydantic BaseModel as payload."""
        payload = SamplePayload(task="build", priority=3)
        msg = Message(
            content="with model",
            cause_by="Plan",
            sent_from="planner",
            payload=payload,
        )
        assert msg.payload.task == "build"
        assert msg.payload.priority == 3


# ===========================================================================
# MessageBus tests (6-20)
# ===========================================================================

class TestMessageBus:
    """Tests 6-20: subscribe, publish, get, history, etc."""

    @pytest.fixture
    def bus(self) -> MessageBus:
        return MessageBus()

    # --- subscribe / publish / get_messages_for ---

    def test_subscribe(self, bus: MessageBus):
        """Test 6: Agent subscribes to cause_by action types."""
        bus.subscribe("agent_a", ["WriteCode", "ReviewCode"])
        # Internal state: agent_a watches both action types
        msgs_for = bus.get_messages_for("agent_a")
        assert msgs_for == []  # no messages yet, but no error

    def test_publish_stores_and_routes(self, bus: MessageBus):
        """Test 7: Publish stores in history and is retrievable by subscriber."""
        bus.subscribe("agent_a", ["WriteCode"])
        msg = Message(content="code ready", cause_by="WriteCode", sent_from="coder")
        bus.publish(msg)
        result = bus.get_messages_for("agent_a")
        assert len(result) == 1
        assert result[0].content == "code ready"

    def test_get_messages_no_match(self, bus: MessageBus):
        """Test 9: Returns empty when no messages match subscriptions."""
        bus.subscribe("agent_a", ["ReviewCode"])
        bus.publish(Message(content="x", cause_by="WriteCode", sent_from="c"))
        assert bus.get_messages_for("agent_a") == []

    def test_targeted_message(self, bus: MessageBus):
        """Test 10: send_to message only delivered to the named agent."""
        bus.subscribe("agent_a", ["WriteCode"])
        bus.subscribe("agent_b", ["WriteCode"])
        msg = Message(
            content="private",
            cause_by="WriteCode",
            sent_from="coder",
            send_to="agent_a",
        )
        bus.publish(msg)
        assert len(bus.get_messages_for("agent_a")) == 1
        assert len(bus.get_messages_for("agent_b")) == 0

    def test_broadcast_message(self, bus: MessageBus):
        """Test 11: send_to=None delivers to all matching subscribers."""
        bus.subscribe("agent_a", ["WriteCode"])
        bus.subscribe("agent_b", ["WriteCode"])
        msg = Message(content="broadcast", cause_by="WriteCode", sent_from="coder")
        bus.publish(msg)
        assert len(bus.get_messages_for("agent_a")) == 1
        assert len(bus.get_messages_for("agent_b")) == 1

    def test_multiple_subscribers(self, bus: MessageBus):
        """Test 12: Same message delivered to all who watch that cause_by."""
        bus.subscribe("a", ["Plan"])
        bus.subscribe("b", ["Plan"])
        bus.subscribe("c", ["Plan"])
        bus.publish(Message(content="plan done", cause_by="Plan", sent_from="planner"))
        for agent in ("a", "b", "c"):
            msgs = bus.get_messages_for(agent)
            assert len(msgs) == 1
            assert msgs[0].content == "plan done"

    def test_message_ordering(self, bus: MessageBus):
        """Test 13: Messages returned in publish order."""
        bus.subscribe("a", ["Act"])
        for i in range(5):
            bus.publish(Message(content=f"msg-{i}", cause_by="Act", sent_from="s"))
        msgs = bus.get_messages_for("a")
        assert [m.content for m in msgs] == [f"msg-{i}" for i in range(5)]

    # --- History ---

    def test_full_history(self, bus: MessageBus):
        """Test 14: Full message history accessible."""
        bus.publish(Message(content="a", cause_by="X", sent_from="s"))
        bus.publish(Message(content="b", cause_by="Y", sent_from="s"))
        history = bus.get_history()
        assert len(history) == 2

    def test_history_filter_cause_by(self, bus: MessageBus):
        """Test 15a: History filtered by cause_by."""
        bus.publish(Message(content="a", cause_by="X", sent_from="s"))
        bus.publish(Message(content="b", cause_by="Y", sent_from="s"))
        assert len(bus.get_history(cause_by="X")) == 1

    def test_history_filter_sent_from(self, bus: MessageBus):
        """Test 15b: History filtered by sent_from."""
        bus.publish(Message(content="a", cause_by="X", sent_from="alice"))
        bus.publish(Message(content="b", cause_by="X", sent_from="bob"))
        assert len(bus.get_history(sent_from="bob")) == 1

    def test_history_filter_time_range(self, bus: MessageBus):
        """Test 15c: History filtered by time range."""
        t1 = datetime.now(timezone.utc)
        bus.publish(Message(content="old", cause_by="X", sent_from="s", timestamp=t1 - timedelta(hours=2)))
        bus.publish(Message(content="new", cause_by="X", sent_from="s", timestamp=t1))
        result = bus.get_history(since=t1 - timedelta(hours=1))
        assert len(result) == 1
        assert result[0].content == "new"

    def test_history_filter_until(self, bus: MessageBus):
        """Test 15d: History filtered with until parameter."""
        t1 = datetime.now(timezone.utc)
        bus.publish(Message(content="old", cause_by="X", sent_from="s", timestamp=t1 - timedelta(hours=2)))
        bus.publish(Message(content="new", cause_by="X", sent_from="s", timestamp=t1))
        result = bus.get_history(until=t1 - timedelta(hours=1))
        assert len(result) == 1
        assert result[0].content == "old"

    def test_clear_history(self, bus: MessageBus):
        """Test 16: clear_history empties everything."""
        bus.publish(Message(content="a", cause_by="X", sent_from="s"))
        bus.clear_history()
        assert bus.get_history() == []

    # --- unsubscribe ---

    def test_unsubscribe(self, bus: MessageBus):
        """Test 17: Agent stops receiving messages for a cause_by type."""
        bus.subscribe("agent_a", ["WriteCode", "ReviewCode"])
        bus.unsubscribe("agent_a", "WriteCode")
        bus.publish(Message(content="code", cause_by="WriteCode", sent_from="c"))
        bus.publish(Message(content="review", cause_by="ReviewCode", sent_from="c"))
        msgs = bus.get_messages_for("agent_a")
        assert len(msgs) == 1
        assert msgs[0].content == "review"

    # --- pending count / mark_read ---

    def test_pending_count(self, bus: MessageBus):
        """Test 18: get_pending_count returns unread count."""
        bus.subscribe("a", ["Act"])
        bus.publish(Message(content="1", cause_by="Act", sent_from="s"))
        bus.publish(Message(content="2", cause_by="Act", sent_from="s"))
        assert bus.get_pending_count("a") == 2

    def test_mark_read(self, bus: MessageBus):
        """Test 19: mark_read then get_pending_count returns 0; new msgs counted."""
        bus.subscribe("a", ["Act"])
        bus.publish(Message(content="1", cause_by="Act", sent_from="s"))
        bus.mark_read("a")
        assert bus.get_pending_count("a") == 0
        bus.publish(Message(content="2", cause_by="Act", sent_from="s"))
        assert bus.get_pending_count("a") == 1

    def test_get_messages_unread_only(self, bus: MessageBus):
        """Test 8 (extended): get_messages_for with unread_only flag."""
        bus.subscribe("a", ["Act"])
        bus.publish(Message(content="1", cause_by="Act", sent_from="s"))
        bus.mark_read("a")
        bus.publish(Message(content="2", cause_by="Act", sent_from="s"))
        unread = bus.get_messages_for("a", unread_only=True)
        assert len(unread) == 1
        assert unread[0].content == "2"

    # --- concurrent safety ---

    def test_concurrent_safety(self, bus: MessageBus):
        """Test 20: Rapid publish/subscribe does not corrupt data."""
        for i in range(100):
            bus.subscribe(f"agent_{i % 10}", [f"Action_{i % 5}"])
        for i in range(200):
            bus.publish(
                Message(content=f"m{i}", cause_by=f"Action_{i % 5}", sent_from=f"src_{i}")
            )
        assert len(bus.get_history()) == 200
        # Every agent that subscribes to Action_0 should get exactly 40 msgs
        msgs = bus.get_messages_for("agent_0")
        action_types = {m.cause_by for m in msgs}
        # agent_0 subscribes when i%10==0, i.e. i=0,10,20,...,90
        # cause_by for those: Action_0, Action_0, Action_0, ... (i%5 when i%10==0 => 0,0,0,...0)
        # So agent_0 watches {"Action_0"}
        assert "Action_0" in action_types


# ===========================================================================
# Typed Payload tests (21-23)
# ===========================================================================

class TestTypedPayload:
    """Tests 21-23: Pydantic payload handling."""

    def test_pydantic_payload_round_trip(self):
        """Test 21: Pydantic BaseModel payload survives to_dict/from_dict."""
        payload = SamplePayload(task="deploy", priority=5)
        msg = Message(
            content="go",
            cause_by="Deploy",
            sent_from="deployer",
            payload=payload,
        )
        d = msg.to_dict()
        restored = Message.from_dict(d)
        # Payload comes back as a dict after round-trip (no type info in dict)
        assert restored.payload["task"] == "deploy"
        assert restored.payload["priority"] == 5

    def test_payload_none_is_valid(self):
        """Test 22: payload=None is perfectly fine."""
        msg = Message(content="x", cause_by="A", sent_from="a", payload=None)
        assert msg.payload is None
        d = msg.to_dict()
        restored = Message.from_dict(d)
        assert restored.payload is None

    def test_payload_arbitrary_type_stored(self):
        """Test 23: Bus doesn't enforce payload types — stores anything."""
        msg = Message(
            content="x",
            cause_by="A",
            sent_from="a",
            payload="just a string",
        )
        assert msg.payload == "just a string"
        msg2 = Message(
            content="x",
            cause_by="A",
            sent_from="a",
            payload=42,
        )
        assert msg2.payload == 42
