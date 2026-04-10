#!/usr/bin/env python3
"""Enterprise demo setup script.

Generates a signed enterprise policy and sends fake device heartbeats to the
IntentOS Console so you can demo the full enterprise flow end-to-end.

Usage:
    python scripts/enterprise_demo.py              # does everything
    python scripts/enterprise_demo.py --setup-policy
    python scripts/enterprise_demo.py --send-heartbeats
    python scripts/enterprise_demo.py --all
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

INTENTOS_DIR = Path.home() / ".intentos"
POLICY_FILE = INTENTOS_DIR / "policy.json"
KEY_FILE = INTENTOS_DIR / "enterprise.key"
CONSOLE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Policy generation
# ---------------------------------------------------------------------------

def _sign_policy(policy: dict, key: bytes) -> str:
    """Produce an HMAC-SHA256 hex signature matching core/enterprise/policy.py."""
    filtered = {k: v for k, v in policy.items() if k != "signature"}
    payload = json.dumps(filtered, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def setup_policy() -> None:
    """Create ~/.intentos/policy.json and ~/.intentos/enterprise.key."""
    INTENTOS_DIR.mkdir(parents=True, exist_ok=True)

    key = secrets.token_hex(32).encode("utf-8")

    policy: dict = {
        "version": "1.0.0",
        "org_id": "demo-enterprise-corp",
        "device_id": "demo-device-001",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "privacy_mode": "smart_routing",
        "privacy_mode_locked": True,
        "allowed_agents": ["file_agent", "document_agent", "system_agent"],
        "blocked_agents": ["browser_agent"],
        "model_pinned": True,
        "allowed_models": ["claude-sonnet-4-20250514"],
        "allowed_cloud_providers": ["anthropic"],
        "spending": {
            "daily_limit_usd": 10.0,
            "monthly_limit_usd": 100.0,
        },
        "telemetry": {
            "enabled": True,
            "endpoint": f"{CONSOLE_URL}/api/v1/telemetry/heartbeat",
            "interval_seconds": 60,
        },
        "path_restrictions": {
            "denied_paths": ["/etc", "/var"],
        },
    }

    policy["signature"] = _sign_policy(policy, key)

    KEY_FILE.write_bytes(key)
    KEY_FILE.chmod(0o600)

    POLICY_FILE.write_text(
        json.dumps(policy, indent=2) + "\n", encoding="utf-8"
    )

    print("  Created", POLICY_FILE)
    print("  Created", KEY_FILE)
    print("  Privacy mode locked to: smart_routing")
    print("  Allowed agents:", ", ".join(policy["allowed_agents"]))
    print("  Pinned model:", policy["allowed_models"][0])
    print(f"  Spending: ${policy['spending']['daily_limit_usd']}/day, "
          f"${policy['spending']['monthly_limit_usd']}/month")


# ---------------------------------------------------------------------------
# Heartbeat simulation
# ---------------------------------------------------------------------------

DEVICES = [
    {
        "name": "alice-macbook",
        "token": "demo-token-alice-001",
        "os_name": "macOS",
        "os_version": "15.4",
        "intentos_version": "0.9.0",
        "inference_usage": [
            {"model": "claude-sonnet-4-20250514", "provider": "anthropic",
             "calls": 47, "input_tokens": 128400, "output_tokens": 34200, "cost_usd": 2.14},
            {"model": "llama3.1:8b", "provider": "ollama",
             "calls": 12, "input_tokens": 8600, "output_tokens": 3100, "cost_usd": 0.0},
        ],
        "compliance_violations": [],
    },
    {
        "name": "bob-thinkpad",
        "token": "demo-token-bob-002",
        "os_name": "Ubuntu",
        "os_version": "24.04",
        "intentos_version": "0.9.0",
        "inference_usage": [
            {"model": "llama3.1:8b", "provider": "ollama",
             "calls": 83, "input_tokens": 62000, "output_tokens": 19500, "cost_usd": 0.0},
        ],
        "compliance_violations": [],
    },
    {
        "name": "carol-surface",
        "token": "demo-token-carol-003",
        "os_name": "Windows",
        "os_version": "11",
        "intentos_version": "0.8.5",
        "inference_usage": [
            {"model": "claude-sonnet-4-20250514", "provider": "anthropic",
             "calls": 21, "input_tokens": 54300, "output_tokens": 15800, "cost_usd": 0.91},
            {"model": "mistral:7b", "provider": "ollama",
             "calls": 35, "input_tokens": 24000, "output_tokens": 9200, "cost_usd": 0.0},
        ],
        "compliance_violations": [
            {"event_type": "blocked_agent_attempt", "severity": "warning",
             "details": {"agent": "browser_agent", "action": "web_search"}},
            {"event_type": "spending_limit_warning", "severity": "info",
             "details": {"daily_spend": 8.50, "daily_limit": 10.0}},
        ],
    },
]


def send_heartbeats() -> None:
    """POST heartbeat payloads for 3 demo devices to the Console."""
    success = 0
    for device in DEVICES:
        payload = json.dumps({
            "os_name": device["os_name"],
            "os_version": device["os_version"],
            "intentos_version": device["intentos_version"],
            "inference_usage": device["inference_usage"],
            "compliance_violations": device["compliance_violations"],
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{CONSOLE_URL}/api/v1/telemetry/heartbeat",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Device-Token": device["token"],
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read())
                status = body.get("status", "unknown")
                print(f"  {device['name']}: {resp.status} ({status})")
                success += 1
        except urllib.error.HTTPError as exc:
            print(f"  {device['name']}: HTTP {exc.code} — {exc.reason}")
        except urllib.error.URLError:
            print(f"  {device['name']}: Console not reachable at {CONSOLE_URL}")
            if success == 0:
                print("\n  Hint: start the Console first —")
                print(f"    cd /tmp/intentos-console && python -m uvicorn backend.app.main:app --port 8000")
                return

    print(f"\n  Sent {success}/{len(DEVICES)} heartbeats")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary() -> None:
    print("""
Enterprise Demo Setup Complete
==============================

Policy:
  ~/.intentos/policy.json (signed, locked to smart_routing)
  ~/.intentos/enterprise.key

To test Desktop (as user):
  python scripts/launcher.py --no-browser
  curl http://localhost:7891/api/policy
  curl http://localhost:7891/api/inference-log
  curl http://localhost:7891/api/telemetry-status

To test Console (as IT admin):
  cd /tmp/intentos-console && python -m uvicorn backend.app.main:app --port 8000
  Open http://localhost:8000 in browser

Demo heartbeats sent to Console (if running):
  3 devices: alice-macbook, bob-thinkpad, carol-surface""")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set up an enterprise demo environment for IntentOS."
    )
    parser.add_argument("--setup-policy", action="store_true",
                        help="Create signed policy and key files")
    parser.add_argument("--send-heartbeats", action="store_true",
                        help="Send demo device heartbeats to the Console")
    parser.add_argument("--all", action="store_true",
                        help="Run everything (default when no flags given)")
    args = parser.parse_args()

    run_all = args.all or not (args.setup_policy or args.send_heartbeats)

    if run_all or args.setup_policy:
        print("\n[1/2] Setting up enterprise policy...")
        setup_policy()

    if run_all or args.send_heartbeats:
        print("\n[2/2] Sending demo heartbeats to Console...")
        send_heartbeats()

    print_summary()


if __name__ == "__main__":
    main()
