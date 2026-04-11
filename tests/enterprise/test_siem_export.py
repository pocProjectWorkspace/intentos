"""Tests for SIEM export module — Splunk HEC and Azure Sentinel formats."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from core.enterprise.siem_export import SIEMExporter


@pytest.fixture
def exporter(tmp_path):
    return SIEMExporter(base_path=tmp_path)


@pytest.fixture
def sample_events():
    return [
        {
            "timestamp": "2026-04-09T10:00:00Z",
            "hostname": "dev-macbook",
            "action": "llm_inference",
            "input_tokens": 500,
            "output_tokens": 100,
            "model": "llama3",
            "provider": "ollama",
            "cost_usd": 0.0,
            "privacy_mode": "local_only",
            "status": "success",
        },
        {
            "timestamp": "2026-04-09T10:01:00Z",
            "hostname": "dev-macbook",
            "action": "file_search",
            "tool": "file_agent",
            "agent": "file_agent",
            "status": "success",
        },
        {
            "timestamp": "2026-04-09T10:02:00Z",
            "hostname": "dev-macbook",
            "event_type": "policy_violation",
            "severity": "warning",
            "details": {"rule": "cloud_access_denied"},
        },
    ]


def test_splunk_hec_format(exporter, sample_events):
    result = exporter.export_splunk_hec(sample_events)
    assert len(result) == 3
    for event in result:
        assert "time" in event
        assert "host" in event
        assert "source" in event
        assert "sourcetype" in event
        assert "index" in event
        assert "event" in event
        assert event["source"] == "intentos:desktop"
        assert event["index"] == "intentos"


def test_sentinel_format(exporter, sample_events):
    result = exporter.export_sentinel(sample_events)
    assert len(result) == 3
    for event in result:
        assert "TimeGenerated" in event
        assert "Computer" in event
        assert "Category" in event
        assert "OperationName" in event


def test_export_to_file(exporter, sample_events):
    # Write some events to the logs directory so export_to_file can read them
    logs_dir = exporter._base / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    with open(logs_dir / "audit.jsonl", "w") as f:
        for ev in sample_events:
            f.write(json.dumps(ev) + "\n")

    filepath = exporter.export_to_file("splunk")
    assert os.path.exists(filepath)
    assert filepath.endswith(".jsonl")

    with open(filepath) as f:
        lines = [line.strip() for line in f if line.strip()]
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert first["source"] == "intentos:desktop"


def test_collect_empty(exporter):
    events = exporter._collect_local_events()
    assert events == []


def test_sourcetype_detection(exporter):
    inference_event = {"input_tokens": 100, "output_tokens": 50}
    assert exporter._get_sourcetype(inference_event) == "intentos:inference"

    agent_event = {"tool": "file_agent", "action": "search"}
    assert exporter._get_sourcetype(agent_event) == "intentos:agent_action"

    compliance_event = {"event_type": "policy_violation"}
    assert exporter._get_sourcetype(compliance_event) == "intentos:compliance"

    generic_event = {"action": "login"}
    assert exporter._get_sourcetype(generic_event) == "intentos:audit"
