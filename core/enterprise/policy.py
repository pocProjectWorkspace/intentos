"""Enterprise Policy Engine.

Loads a signed policy.json from the IntentOS base directory, validates its
HMAC-SHA256 signature, and exposes check_* helpers consumed by the kernel,
inference router, and agent scheduler.

When no policy file exists the engine degrades gracefully — every check
returns True so consumer/SMB installations are unaffected.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PolicyViolationError(Exception):
    """Raised when an operation violates an enterprise policy constraint."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _canonical_payload(data: dict) -> bytes:
    """Return the deterministic JSON representation used for signing."""
    filtered = {k: v for k, v in data.items() if k != "signature"}
    return json.dumps(filtered, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _verify_signature(payload: bytes, key: bytes, expected_hex: str) -> bool:
    computed = hmac.new(key, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, expected_hex)


def _resolve(p: str) -> str:
    """Expand ~ and resolve to an absolute real path."""
    return os.path.realpath(os.path.expanduser(p))


# ---------------------------------------------------------------------------
# PolicyEngine
# ---------------------------------------------------------------------------

class PolicyEngine:
    """Enterprise policy enforcement layer.

    Parameters
    ----------
    base_path:
        Root of the IntentOS data directory (typically ``~/.intentos``).
    """

    def __init__(self, base_path: Path) -> None:
        self._base = base_path
        self._policy: Optional[Dict[str, Any]] = None
        self._managed: bool = False
        self._loaded_at: float = 0.0
        self._load()

    # -- lifecycle -----------------------------------------------------------

    def _load(self) -> None:
        policy_file = self._base / "policy.json"
        key_file = self._base / "enterprise.key"

        if not policy_file.exists():
            logger.debug("No enterprise policy found — running unmanaged")
            self._policy = None
            self._managed = False
            return

        try:
            raw = policy_file.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception:
            logger.warning("Corrupt policy.json — ignoring enterprise policy")
            self._policy = None
            self._managed = False
            return

        if not key_file.exists():
            logger.warning("enterprise.key missing — policy signature cannot be verified")
            self._policy = None
            self._managed = False
            return

        try:
            key = key_file.read_bytes().strip()
        except Exception:
            logger.warning("Unable to read enterprise.key")
            self._policy = None
            self._managed = False
            return

        signature = data.get("signature", "")
        if not _verify_signature(_canonical_payload(data), key, signature):
            logger.warning("Policy signature verification failed — ignoring policy")
            self._policy = None
            self._managed = False
            return

        self._policy = data
        self._managed = True
        self._loaded_at = time.monotonic()
        logger.info("Enterprise policy loaded (org=%s)", data.get("org_id", "unknown"))

    def reload(self) -> None:
        """Re-read the policy from disk."""
        self._load()

    # -- properties ----------------------------------------------------------

    @property
    def is_managed(self) -> bool:
        """True when a valid, signed enterprise policy is active."""
        return self._managed

    # -- checks --------------------------------------------------------------

    def check_privacy_mode(self, requested_mode: str) -> bool:
        """Return False if the policy locks privacy mode and *requested_mode* differs."""
        if not self._managed or self._policy is None:
            return True
        if not self._policy.get("privacy_mode_locked", False):
            return True
        return requested_mode == self._policy.get("privacy_mode")

    def check_agent(self, agent_name: str) -> bool:
        """Return False if the agent is blocked or not in the allowed list."""
        if not self._managed or self._policy is None:
            return True
        blocked: List[str] = self._policy.get("blocked_agents", [])
        if agent_name in blocked:
            return False
        allowed: List[str] = self._policy.get("allowed_agents", [])
        if allowed and agent_name not in allowed:
            return False
        return True

    def check_model(self, model_name: str) -> bool:
        """Return False if model is pinned and *model_name* is not in the allowed list."""
        if not self._managed or self._policy is None:
            return True
        if not self._policy.get("model_pinned", False):
            return True
        allowed: List[str] = self._policy.get("allowed_models", [])
        return model_name in allowed

    def check_provider(self, provider_name: str) -> bool:
        """Return False if *provider_name* is not in the allowed cloud providers."""
        if not self._managed or self._policy is None:
            return True
        allowed: List[str] = self._policy.get("allowed_cloud_providers", [])
        if not allowed:
            return True
        return provider_name in allowed

    def check_path(self, path: str) -> bool:
        """Return False if *path* violates the policy's path restrictions."""
        if not self._managed or self._policy is None:
            return True
        restrictions = self._policy.get("path_restrictions", {})
        real = _resolve(path)

        denied: List[str] = restrictions.get("denied_paths", [])
        for dp in denied:
            resolved = _resolve(dp)
            if real == resolved or real.startswith(resolved + os.sep):
                return False

        allowed: List[str] = restrictions.get("allowed_paths", [])
        if allowed:
            for ap in allowed:
                resolved = _resolve(ap)
                if real == resolved or real.startswith(resolved + os.sep):
                    return True
            return False

        return True

    def check_spending(self, current_daily: float, current_monthly: float) -> bool:
        """Return False if either spending limit has been exceeded."""
        if not self._managed or self._policy is None:
            return True
        limits = self._policy.get("spending", {})
        daily_limit = limits.get("daily_limit_usd")
        monthly_limit = limits.get("monthly_limit_usd")
        if daily_limit is not None and current_daily >= daily_limit:
            return False
        if monthly_limit is not None and current_monthly >= monthly_limit:
            return False
        return True

    # -- accessors -----------------------------------------------------------

    def get_telemetry_config(self) -> Optional[Dict[str, Any]]:
        """Return the telemetry section or None if unmanaged."""
        if not self._managed or self._policy is None:
            return None
        return self._policy.get("telemetry")

    def get_spending_limits(self) -> Dict[str, Any]:
        """Return the spending limits dict, or empty dict if unmanaged."""
        if not self._managed or self._policy is None:
            return {}
        return dict(self._policy.get("spending", {}))

    def get_compliance_status(self) -> Dict[str, Any]:
        """Return a summary suitable for the /status API endpoint."""
        if not self._managed or self._policy is None:
            return {"managed": False}
        return {
            "managed": True,
            "org_id": self._policy.get("org_id"),
            "device_id": self._policy.get("device_id"),
            "privacy_mode": self._policy.get("privacy_mode"),
            "privacy_mode_locked": self._policy.get("privacy_mode_locked", False),
            "model_pinned": self._policy.get("model_pinned", False),
            "allowed_agents": self._policy.get("allowed_agents", []),
            "blocked_agents": self._policy.get("blocked_agents", []),
            "spending": self._policy.get("spending", {}),
            "policy_version": self._policy.get("version"),
            "issued_at": self._policy.get("issued_at"),
        }
