"""Tests for core.enterprise.policy — Enterprise Policy Engine."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.enterprise.policy import PolicyEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_KEY = b"super-secret-enterprise-key-256bit"


def make_signed_policy(policy_data: dict, key: bytes) -> str:
    """Create a JSON string with a valid HMAC-SHA256 signature."""
    filtered = {k: v for k, v in policy_data.items() if k != "signature"}
    payload = json.dumps(filtered, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(key, payload, hashlib.sha256).hexdigest()
    policy_data["signature"] = sig
    return json.dumps(policy_data, indent=2)


def _base_policy() -> dict:
    """Return a realistic enterprise policy dict (unsigned)."""
    return {
        "version": "1.0.0",
        "org_id": "acme-corp",
        "device_id": "laptop-042",
        "issued_at": "2026-04-09T00:00:00Z",
        "privacy_mode": "local_only",
        "privacy_mode_locked": True,
        "blocked_agents": ["browser_agent"],
        "allowed_agents": [],
        "model_pinned": True,
        "allowed_models": ["llama-3.1-8b", "phi-3-mini"],
        "allowed_cloud_providers": ["anthropic", "azure"],
        "path_restrictions": {
            "denied_paths": ["/etc/shadow", "/var/secrets"],
            "allowed_paths": ["/home/user/workspace", "/tmp"],
        },
        "spending": {
            "daily_limit_usd": 10.0,
            "monthly_limit_usd": 200.0,
        },
        "telemetry": {
            "enabled": True,
            "endpoint": "https://telemetry.acme.example/v1",
            "interval_seconds": 300,
        },
    }


def _write_policy(base: Path, policy_data: dict, key: bytes = TEST_KEY) -> None:
    """Write a signed policy.json and enterprise.key into *base*."""
    base.mkdir(parents=True, exist_ok=True)
    (base / "policy.json").write_text(make_signed_policy(policy_data, key), encoding="utf-8")
    (base / "enterprise.key").write_bytes(key)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base(tmp_path):
    """Return a temporary base_path that acts like ~/.intentos."""
    return tmp_path / ".intentos"


# ===========================================================================
# Tests
# ===========================================================================


def test_no_policy_file(base):
    """1: Without a policy file the engine is unmanaged and all checks pass."""
    base.mkdir(parents=True, exist_ok=True)
    engine = PolicyEngine(base)

    assert engine.is_managed is False
    assert engine.check_privacy_mode("performance") is True
    assert engine.check_agent("anything") is True
    assert engine.check_model("any-model") is True
    assert engine.check_provider("any-provider") is True
    assert engine.check_path("/etc/shadow") is True
    assert engine.check_spending(9999, 9999) is True
    assert engine.get_telemetry_config() is None
    assert engine.get_spending_limits() == {}
    assert engine.get_compliance_status() == {"managed": False}


def test_valid_signed_policy(base):
    """2: A correctly signed policy makes the engine managed and enforces checks."""
    policy = _base_policy()
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    assert engine.is_managed is True
    # locked to local_only — wrong mode blocked
    assert engine.check_privacy_mode("performance") is False
    assert engine.check_privacy_mode("local_only") is True
    # browser_agent is blocked
    assert engine.check_agent("browser_agent") is False
    # model must be in allowed list
    assert engine.check_model("gpt-4o") is False
    assert engine.check_model("llama-3.1-8b") is True


def test_invalid_signature(base):
    """3: A tampered policy is rejected — engine stays unmanaged."""
    policy = _base_policy()
    _write_policy(base, policy)
    # Tamper with the file after signing
    path = base / "policy.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["org_id"] = "evil-corp"
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    engine = PolicyEngine(base)
    assert engine.is_managed is False
    assert engine.check_agent("browser_agent") is True  # unmanaged → allow


def test_missing_key_file(base):
    """4: Policy present but enterprise.key missing → unmanaged."""
    base.mkdir(parents=True, exist_ok=True)
    policy = _base_policy()
    # Write only the policy, not the key
    signed = make_signed_policy(policy, TEST_KEY)
    (base / "policy.json").write_text(signed, encoding="utf-8")

    engine = PolicyEngine(base)
    assert engine.is_managed is False


def test_corrupt_json(base):
    """5: Corrupt policy.json → unmanaged."""
    base.mkdir(parents=True, exist_ok=True)
    (base / "policy.json").write_text("{not valid json!!!", encoding="utf-8")
    (base / "enterprise.key").write_bytes(TEST_KEY)

    engine = PolicyEngine(base)
    assert engine.is_managed is False


def test_check_privacy_mode_locked(base):
    """6: When privacy_mode_locked is True, only the policy mode is allowed."""
    policy = _base_policy()
    policy["privacy_mode"] = "smart_routing"
    policy["privacy_mode_locked"] = True
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    assert engine.check_privacy_mode("smart_routing") is True
    assert engine.check_privacy_mode("local_only") is False
    assert engine.check_privacy_mode("performance") is False


def test_check_privacy_mode_unlocked(base):
    """7: When privacy_mode_locked is False, any mode is allowed."""
    policy = _base_policy()
    policy["privacy_mode"] = "local_only"
    policy["privacy_mode_locked"] = False
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    assert engine.check_privacy_mode("local_only") is True
    assert engine.check_privacy_mode("performance") is True
    assert engine.check_privacy_mode("smart_routing") is True


def test_check_agent_blocked(base):
    """8: Agents in blocked_agents list are rejected."""
    policy = _base_policy()
    policy["blocked_agents"] = ["browser_agent", "system_agent"]
    policy["allowed_agents"] = []
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    assert engine.check_agent("browser_agent") is False
    assert engine.check_agent("system_agent") is False
    assert engine.check_agent("file_agent") is True


def test_check_agent_allowed_list(base):
    """9: When allowed_agents is non-empty, only listed agents pass."""
    policy = _base_policy()
    policy["blocked_agents"] = []
    policy["allowed_agents"] = ["file_agent", "document_agent"]
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    assert engine.check_agent("file_agent") is True
    assert engine.check_agent("document_agent") is True
    assert engine.check_agent("browser_agent") is False
    assert engine.check_agent("system_agent") is False


def test_check_model_pinned(base):
    """10: When model_pinned is True, only allowed_models pass."""
    policy = _base_policy()
    policy["model_pinned"] = True
    policy["allowed_models"] = ["llama-3.1-8b"]
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    assert engine.check_model("llama-3.1-8b") is True
    assert engine.check_model("gpt-4o") is False
    assert engine.check_model("mistral-7b") is False


def test_check_model_not_pinned(base):
    """11: When model_pinned is False, any model is allowed."""
    policy = _base_policy()
    policy["model_pinned"] = False
    policy["allowed_models"] = ["llama-3.1-8b"]
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    assert engine.check_model("llama-3.1-8b") is True
    assert engine.check_model("gpt-4o") is True
    assert engine.check_model("anything") is True


def test_check_provider(base):
    """12: Only listed cloud providers are allowed when list is non-empty."""
    policy = _base_policy()
    policy["allowed_cloud_providers"] = ["anthropic"]
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    assert engine.check_provider("anthropic") is True
    assert engine.check_provider("openai") is False
    assert engine.check_provider("azure") is False


def test_check_path_denied(base):
    """13: Paths in denied_paths are blocked."""
    policy = _base_policy()
    policy["path_restrictions"] = {
        "denied_paths": ["/etc/shadow", "/var/secrets"],
        "allowed_paths": [],
    }
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    assert engine.check_path("/etc/shadow") is False
    assert engine.check_path("/var/secrets/api.key") is False
    assert engine.check_path("/home/user/docs") is True


def test_check_path_allowed(base):
    """14: When allowed_paths is non-empty, only listed paths (and children) pass."""
    policy = _base_policy()
    policy["path_restrictions"] = {
        "denied_paths": [],
        "allowed_paths": ["/home/user/workspace"],
    }
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    assert engine.check_path("/home/user/workspace") is True
    assert engine.check_path("/home/user/workspace/src/main.py") is True
    assert engine.check_path("/home/user/desktop/secret.txt") is False


def test_check_spending_within_limits(base):
    """15: Spending within both limits passes."""
    policy = _base_policy()
    policy["spending"] = {"daily_limit_usd": 10.0, "monthly_limit_usd": 200.0}
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    assert engine.check_spending(5.0, 100.0) is True
    assert engine.check_spending(0.0, 0.0) is True
    assert engine.check_spending(9.99, 199.99) is True


def test_check_spending_exceeded(base):
    """16: Exceeding either limit fails."""
    policy = _base_policy()
    policy["spending"] = {"daily_limit_usd": 10.0, "monthly_limit_usd": 200.0}
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    assert engine.check_spending(10.0, 50.0) is False   # daily hit
    assert engine.check_spending(5.0, 200.0) is False    # monthly hit
    assert engine.check_spending(10.0, 200.0) is False   # both hit


def test_get_telemetry_config(base):
    """17: Telemetry config is returned when managed."""
    policy = _base_policy()
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    telem = engine.get_telemetry_config()
    assert telem is not None
    assert telem["enabled"] is True
    assert "endpoint" in telem


def test_get_compliance_status(base):
    """18: Compliance status returns a full summary when managed."""
    policy = _base_policy()
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    status = engine.get_compliance_status()
    assert status["managed"] is True
    assert status["org_id"] == "acme-corp"
    assert status["device_id"] == "laptop-042"
    assert status["privacy_mode"] == "local_only"
    assert status["privacy_mode_locked"] is True
    assert status["model_pinned"] is True
    assert status["policy_version"] == "1.0.0"
    assert "spending" in status


def test_reload(base):
    """19: After reload, changes to the policy take effect."""
    policy = _base_policy()
    policy["blocked_agents"] = []
    _write_policy(base, policy)
    engine = PolicyEngine(base)

    assert engine.check_agent("browser_agent") is True

    # Update policy to block browser_agent
    policy["blocked_agents"] = ["browser_agent"]
    _write_policy(base, policy)
    engine.reload()

    assert engine.check_agent("browser_agent") is False
