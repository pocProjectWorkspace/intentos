"""Tests for telemetry consent in TelemetryReporter."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _project_root)

from core.enterprise.telemetry import TelemetryReporter


@pytest.fixture
def base(tmp_path):
    """Provide a temporary ~/.intentos directory."""
    return tmp_path / ".intentos"


def _make_reporter(base: Path, policy=None) -> TelemetryReporter:
    return TelemetryReporter(
        console_url="https://console.test.com",
        device_token="tok-123",
        interval=300,
        policy_engine=policy,
        base_path=base,
    )


def test_no_consent_file(base):
    """Without a consent file, _check_consent returns False."""
    reporter = _make_reporter(base)
    assert reporter._check_consent() is False


def test_consent_granted(base):
    """With consent=True in file, _check_consent returns True."""
    base.mkdir(parents=True)
    (base / "telemetry_consent.json").write_text(
        json.dumps({"consented": True, "consented_at": "2026-04-09T00:00:00Z"})
    )
    reporter = _make_reporter(base)
    assert reporter._check_consent() is True


def test_consent_revoked(base):
    """With consent=False in file, _check_consent returns False."""
    base.mkdir(parents=True)
    (base / "telemetry_consent.json").write_text(
        json.dumps({"consented": False})
    )
    reporter = _make_reporter(base)
    assert reporter._check_consent() is False


def test_managed_skips_consent(base):
    """Policy-managed mode starts reporter without consent file."""
    policy = MagicMock()
    policy.is_managed = True
    policy.get_compliance_status.return_value = {}

    reporter = _make_reporter(base, policy=policy)
    assert reporter._check_consent() is False  # no consent file

    reporter.start()
    assert reporter._running is True
    reporter.stop()


def test_no_consent_prevents_start(base):
    """Without consent, start() does not begin reporting."""
    reporter = _make_reporter(base)
    reporter.start()
    assert reporter._running is False


def test_grant_and_revoke(base):
    """grant_consent writes file, revoke_consent clears it."""
    TelemetryReporter.grant_consent(base_path=base)
    data = json.loads((base / "telemetry_consent.json").read_text())
    assert data["consented"] is True
    assert "consented_at" in data

    TelemetryReporter.revoke_consent(base_path=base)
    data = json.loads((base / "telemetry_consent.json").read_text())
    assert data["consented"] is False
