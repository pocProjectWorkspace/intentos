"""Tests for _extract_json — robust JSON extraction from local LLM output."""

from __future__ import annotations

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pytest
from core.inference.llm import _extract_json


# -- Clean JSON (cloud models) ------------------------------------------------

def test_clean_json():
    raw = '{"raw_input": "hello", "intent": "file.list", "subtasks": []}'
    result = _extract_json(raw)
    assert result is not None
    assert result["intent"] == "file.list"


# -- Markdown fenced JSON (most common local model issue) ----------------------

def test_json_in_markdown_fence():
    raw = '```json\n{"raw_input": "test", "intent": "file.find", "subtasks": []}\n```'
    result = _extract_json(raw)
    assert result is not None
    assert result["intent"] == "file.find"


def test_json_in_plain_fence():
    raw = '```\n{"raw_input": "test", "intent": "file.find", "subtasks": []}\n```'
    result = _extract_json(raw)
    assert result is not None
    assert result["intent"] == "file.find"


# -- Preamble text before JSON ------------------------------------------------

def test_preamble_then_json():
    raw = (
        "Sure! Here is the structured intent:\n\n"
        '{"raw_input": "list files", "intent": "file.list", "subtasks": []}'
    )
    result = _extract_json(raw)
    assert result is not None
    assert result["intent"] == "file.list"


def test_preamble_and_fence():
    raw = (
        "Here is the JSON output:\n\n"
        "```json\n"
        '{"raw_input": "find big files", "intent": "file.find", "subtasks": [{"id": "1", "agent": "file_agent", "action": "find_files", "params": {"path": "~/Downloads"}}]}\n'
        "```\n\n"
        "Let me know if you need anything else!"
    )
    result = _extract_json(raw)
    assert result is not None
    assert result["intent"] == "file.find"
    assert len(result["subtasks"]) == 1


# -- Nested braces (params contain dicts) -------------------------------------

def test_nested_braces():
    raw = (
        'I think this is what you need:\n'
        '{"raw_input": "rename", "intent": "file.rename", '
        '"subtasks": [{"id": "1", "agent": "file_agent", "action": "rename_file", '
        '"params": {"old": "a.txt", "new": "b.txt"}}]}'
    )
    result = _extract_json(raw)
    assert result is not None
    assert result["subtasks"][0]["params"]["old"] == "a.txt"


# -- Edge cases ----------------------------------------------------------------

def test_empty_string():
    assert _extract_json("") is None


def test_none_input():
    assert _extract_json(None) is None


def test_no_json_at_all():
    assert _extract_json("I don't understand your request.") is None


def test_whitespace_around_json():
    raw = '  \n  {"intent": "file.list", "subtasks": []}  \n  '
    result = _extract_json(raw)
    assert result is not None
    assert result["intent"] == "file.list"
