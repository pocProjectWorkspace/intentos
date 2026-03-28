"""
Tests for IntentOS Credential Provider.

Tests the resolution chain: encrypted store → env var → prompt.
Tests .env migration to encrypted storage.
Tests kernel integration via create_client().
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def provider(tmp_path):
    """CredentialProvider using temp paths (no real keychain)."""
    from core.security.credential_provider import CredentialProvider

    return CredentialProvider(
        creds_path=tmp_path / "creds.enc",
        keychain_fallback_path=tmp_path / "master_key.enc",
        use_os_keychain=False,
    )


# --- Resolution Order Tests ---


class TestResolutionOrder:
    """Credentials resolve: encrypted store → env var → None."""

    def test_returns_none_when_nothing_set(self, provider):
        result = provider.get("NONEXISTENT_KEY")
        assert result is None

    def test_returns_from_store(self, provider):
        provider.store("MY_KEY", "stored-value")
        result = provider.get("MY_KEY")
        assert result == "stored-value"

    def test_returns_from_env_var(self, provider):
        with patch.dict(os.environ, {"MY_KEY": "env-value"}):
            result = provider.get("MY_KEY")
            assert result == "env-value"

    def test_store_takes_priority_over_env(self, provider):
        provider.store("MY_KEY", "store-wins")
        with patch.dict(os.environ, {"MY_KEY": "env-loses"}):
            result = provider.get("MY_KEY")
            assert result == "store-wins"

    def test_has_returns_true_when_stored(self, provider):
        provider.store("EXISTS", "yes")
        assert provider.has("EXISTS") is True

    def test_has_returns_true_from_env(self, provider):
        with patch.dict(os.environ, {"ENV_KEY": "yes"}):
            assert provider.has("ENV_KEY") is True

    def test_has_returns_false_when_missing(self, provider):
        assert provider.has("NOPE") is False


# --- Store / Delete / List Tests ---


class TestStoreOperations:
    """Test credential CRUD operations."""

    def test_store_and_retrieve(self, provider):
        provider.store("api_key", "sk-test-123")
        assert provider.get("api_key") == "sk-test-123"

    def test_overwrite(self, provider):
        provider.store("key", "old")
        provider.store("key", "new")
        assert provider.get("key") == "new"

    def test_delete(self, provider):
        provider.store("key", "val")
        provider.delete("key")
        assert provider.get("key") is None

    def test_list_stored(self, provider):
        provider.store("a", "1")
        provider.store("b", "2")
        names = provider.list_stored()
        assert "a" in names
        assert "b" in names

    def test_persistence_across_instances(self, tmp_path):
        from core.security.credential_provider import CredentialProvider

        creds_path = tmp_path / "creds.enc"
        key_path = tmp_path / "master_key.enc"

        # Instance 1: store a credential
        p1 = CredentialProvider(
            creds_path=creds_path,
            keychain_fallback_path=key_path,
            use_os_keychain=False,
        )
        p1.store("api_key", "sk-persist-test")

        # Instance 2: retrieve from same files
        p2 = CredentialProvider(
            creds_path=creds_path,
            keychain_fallback_path=key_path,
            use_os_keychain=False,
        )
        assert p2.get("api_key") == "sk-persist-test"


# --- .env Migration Tests ---


class TestEnvMigration:
    """Test automatic migration of .env credentials to encrypted store."""

    def test_get_api_key_from_store(self, provider):
        """If key is in store, return it directly."""
        from core.security.credential_provider import get_api_key

        provider.store("ANTHROPIC_API_KEY", "sk-from-store")
        result = get_api_key(provider)
        assert result == "sk-from-store"

    def test_get_api_key_from_env(self, provider):
        """If key is in env, migrate to store and return it."""
        from core.security.credential_provider import get_api_key

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-from-env"}):
            # Patch load_dotenv to avoid touching real .env
            with patch("core.security.credential_provider.Path") as mock_path:
                # Make .env check return False so it skips the .env file path
                result = get_api_key(provider)
                # Should find it from os.environ via provider.get()
                assert result == "sk-from-env"


# --- Kernel Integration Tests ---


class TestKernelIntegration:
    """Test that the kernel's create_client uses the credential provider."""

    def test_create_client_with_provider(self, provider):
        """create_client should use the credential provider."""
        provider.store("ANTHROPIC_API_KEY", "sk-test-key")

        # We can't actually create a valid client with a fake key,
        # but we can verify create_client doesn't crash and uses our key
        from core.kernel import create_client

        with patch("core.kernel.anthropic.Anthropic") as mock_anthropic:
            create_client(provider)
            mock_anthropic.assert_called_once_with(api_key="sk-test-key")
