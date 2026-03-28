"""Tests for core.rag.user_profile — Phase 4.1: User Profile Index.

Passive preference learning from task history.
"""

import json
import os
import tempfile

import pytest

from core.rag.user_profile import UserProfile, ProfileManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(intent="rename_file", folder="/home/user/docs", params=None,
               completed_at="2026-03-28T10:00:00"):
    """Build a minimal task record dict."""
    return {
        "intent": intent,
        "params": params or {},
        "folder": folder,
        "completed_at": completed_at,
    }


# ===================================================================
# UserProfile model
# ===================================================================

class TestUserProfile:
    """UserProfile dataclass behaviour."""

    def test_default_profile(self):
        p = UserProfile()
        assert p.preferences == {}
        assert p.frequent_folders == {}
        assert p.frequent_contacts == []
        assert p.task_patterns == []
        assert p.avoided_actions == []

    def test_preferences_keys(self):
        p = UserProfile(preferences={
            "date_format": "YYYY-MM-DD",
            "export_format": "csv",
            "image_format": "png",
            "archive_format": "zip",
            "language": "en",
            "timezone": "UTC",
        })
        assert p.preferences["date_format"] == "YYYY-MM-DD"
        assert p.preferences["timezone"] == "UTC"

    def test_frequent_folders(self):
        p = UserProfile(frequent_folders={"docs": "/home/user/docs"})
        assert p.frequent_folders["docs"] == "/home/user/docs"

    def test_frequent_contacts(self):
        p = UserProfile(frequent_contacts=[
            {"name": "Alice", "context": "project-x"},
        ])
        assert p.frequent_contacts[0]["name"] == "Alice"

    def test_task_patterns(self):
        p = UserProfile(task_patterns=[
            {"pattern": "rename_file", "frequency": 7,
             "last_used": "2026-03-28", "preferred_params": {"prefix": "v"}},
        ])
        assert p.task_patterns[0]["frequency"] == 7

    def test_avoided_actions(self):
        p = UserProfile(avoided_actions=["delete_without_confirm"])
        assert "delete_without_confirm" in p.avoided_actions

    def test_serialization_roundtrip(self):
        p = UserProfile(
            preferences={"date_format": "DD/MM/YYYY", "export_format": "pdf"},
            frequent_folders={"downloads": "/tmp/dl"},
            frequent_contacts=[{"name": "Bob", "context": "work"}],
            task_patterns=[{"pattern": "export", "frequency": 3,
                            "last_used": "2026-03-01",
                            "preferred_params": {"fmt": "pdf"}}],
            avoided_actions=["overwrite"],
        )
        d = p.to_dict()
        p2 = UserProfile.from_dict(d)
        assert p2.preferences == p.preferences
        assert p2.frequent_folders == p.frequent_folders
        assert p2.frequent_contacts == p.frequent_contacts
        assert p2.task_patterns == p.task_patterns
        assert p2.avoided_actions == p.avoided_actions

    def test_serialization_json_compatible(self):
        p = UserProfile(preferences={"language": "en"})
        blob = json.dumps(p.to_dict())
        p2 = UserProfile.from_dict(json.loads(blob))
        assert p2.preferences["language"] == "en"


# ===================================================================
# ProfileManager — learning
# ===================================================================

class TestProfileManagerLearning:
    """ProfileManager.learn_from_task and derived state."""

    def test_empty_history_default_profile(self):
        pm = ProfileManager()
        prof = pm.get_profile()
        assert prof.preferences == {}
        assert prof.frequent_folders == {}
        assert prof.task_patterns == []

    def test_single_task_no_patterns(self):
        pm = ProfileManager()
        pm.learn_from_task(_make_task(folder="/home/user/docs"))
        prof = pm.get_profile()
        # Not enough repetitions yet
        assert prof.frequent_folders == {}
        assert prof.task_patterns == []

    def test_frequent_folder_after_three_tasks(self):
        pm = ProfileManager()
        for i in range(3):
            pm.learn_from_task(_make_task(folder="/home/user/docs"))
        prof = pm.get_profile()
        assert "/home/user/docs" in prof.frequent_folders.values()

    def test_frequent_folder_not_added_below_threshold(self):
        pm = ProfileManager()
        for i in range(2):
            pm.learn_from_task(_make_task(folder="/home/user/docs"))
        prof = pm.get_profile()
        assert prof.frequent_folders == {}

    def test_task_pattern_after_five_tasks(self):
        pm = ProfileManager()
        for i in range(5):
            pm.learn_from_task(_make_task(
                intent="rename_file",
                params={"pattern": "date_prefix"},
            ))
        prof = pm.get_profile()
        assert len(prof.task_patterns) >= 1
        assert prof.task_patterns[0]["pattern"] == "rename_file"

    def test_task_pattern_not_added_below_threshold(self):
        pm = ProfileManager()
        for i in range(4):
            pm.learn_from_task(_make_task(
                intent="rename_file",
                params={"pattern": "date_prefix"},
            ))
        prof = pm.get_profile()
        assert prof.task_patterns == []

    def test_detects_date_format_preference(self):
        pm = ProfileManager()
        for i in range(5):
            pm.learn_from_task(_make_task(
                params={"date_format": "YYYY-MM-DD"},
            ))
        prof = pm.get_profile()
        assert prof.preferences.get("date_format") == "YYYY-MM-DD"

    def test_detects_export_format_preference(self):
        pm = ProfileManager()
        for i in range(5):
            pm.learn_from_task(_make_task(
                intent="export",
                params={"export_format": "csv"},
            ))
        prof = pm.get_profile()
        assert prof.preferences.get("export_format") == "csv"

    def test_contradictory_preferences_lower_confidence(self):
        """When half the tasks say csv and half say pdf, confidence drops."""
        pm = ProfileManager()
        for i in range(5):
            pm.learn_from_task(_make_task(params={"export_format": "csv"}))
        for i in range(5):
            pm.learn_from_task(_make_task(params={"export_format": "pdf"}))
        conf = pm.confidence("export_format")
        # Should be around 0.5, not high
        assert conf is not None
        assert conf <= 0.6


# ===================================================================
# ProfileManager — query helpers
# ===================================================================

class TestProfileManagerQueries:

    def test_get_preference_returns_value(self):
        pm = ProfileManager()
        for i in range(5):
            pm.learn_from_task(_make_task(params={"date_format": "ISO"}))
        assert pm.get_preference("date_format") == "ISO"

    def test_get_preference_returns_none_unknown(self):
        pm = ProfileManager()
        assert pm.get_preference("nonexistent") is None

    def test_confidence_scoring(self):
        pm = ProfileManager()
        for i in range(10):
            pm.learn_from_task(_make_task(params={"date_format": "ISO"}))
        conf = pm.confidence("date_format")
        assert conf is not None
        assert conf > 0.8

    def test_suggest_for_intent(self):
        pm = ProfileManager()
        for i in range(5):
            pm.learn_from_task(_make_task(
                intent="export",
                params={"export_format": "csv"},
                folder="/home/user/exports",
            ))
        suggestions = pm.suggest_for_intent("export")
        assert isinstance(suggestions, dict)
        # Should contain something useful
        assert len(suggestions) > 0


# ===================================================================
# ProfileManager — merge, persistence, reset
# ===================================================================

class TestProfileManagerOps:

    def test_merge_profiles_higher_frequency_wins(self):
        a = UserProfile(
            preferences={"date_format": "ISO"},
            task_patterns=[
                {"pattern": "rename", "frequency": 3,
                 "last_used": "2026-03-01", "preferred_params": {}},
            ],
        )
        b = UserProfile(
            preferences={"date_format": "US", "export_format": "csv"},
            task_patterns=[
                {"pattern": "rename", "frequency": 7,
                 "last_used": "2026-03-20", "preferred_params": {}},
            ],
        )
        merged = ProfileManager.merge_profiles(a, b)
        # b has higher frequency rename pattern
        rename_patterns = [p for p in merged.task_patterns
                           if p["pattern"] == "rename"]
        assert rename_patterns[0]["frequency"] == 7
        # Both preferences present; date_format could go either way,
        # but export_format from b should be there
        assert merged.preferences.get("export_format") == "csv"

    def test_save_load_roundtrip(self):
        pm = ProfileManager()
        for i in range(5):
            pm.learn_from_task(_make_task(
                params={"date_format": "ISO"},
                folder="/home/user/docs",
            ))
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            pm.save(path)
            pm2 = ProfileManager()
            pm2.load(path)
            prof = pm2.get_profile()
            assert prof.preferences.get("date_format") == "ISO"
        finally:
            os.unlink(path)

    def test_reset_clears_all(self):
        pm = ProfileManager()
        for i in range(5):
            pm.learn_from_task(_make_task(params={"date_format": "ISO"}))
        pm.reset()
        prof = pm.get_profile()
        assert prof.preferences == {}
        assert prof.frequent_folders == {}
        assert prof.task_patterns == []

    def test_load_nonexistent_raises(self):
        pm = ProfileManager()
        with pytest.raises(FileNotFoundError):
            pm.load("/tmp/does_not_exist_user_profile.json")
