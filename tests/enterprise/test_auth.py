"""Tests for the IntentOS SSO/SAML Integration module (Phase 3B.1)."""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from core.enterprise.auth import (
    AuthProvider,
    AuthToken,
    AuthConfig,
    AuthManager,
    MockSAMLProvider,
    MockOIDCProvider,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def manager():
    return AuthManager()


@pytest.fixture
def sample_config():
    return AuthConfig(
        provider=AuthProvider.SAML,
        issuer_url="https://idp.example.com",
        client_id="client-123",
        client_secret="secret-456",
        redirect_uri="https://app.example.com/callback",
        allowed_domains=["example.com", "corp.example.com"],
    )


@pytest.fixture
def open_config():
    """Config with no domain restrictions."""
    return AuthConfig(
        provider=AuthProvider.OIDC,
        issuer_url="https://idp.example.com",
        client_id="client-123",
        client_secret="secret-456",
        redirect_uri="https://app.example.com/callback",
        allowed_domains=[],
    )


# ---------------------------------------------------------------------------
# 1. AuthProvider enum
# ---------------------------------------------------------------------------

class TestAuthProvider:
    def test_enum_members(self):
        assert AuthProvider.SAML == "saml"
        assert AuthProvider.OIDC == "oidc"
        assert AuthProvider.API_KEY == "api_key"
        assert AuthProvider.LOCAL == "local"

    def test_all_members_present(self):
        names = {m.name for m in AuthProvider}
        assert names == {"SAML", "OIDC", "API_KEY", "LOCAL"}


# ---------------------------------------------------------------------------
# 2-5. AuthToken model
# ---------------------------------------------------------------------------

class TestAuthToken:
    def test_fields(self):
        now = datetime.now(timezone.utc)
        token = AuthToken(
            token_id="t-1",
            user_id="u-1",
            username="alice",
            email="alice@example.com",
            provider=AuthProvider.SAML,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
            roles=["admin"],
            metadata={"group": "eng"},
        )
        assert token.token_id == "t-1"
        assert token.user_id == "u-1"
        assert token.username == "alice"
        assert token.email == "alice@example.com"
        assert token.provider == AuthProvider.SAML
        assert token.issued_at == now
        assert token.roles == ["admin"]
        assert token.metadata == {"group": "eng"}

    def test_is_expired_false(self):
        now = datetime.now(timezone.utc)
        token = AuthToken(
            token_id="t-1", user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            issued_at=now, expires_at=now + timedelta(hours=1),
            roles=[], metadata={},
        )
        assert token.is_expired is False

    def test_is_expired_true(self):
        now = datetime.now(timezone.utc)
        token = AuthToken(
            token_id="t-1", user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            issued_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
            roles=[], metadata={},
        )
        assert token.is_expired is True

    def test_serialization_roundtrip(self):
        now = datetime.now(timezone.utc)
        token = AuthToken(
            token_id="t-1", user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.SAML,
            issued_at=now, expires_at=now + timedelta(hours=1),
            roles=["admin", "viewer"], metadata={"org": "acme"},
        )
        d = token.to_dict()
        restored = AuthToken.from_dict(d)
        assert restored.token_id == token.token_id
        assert restored.user_id == token.user_id
        assert restored.username == token.username
        assert restored.email == token.email
        assert restored.provider == token.provider
        assert restored.roles == token.roles
        assert restored.metadata == token.metadata
        # Datetimes should survive roundtrip
        assert abs((restored.issued_at - token.issued_at).total_seconds()) < 1
        assert abs((restored.expires_at - token.expires_at).total_seconds()) < 1

    def test_auto_generated_token_id(self):
        now = datetime.now(timezone.utc)
        token = AuthToken(
            token_id=None, user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            issued_at=now, expires_at=now + timedelta(hours=1),
            roles=[], metadata={},
        )
        assert token.token_id is not None
        assert len(token.token_id) > 0


# ---------------------------------------------------------------------------
# 6. AuthConfig model
# ---------------------------------------------------------------------------

class TestAuthConfig:
    def test_fields(self):
        cfg = AuthConfig(
            provider=AuthProvider.OIDC,
            issuer_url="https://idp.example.com",
            client_id="cid",
            client_secret="csec",
            redirect_uri="https://app.example.com/cb",
            allowed_domains=["example.com"],
        )
        assert cfg.provider == AuthProvider.OIDC
        assert cfg.issuer_url == "https://idp.example.com"
        assert cfg.client_id == "cid"
        assert cfg.client_secret == "csec"
        assert cfg.redirect_uri == "https://app.example.com/cb"
        assert cfg.allowed_domains == ["example.com"]

    def test_serialization_roundtrip(self):
        cfg = AuthConfig(
            provider=AuthProvider.SAML,
            issuer_url="https://idp.example.com",
            client_id="cid",
            client_secret="csec",
            redirect_uri="https://app.example.com/cb",
            allowed_domains=["example.com", "corp.com"],
        )
        d = cfg.to_dict()
        restored = AuthConfig.from_dict(d)
        assert restored.provider == cfg.provider
        assert restored.issuer_url == cfg.issuer_url
        assert restored.allowed_domains == cfg.allowed_domains


# ---------------------------------------------------------------------------
# 7-13. AuthManager — Token Management
# ---------------------------------------------------------------------------

class TestTokenManagement:
    def test_create_token(self, manager):
        token = manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            roles=["admin"],
        )
        assert isinstance(token, AuthToken)
        assert token.user_id == "u-1"
        assert token.username == "alice"
        assert token.provider == AuthProvider.LOCAL
        assert token.roles == ["admin"]
        assert token.is_expired is False

    def test_create_token_custom_ttl(self, manager):
        token = manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            roles=[], ttl_seconds=60,
        )
        delta = (token.expires_at - token.issued_at).total_seconds()
        assert abs(delta - 60) < 2

    def test_validate_token(self, manager):
        token = manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            roles=[],
        )
        result = manager.validate_token(token.token_id)
        assert result is not None
        assert result.token_id == token.token_id

    def test_validate_unknown_token(self, manager):
        assert manager.validate_token("nonexistent") is None

    def test_validate_expired_token(self, manager):
        token = manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            roles=[], ttl_seconds=0,
        )
        assert manager.validate_token(token.token_id) is None

    def test_revoke_token(self, manager):
        token = manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            roles=[],
        )
        manager.revoke_token(token.token_id)
        assert manager.validate_token(token.token_id) is None

    def test_refresh_token(self, manager):
        token = manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            roles=[], ttl_seconds=60,
        )
        old_expires = token.expires_at
        refreshed = manager.refresh_token(token.token_id, ttl_seconds=7200)
        assert refreshed is not None
        assert refreshed.expires_at > old_expires

    def test_refresh_unknown_token(self, manager):
        assert manager.refresh_token("nonexistent", 3600) is None

    def test_list_active_tokens(self, manager):
        t1 = manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            roles=[], ttl_seconds=3600,
        )
        t2 = manager.create_token(
            user_id="u-2", username="bob",
            email="bob@example.com", provider=AuthProvider.LOCAL,
            roles=[], ttl_seconds=0,
        )
        active = manager.list_active_tokens()
        active_ids = [t.token_id for t in active]
        assert t1.token_id in active_ids
        assert t2.token_id not in active_ids

    def test_cleanup_expired(self, manager):
        manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            roles=[], ttl_seconds=3600,
        )
        manager.create_token(
            user_id="u-2", username="bob",
            email="bob@example.com", provider=AuthProvider.LOCAL,
            roles=[], ttl_seconds=0,
        )
        removed = manager.cleanup_expired()
        assert removed == 1
        assert len(manager.list_active_tokens()) == 1


# ---------------------------------------------------------------------------
# 14-17. Provider Interface
# ---------------------------------------------------------------------------

class TestProviderInterface:
    def test_register_provider(self, manager, sample_config):
        manager.register_provider("corp-saml", sample_config)
        assert manager.get_provider("corp-saml") is not None

    def test_list_providers(self, manager, sample_config, open_config):
        manager.register_provider("saml-1", sample_config)
        manager.register_provider("oidc-1", open_config)
        providers = manager.list_providers()
        assert set(providers.keys()) == {"saml-1", "oidc-1"}

    def test_remove_provider(self, manager, sample_config):
        manager.register_provider("saml-1", sample_config)
        manager.remove_provider("saml-1")
        assert manager.get_provider("saml-1") is None

    def test_get_provider_unknown(self, manager):
        assert manager.get_provider("nonexistent") is None

    def test_duplicate_provider_overwrites(self, manager, sample_config, open_config):
        manager.register_provider("p1", sample_config)
        manager.register_provider("p1", open_config)
        cfg = manager.get_provider("p1")
        assert cfg.provider == AuthProvider.OIDC


# ---------------------------------------------------------------------------
# 18-20. MockSAMLProvider
# ---------------------------------------------------------------------------

class TestMockSAMLProvider:
    def test_authenticate(self, manager):
        saml = MockSAMLProvider(manager)
        saml_response = (
            '<SAMLResponse>'
            '<Assertion>'
            '<Subject>alice</Subject>'
            '<Email>alice@example.com</Email>'
            '<Role>admin</Role>'
            '</Assertion>'
            '</SAMLResponse>'
        )
        token = saml.authenticate(saml_response)
        assert isinstance(token, AuthToken)
        assert token.provider == AuthProvider.SAML
        assert token.username == "alice"

    def test_validate_assertion(self, manager):
        saml = MockSAMLProvider(manager)
        assertion_xml = (
            '<Assertion>'
            '<Subject>bob</Subject>'
            '<Email>bob@example.com</Email>'
            '<Role>viewer</Role>'
            '</Assertion>'
        )
        info = saml.validate_assertion(assertion_xml)
        assert info is not None
        assert info["username"] == "bob"
        assert info["email"] == "bob@example.com"

    def test_invalid_assertion(self, manager):
        saml = MockSAMLProvider(manager)
        result = saml.validate_assertion("<Invalid>garbage</Invalid>")
        assert result is None


# ---------------------------------------------------------------------------
# 21-23. MockOIDCProvider
# ---------------------------------------------------------------------------

class TestMockOIDCProvider:
    def test_authenticate(self, manager):
        oidc = MockOIDCProvider(manager)
        # Register a valid code
        oidc.register_code(
            "code-abc",
            user_id="u-1", username="carol",
            email="carol@example.com", roles=["editor"],
        )
        token = oidc.authenticate("code-abc")
        assert isinstance(token, AuthToken)
        assert token.provider == AuthProvider.OIDC
        assert token.username == "carol"

    def test_get_user_info(self, manager):
        oidc = MockOIDCProvider(manager)
        oidc.register_code(
            "code-abc",
            user_id="u-1", username="carol",
            email="carol@example.com", roles=["editor"],
        )
        token = oidc.authenticate("code-abc")
        info = oidc.get_user_info(token.token_id)
        assert info is not None
        assert info["username"] == "carol"
        assert info["email"] == "carol@example.com"

    def test_invalid_code(self, manager):
        oidc = MockOIDCProvider(manager)
        assert oidc.authenticate("bad-code") is None


# ---------------------------------------------------------------------------
# 24-26. API Key Auth
# ---------------------------------------------------------------------------

class TestAPIKeyAuth:
    def test_register_api_key(self, manager):
        key = manager.register_api_key(user_id="u-1", username="alice")
        assert isinstance(key, str)
        assert len(key) > 16

    def test_authenticate_api_key(self, manager):
        key = manager.register_api_key(user_id="u-1", username="alice")
        token = manager.authenticate_api_key(key)
        assert isinstance(token, AuthToken)
        assert token.provider == AuthProvider.API_KEY
        assert token.user_id == "u-1"

    def test_authenticate_invalid_api_key(self, manager):
        assert manager.authenticate_api_key("bad-key") is None

    def test_revoke_api_key(self, manager):
        key = manager.register_api_key(user_id="u-1", username="alice")
        manager.revoke_api_key(key)
        assert manager.authenticate_api_key(key) is None


# ---------------------------------------------------------------------------
# 27-28. Domain Restriction
# ---------------------------------------------------------------------------

class TestDomainRestriction:
    def test_reject_email_not_in_allowed_domains(self, manager, sample_config):
        manager.register_provider("corp", sample_config)
        token = manager.create_token(
            user_id="u-1", username="eve",
            email="eve@evil.com", provider=AuthProvider.SAML,
            roles=[], allowed_domains=["example.com", "corp.example.com"],
        )
        assert token is None

    def test_accept_email_in_allowed_domains(self, manager, sample_config):
        manager.register_provider("corp", sample_config)
        token = manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.SAML,
            roles=[], allowed_domains=["example.com"],
        )
        assert token is not None

    def test_empty_allowed_domains_accepts_all(self, manager):
        token = manager.create_token(
            user_id="u-1", username="anyone",
            email="anyone@anywhere.org", provider=AuthProvider.LOCAL,
            roles=[], allowed_domains=[],
        )
        assert token is not None


# ---------------------------------------------------------------------------
# 29-30. Session Management
# ---------------------------------------------------------------------------

class TestSessionManagement:
    def test_get_user_sessions(self, manager):
        manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            roles=[],
        )
        manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            roles=[],
        )
        manager.create_token(
            user_id="u-2", username="bob",
            email="bob@example.com", provider=AuthProvider.LOCAL,
            roles=[],
        )
        sessions = manager.get_user_sessions("u-1")
        assert len(sessions) == 2
        assert all(s.user_id == "u-1" for s in sessions)

    def test_revoke_all_user_sessions(self, manager):
        manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            roles=[],
        )
        manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            roles=[],
        )
        t3 = manager.create_token(
            user_id="u-2", username="bob",
            email="bob@example.com", provider=AuthProvider.LOCAL,
            roles=[],
        )
        manager.revoke_all_user_sessions("u-1")
        assert len(manager.get_user_sessions("u-1")) == 0
        assert manager.validate_token(t3.token_id) is not None


# ---------------------------------------------------------------------------
# 31. Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_and_load(self, manager, sample_config):
        manager.register_provider("corp-saml", sample_config)
        manager.register_api_key(user_id="u-1", username="alice")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            manager.save(path)

            new_manager = AuthManager()
            new_manager.load(path)

            assert new_manager.get_provider("corp-saml") is not None
            cfg = new_manager.get_provider("corp-saml")
            assert cfg.provider == AuthProvider.SAML
            assert cfg.issuer_url == sample_config.issuer_url
            # API keys should survive
            assert len(new_manager._api_keys) == 1
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# 32-33. Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_zero_ttl_immediately_expired(self, manager):
        token = manager.create_token(
            user_id="u-1", username="alice",
            email="alice@example.com", provider=AuthProvider.LOCAL,
            roles=[], ttl_seconds=0,
        )
        assert token is not None
        assert token.is_expired is True
        assert manager.validate_token(token.token_id) is None

    def test_duplicate_provider_name_overwrites(self, manager, sample_config, open_config):
        manager.register_provider("p1", sample_config)
        manager.register_provider("p1", open_config)
        cfg = manager.get_provider("p1")
        assert cfg.provider == AuthProvider.OIDC
