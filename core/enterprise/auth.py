"""IntentOS SSO/SAML Integration module (Phase 3B.1).

Provides enterprise identity integration for fleet-managed deployments,
including SAML, OIDC, API key, and local authentication providers.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AuthProvider(str, Enum):
    SAML = "saml"
    OIDC = "oidc"
    API_KEY = "api_key"
    LOCAL = "local"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class AuthToken:
    user_id: str
    username: str
    email: str
    provider: AuthProvider
    issued_at: datetime
    expires_at: datetime
    roles: List[str]
    metadata: Dict[str, Any]
    token_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.token_id is None:
            self.token_id = str(uuid4())

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "provider": self.provider.value,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "roles": list(self.roles),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AuthToken:
        return cls(
            token_id=data["token_id"],
            user_id=data["user_id"],
            username=data["username"],
            email=data["email"],
            provider=AuthProvider(data["provider"]),
            issued_at=datetime.fromisoformat(data["issued_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            roles=data["roles"],
            metadata=data["metadata"],
        )


@dataclass
class AuthConfig:
    provider: AuthProvider
    issuer_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    allowed_domains: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider.value,
            "issuer_url": self.issuer_url,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "allowed_domains": list(self.allowed_domains),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AuthConfig:
        return cls(
            provider=AuthProvider(data["provider"]),
            issuer_url=data["issuer_url"],
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            redirect_uri=data["redirect_uri"],
            allowed_domains=data.get("allowed_domains", []),
        )


# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------

class AuthManager:
    """Central authentication manager for IntentOS enterprise deployments."""

    def __init__(self) -> None:
        self._tokens: Dict[str, AuthToken] = {}
        self._providers: Dict[str, AuthConfig] = {}
        self._api_keys: Dict[str, Dict[str, str]] = {}

    # -- Token Management ---------------------------------------------------

    def create_token(
        self,
        user_id: str,
        username: str,
        email: str,
        provider: AuthProvider,
        roles: List[str],
        ttl_seconds: int = 3600,
        allowed_domains: Optional[List[str]] = None,
    ) -> Optional[AuthToken]:
        # Domain check
        if allowed_domains:
            domain = email.rsplit("@", 1)[-1]
            if domain not in allowed_domains:
                return None

        now = datetime.now(timezone.utc)
        token = AuthToken(
            user_id=user_id,
            username=username,
            email=email,
            provider=provider,
            issued_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            roles=roles,
            metadata={},
        )
        self._tokens[token.token_id] = token
        return token

    def validate_token(self, token_id: str) -> Optional[AuthToken]:
        token = self._tokens.get(token_id)
        if token is None or token.is_expired:
            return None
        return token

    def revoke_token(self, token_id: str) -> None:
        self._tokens.pop(token_id, None)

    def refresh_token(
        self, token_id: str, ttl_seconds: int = 3600
    ) -> Optional[AuthToken]:
        token = self._tokens.get(token_id)
        if token is None:
            return None
        token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        return token

    def list_active_tokens(self) -> List[AuthToken]:
        return [t for t in self._tokens.values() if not t.is_expired]

    def cleanup_expired(self) -> int:
        expired_ids = [
            tid for tid, t in self._tokens.items() if t.is_expired
        ]
        for tid in expired_ids:
            del self._tokens[tid]
        return len(expired_ids)

    # -- Provider Interface -------------------------------------------------

    def register_provider(self, name: str, config: AuthConfig) -> None:
        self._providers[name] = config

    def list_providers(self) -> Dict[str, AuthConfig]:
        return dict(self._providers)

    def remove_provider(self, name: str) -> None:
        self._providers.pop(name, None)

    def get_provider(self, name: str) -> Optional[AuthConfig]:
        return self._providers.get(name)

    # -- API Key Auth -------------------------------------------------------

    def register_api_key(self, user_id: str, username: str) -> str:
        key = secrets.token_urlsafe(32)
        self._api_keys[key] = {"user_id": user_id, "username": username}
        return key

    def authenticate_api_key(self, api_key: str) -> Optional[AuthToken]:
        info = self._api_keys.get(api_key)
        if info is None:
            return None
        return self.create_token(
            user_id=info["user_id"],
            username=info["username"],
            email=f"{info['username']}@api-key",
            provider=AuthProvider.API_KEY,
            roles=[],
        )

    def revoke_api_key(self, api_key: str) -> None:
        self._api_keys.pop(api_key, None)

    # -- Session Management -------------------------------------------------

    def get_user_sessions(self, user_id: str) -> List[AuthToken]:
        return [
            t for t in self._tokens.values()
            if t.user_id == user_id and not t.is_expired
        ]

    def revoke_all_user_sessions(self, user_id: str) -> None:
        to_remove = [
            tid for tid, t in self._tokens.items() if t.user_id == user_id
        ]
        for tid in to_remove:
            del self._tokens[tid]

    # -- Persistence --------------------------------------------------------

    def save(self, path: str) -> None:
        data = {
            "providers": {
                name: cfg.to_dict() for name, cfg in self._providers.items()
            },
            "api_keys": dict(self._api_keys),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        with open(path, "r") as f:
            data = json.load(f)
        self._providers = {
            name: AuthConfig.from_dict(cfg)
            for name, cfg in data.get("providers", {}).items()
        }
        self._api_keys = data.get("api_keys", {})


# ---------------------------------------------------------------------------
# Mock Providers
# ---------------------------------------------------------------------------

class MockSAMLProvider:
    """Simulates SAML authentication with simple XML-like assertion parsing."""

    def __init__(self, manager: AuthManager) -> None:
        self._manager = manager

    def authenticate(self, saml_response: str) -> Optional[AuthToken]:
        info = self.validate_assertion(
            self._extract_assertion(saml_response)
        )
        if info is None:
            return None
        return self._manager.create_token(
            user_id=f"saml-{info['username']}",
            username=info["username"],
            email=info["email"],
            provider=AuthProvider.SAML,
            roles=info.get("roles", []),
        )

    def validate_assertion(self, assertion_xml: str) -> Optional[Dict[str, Any]]:
        subject = self._extract_tag(assertion_xml, "Subject")
        email = self._extract_tag(assertion_xml, "Email")
        if not subject or not email:
            return None
        role = self._extract_tag(assertion_xml, "Role")
        return {
            "username": subject,
            "email": email,
            "roles": [role] if role else [],
        }

    @staticmethod
    def _extract_assertion(saml_response: str) -> str:
        m = re.search(r"<Assertion>.*</Assertion>", saml_response, re.DOTALL)
        return m.group(0) if m else saml_response

    @staticmethod
    def _extract_tag(xml: str, tag: str) -> Optional[str]:
        m = re.search(rf"<{tag}>(.*?)</{tag}>", xml)
        return m.group(1) if m else None


class MockOIDCProvider:
    """Simulates OIDC authorization code flow."""

    def __init__(self, manager: AuthManager) -> None:
        self._manager = manager
        self._codes: Dict[str, Dict[str, Any]] = {}

    def register_code(
        self,
        code: str,
        user_id: str,
        username: str,
        email: str,
        roles: Optional[List[str]] = None,
    ) -> None:
        self._codes[code] = {
            "user_id": user_id,
            "username": username,
            "email": email,
            "roles": roles or [],
        }

    def authenticate(self, authorization_code: str) -> Optional[AuthToken]:
        info = self._codes.pop(authorization_code, None)
        if info is None:
            return None
        return self._manager.create_token(
            user_id=info["user_id"],
            username=info["username"],
            email=info["email"],
            provider=AuthProvider.OIDC,
            roles=info["roles"],
        )

    def get_user_info(self, token_id: str) -> Optional[Dict[str, Any]]:
        token = self._manager.validate_token(token_id)
        if token is None:
            return None
        return {
            "user_id": token.user_id,
            "username": token.username,
            "email": token.email,
            "roles": token.roles,
        }
