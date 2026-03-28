"""
Tests for IntentOS Secrets Manager (Phase 4.6).

Enterprise credential management with rotation, expiration, and access tracking.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from core.security.encryption import CredentialStore, EncryptedBlob
from core.security.secrets_manager import SecretEntry, SecretsManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def master_key():
    return os.urandom(32)


@pytest.fixture
def manager(master_key):
    return SecretsManager(master_key=master_key)


@pytest.fixture
def populated_manager(manager):
    """Manager pre-loaded with a few secrets."""
    manager.store("db_password", "s3cret!", owner="alice", tags=["database"])
    manager.store("api_key", "sk-abc123", owner="bob", tags=["api_key", "service_account"])
    manager.store("redis_url", "redis://localhost:6379", owner="alice", tags=["database", "service_account"])
    return manager


# ---------------------------------------------------------------------------
# SecretEntry model
# ---------------------------------------------------------------------------

class TestSecretEntryModel:

    def test_secret_entry_fields(self, master_key):
        blob = CredentialStore(master_key).encrypt("value")
        now = datetime.now(timezone.utc)
        entry = SecretEntry(
            name="test",
            encrypted_value=blob,
            created_at=now,
            expires_at=now + timedelta(days=30),
            last_accessed=now,
            access_count=0,
            rotated_at=None,
            tags=["api_key"],
            owner="alice",
        )
        assert entry.name == "test"
        assert isinstance(entry.encrypted_value, EncryptedBlob)
        assert entry.created_at == now
        assert entry.expires_at == now + timedelta(days=30)
        assert entry.last_accessed == now
        assert entry.access_count == 0
        assert entry.rotated_at is None
        assert entry.tags == ["api_key"]
        assert entry.owner == "alice"

    def test_secret_entry_defaults(self, master_key):
        blob = CredentialStore(master_key).encrypt("value")
        now = datetime.now(timezone.utc)
        entry = SecretEntry(
            name="minimal",
            encrypted_value=blob,
            created_at=now,
            owner="bob",
        )
        assert entry.expires_at is None
        assert entry.access_count == 0
        assert entry.rotated_at is None
        assert entry.tags == []


# ---------------------------------------------------------------------------
# Store and Retrieve
# ---------------------------------------------------------------------------

class TestStoreAndRetrieve:

    def test_store_and_retrieve(self, manager):
        manager.store("my_secret", "hunter2", owner="alice")
        assert manager.retrieve("my_secret", requester="alice") == "hunter2"

    def test_retrieve_nonexistent_returns_none(self, manager):
        assert manager.retrieve("nope", requester="alice") is None

    def test_store_with_tags(self, manager):
        manager.store("tagged", "val", owner="bob", tags=["api_key", "database"])
        meta = manager.get_metadata("tagged")
        assert set(meta.tags) == {"api_key", "database"}

    def test_store_with_expiration(self, manager):
        manager.store("expiring", "val", owner="alice", expires_in_days=30)
        meta = manager.get_metadata("expiring")
        assert meta.expires_at is not None
        assert meta.expires_at > datetime.now(timezone.utc)

    def test_retrieve_updates_access_tracking(self, manager):
        manager.store("tracked", "val", owner="alice")
        before = datetime.now(timezone.utc)
        manager.retrieve("tracked", requester="bob")
        meta = manager.get_metadata("tracked")
        assert meta.access_count == 1
        assert meta.last_accessed >= before

    def test_multiple_retrieves_increment_count(self, manager):
        manager.store("multi", "val", owner="alice")
        for _ in range(5):
            manager.retrieve("multi", requester="bob")
        meta = manager.get_metadata("multi")
        assert meta.access_count == 5


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class TestDelete:

    def test_owner_can_delete(self, manager):
        manager.store("deleteme", "val", owner="alice")
        manager.delete("deleteme", requester="alice")
        assert manager.retrieve("deleteme", requester="alice") is None

    def test_admin_can_delete(self, manager):
        manager.store("deleteme", "val", owner="alice")
        manager.delete("deleteme", requester="admin")
        assert manager.retrieve("deleteme", requester="alice") is None

    def test_non_owner_cannot_delete(self, manager):
        manager.store("protected", "val", owner="alice")
        with pytest.raises(PermissionError):
            manager.delete("protected", requester="bob")

    def test_delete_nonexistent_raises_keyerror(self, manager):
        with pytest.raises(KeyError):
            manager.delete("nope", requester="admin")


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------

class TestRotation:

    def test_rotate_updates_value(self, manager):
        manager.store("rotatable", "old_val", owner="alice")
        manager.rotate("rotatable", new_value="new_val", requester="alice")
        assert manager.retrieve("rotatable", requester="alice") == "new_val"

    def test_rotate_sets_rotated_at(self, manager):
        manager.store("rotatable", "old_val", owner="alice")
        before = datetime.now(timezone.utc)
        manager.rotate("rotatable", new_value="new_val", requester="alice")
        meta = manager.get_metadata("rotatable")
        assert meta.rotated_at is not None
        assert meta.rotated_at >= before

    def test_rotate_preserves_access_count(self, manager):
        manager.store("rotatable", "old_val", owner="alice")
        manager.retrieve("rotatable", requester="bob")
        manager.retrieve("rotatable", requester="bob")
        manager.rotate("rotatable", new_value="new_val", requester="alice")
        meta = manager.get_metadata("rotatable")
        assert meta.access_count == 2

    def test_rotate_nonexistent_raises_keyerror(self, manager):
        with pytest.raises(KeyError):
            manager.rotate("nope", new_value="val", requester="alice")

    def test_rotation_history(self, manager):
        manager.store("rotatable", "v1", owner="alice")
        manager.rotate("rotatable", new_value="v2", requester="alice")
        manager.rotate("rotatable", new_value="v3", requester="alice")
        history = manager.get_rotation_history("rotatable")
        assert len(history) == 2
        assert history[0] <= history[1]


# ---------------------------------------------------------------------------
# Expiration
# ---------------------------------------------------------------------------

class TestExpiration:

    def test_retrieve_expired_returns_none(self, manager):
        manager.store("expiring", "val", owner="alice", expires_in_days=1)
        # Manually set expiration to the past
        entry = manager._secrets["expiring"]
        entry.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert manager.retrieve("expiring", requester="alice") is None

    def test_cleanup_expired_removes_secrets(self, manager):
        manager.store("fresh", "val1", owner="alice", expires_in_days=30)
        manager.store("stale", "val2", owner="alice", expires_in_days=1)
        # Force stale to be expired
        manager._secrets["stale"].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        removed = manager.cleanup_expired()
        assert removed == ["stale"]
        assert "stale" not in manager._secrets
        assert "fresh" in manager._secrets

    def test_cleanup_expired_empty_manager(self, manager):
        assert manager.cleanup_expired() == []

    def test_no_expiration_never_expires(self, manager):
        manager.store("forever", "val", owner="alice")
        assert manager.retrieve("forever", requester="alice") == "val"


# ---------------------------------------------------------------------------
# List and Metadata
# ---------------------------------------------------------------------------

class TestListAndMetadata:

    def test_list_secrets_all(self, populated_manager):
        secrets = populated_manager.list_secrets()
        names = [s.name for s in secrets]
        assert set(names) == {"db_password", "api_key", "redis_url"}

    def test_list_secrets_never_exposes_values(self, populated_manager):
        secrets = populated_manager.list_secrets()
        for s in secrets:
            assert s.encrypted_value is None

    def test_list_secrets_filter_by_owner(self, populated_manager):
        secrets = populated_manager.list_secrets(owner="alice")
        names = [s.name for s in secrets]
        assert set(names) == {"db_password", "redis_url"}

    def test_list_secrets_filter_by_tag(self, populated_manager):
        secrets = populated_manager.list_secrets(tag="database")
        names = [s.name for s in secrets]
        assert set(names) == {"db_password", "redis_url"}

    def test_list_secrets_filter_owner_and_tag(self, populated_manager):
        secrets = populated_manager.list_secrets(owner="bob", tag="api_key")
        names = [s.name for s in secrets]
        assert names == ["api_key"]

    def test_get_metadata(self, populated_manager):
        meta = populated_manager.get_metadata("api_key")
        assert meta.name == "api_key"
        assert meta.owner == "bob"
        assert meta.encrypted_value is None  # value stripped

    def test_get_metadata_nonexistent_raises(self, manager):
        with pytest.raises(KeyError):
            manager.get_metadata("nope")


# ---------------------------------------------------------------------------
# Access Log
# ---------------------------------------------------------------------------

class TestAccessLog:

    def test_access_log_recorded(self, manager):
        manager.store("logged", "val", owner="alice")
        manager.retrieve("logged", requester="bob")
        manager.retrieve("logged", requester="charlie")
        log = manager.get_access_log("logged")
        assert len(log) == 2
        assert log[0]["requester"] == "bob"
        assert log[1]["requester"] == "charlie"
        assert "timestamp" in log[0]

    def test_access_log_empty(self, manager):
        manager.store("untouched", "val", owner="alice")
        assert manager.get_access_log("untouched") == []

    def test_access_log_nonexistent_raises(self, manager):
        with pytest.raises(KeyError):
            manager.get_access_log("nope")


# ---------------------------------------------------------------------------
# Persistence (save / load)
# ---------------------------------------------------------------------------

class TestPersistence:

    def test_save_and_load(self, master_key, tmp_path):
        path = tmp_path / "secrets.enc"
        mgr1 = SecretsManager(master_key=master_key)
        mgr1.store("persisted", "secret_val", owner="alice", tags=["database"])
        mgr1.retrieve("persisted", requester="bob")
        mgr1.save(path)

        mgr2 = SecretsManager(master_key=master_key)
        mgr2.load(path)
        assert mgr2.retrieve("persisted", requester="alice") == "secret_val"
        meta = mgr2.get_metadata("persisted")
        assert meta.owner == "alice"
        assert meta.tags == ["database"]

    def test_load_nonexistent_is_noop(self, master_key, tmp_path):
        path = tmp_path / "does_not_exist.enc"
        mgr = SecretsManager(master_key=master_key)
        mgr.load(path)  # should not raise
        assert mgr.list_secrets() == []


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_manager_list(self, manager):
        assert manager.list_secrets() == []

    def test_overwrite_existing_secret(self, manager):
        manager.store("key", "v1", owner="alice")
        manager.store("key", "v2", owner="alice")
        assert manager.retrieve("key", requester="alice") == "v2"

    def test_retrieve_expired_does_not_increment_access(self, manager):
        manager.store("expiring", "val", owner="alice", expires_in_days=1)
        manager._secrets["expiring"].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        result = manager.retrieve("expiring", requester="alice")
        assert result is None
        meta_entry = manager._secrets["expiring"]
        assert meta_entry.access_count == 0
