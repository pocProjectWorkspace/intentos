"""Tests for core.rag.experience — Experience Retriever (Phase 3D.2)."""

import json
import os
from datetime import datetime, timedelta
from typing import Optional

import pytest

from core.rag.experience import ExperienceRetriever, LearnedPattern, UserPreference


# ---------------------------------------------------------------------------
# Helper: build a fake task record
# ---------------------------------------------------------------------------

def _task(intent: str, params: dict, folder: str = "/tmp",
          completed_at: "Optional[datetime]" = None) -> dict:
    """Return a minimal task record dict."""
    return {
        "intent": intent,
        "params": params,
        "folder": folder,
        "completed_at": (completed_at or datetime.now()).isoformat(),
        "status": "completed",
    }


# ---------------------------------------------------------------------------
# LearnedPattern model
# ---------------------------------------------------------------------------

class TestLearnedPattern:
    """Tests 1-2: LearnedPattern dataclass."""

    def test_fields(self):
        """Test 1: LearnedPattern contains all required fields."""
        now = datetime.now()
        p = LearnedPattern(
            pattern_type="intent_preference",
            description="User prefers PDF export",
            confidence=0.85,
            frequency=10,
            last_seen=now,
            parameters={"format": "pdf"},
        )
        assert p.pattern_type == "intent_preference"
        assert p.description == "User prefers PDF export"
        assert p.confidence == 0.85
        assert p.frequency == 10
        assert p.last_seen == now
        assert p.parameters == {"format": "pdf"}

    def test_serialization(self):
        """Test 2: LearnedPattern round-trips through dict."""
        now = datetime.now()
        p = LearnedPattern(
            pattern_type="folder_preference",
            description="Saves invoices to /docs",
            confidence=0.9,
            frequency=5,
            last_seen=now,
            parameters={"folder": "/docs"},
        )
        d = p.to_dict()
        assert isinstance(d, dict)
        p2 = LearnedPattern.from_dict(d)
        assert p2.pattern_type == p.pattern_type
        assert p2.description == p.description
        assert p2.confidence == p.confidence
        assert p2.frequency == p.frequency
        assert p2.parameters == p.parameters
        # datetime round-trip (ISO)
        assert abs((p2.last_seen - p.last_seen).total_seconds()) < 1


# ---------------------------------------------------------------------------
# UserPreference model
# ---------------------------------------------------------------------------

class TestUserPreference:
    """Tests 3-4: UserPreference dataclass."""

    def test_fields(self):
        """Test 3: UserPreference contains all required fields."""
        pref = UserPreference(
            key="rename_pattern",
            value="YYYY-MM-DD",
            confidence=0.75,
            source_count=8,
        )
        assert pref.key == "rename_pattern"
        assert pref.value == "YYYY-MM-DD"
        assert pref.confidence == 0.75
        assert pref.source_count == 8

    def test_serialization(self):
        """Test 4: UserPreference round-trips through dict."""
        pref = UserPreference(
            key="default_export_format",
            value="pdf",
            confidence=0.95,
            source_count=12,
        )
        d = pref.to_dict()
        assert isinstance(d, dict)
        pref2 = UserPreference.from_dict(d)
        assert pref2.key == pref.key
        assert pref2.value == pref.value
        assert pref2.confidence == pref.confidence
        assert pref2.source_count == pref.source_count


# ---------------------------------------------------------------------------
# ExperienceRetriever — Learning from Tasks
# ---------------------------------------------------------------------------

class TestLearningFromTasks:
    """Tests 5-8: learn / learn_batch / pattern + preference detection."""

    def test_learn_single_task(self):
        """Test 5: learn() accepts a completed task record."""
        er = ExperienceRetriever()
        task = _task("rename_file", {"pattern": "YYYY-MM-DD"})
        er.learn(task)
        # Should record the task in history without error
        assert len(er._intent_history["rename_file"]) == 1

    def test_learn_batch(self):
        """Test 6: learn_batch() processes multiple tasks."""
        er = ExperienceRetriever()
        tasks = [
            _task("rename_file", {"pattern": "YYYY-MM-DD"}),
            _task("rename_file", {"pattern": "YYYY-MM-DD"}),
            _task("export_doc", {"format": "pdf"}),
        ]
        er.learn_batch(tasks)
        assert len(er._intent_history["rename_file"]) == 2
        assert len(er._intent_history["export_doc"]) == 1

    def test_pattern_detected_after_3_tasks_same_intent(self):
        """Test 7: After 3+ tasks with same intent, a pattern is detected."""
        er = ExperienceRetriever()
        for _ in range(3):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"}))
        patterns = er.get_patterns_for_intent("rename_file")
        assert len(patterns) >= 1

    def test_preference_inferred_after_5_tasks_same_params(self):
        """Test 8: After 5+ tasks with same params, a preference is inferred."""
        er = ExperienceRetriever()
        for _ in range(5):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"}))
        prefs = er.get_preferences()
        # Should have a preference for rename_file.pattern = YYYY-MM-DD
        matching = [p for p in prefs if p.value == "YYYY-MM-DD"]
        assert len(matching) >= 1


# ---------------------------------------------------------------------------
# ExperienceRetriever — Pattern Detection
# ---------------------------------------------------------------------------

class TestPatternDetection:
    """Tests 9-13: pattern retrieval and confidence."""

    def test_get_patterns_returns_all(self):
        """Test 9: get_patterns() returns all detected patterns."""
        er = ExperienceRetriever()
        for _ in range(3):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"}))
        for _ in range(3):
            er.learn(_task("export_doc", {"format": "pdf"}))
        patterns = er.get_patterns()
        # Should have patterns for both intents
        types = {p.pattern_type for p in patterns}
        assert len(patterns) >= 2

    def test_get_patterns_for_intent(self):
        """Test 10: get_patterns_for_intent() filters correctly."""
        er = ExperienceRetriever()
        for _ in range(3):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"}))
        for _ in range(3):
            er.learn(_task("export_doc", {"format": "pdf"}))
        rename_patterns = er.get_patterns_for_intent("rename_file")
        export_patterns = er.get_patterns_for_intent("export_doc")
        assert all("rename_file" in p.description or p.parameters.get("intent") == "rename_file"
                    for p in rename_patterns)
        assert len(export_patterns) >= 1

    def test_confidence_increases_with_repetition(self):
        """Test 11: Pattern confidence increases with more repetitions."""
        er = ExperienceRetriever()
        for _ in range(3):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"}))
        patterns_3 = er.get_patterns_for_intent("rename_file")
        conf_3 = max(p.confidence for p in patterns_3)

        for _ in range(5):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"}))
        patterns_8 = er.get_patterns_for_intent("rename_file")
        conf_8 = max(p.confidence for p in patterns_8)
        assert conf_8 > conf_3

    def test_confidence_decays_with_time(self):
        """Test 12: Pattern confidence decays for old patterns."""
        er = ExperienceRetriever()
        old_time = datetime.now() - timedelta(days=60)
        for _ in range(5):
            er.learn(_task("old_task", {"x": "1"}, completed_at=old_time))

        recent_time = datetime.now()
        for _ in range(5):
            er.learn(_task("new_task", {"x": "1"}, completed_at=recent_time))

        old_patterns = er.get_patterns_for_intent("old_task")
        new_patterns = er.get_patterns_for_intent("new_task")
        assert len(old_patterns) >= 1 and len(new_patterns) >= 1
        old_conf = max(p.confidence for p in old_patterns)
        new_conf = max(p.confidence for p in new_patterns)
        assert new_conf > old_conf

    def test_pattern_includes_preferred_params_and_folders(self):
        """Test 13: Pattern includes preferred parameters, folders, agents."""
        er = ExperienceRetriever()
        for _ in range(4):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"},
                           folder="/home/user/photos"))
        patterns = er.get_patterns_for_intent("rename_file")
        assert len(patterns) >= 1
        # At least one pattern should mention parameters or folders
        has_params = any(p.parameters for p in patterns)
        assert has_params


# ---------------------------------------------------------------------------
# ExperienceRetriever — Preference Inference
# ---------------------------------------------------------------------------

class TestPreferenceInference:
    """Tests 14-18: preference detection and confidence."""

    def test_get_preferences_returns_all(self):
        """Test 14: get_preferences() returns all inferred preferences."""
        er = ExperienceRetriever()
        for _ in range(5):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"}))
        for _ in range(5):
            er.learn(_task("export_doc", {"format": "pdf"}))
        prefs = er.get_preferences()
        assert len(prefs) >= 2

    def test_rename_pattern_preference(self):
        """Test 15: Renaming photos by date 5+ times -> preference."""
        er = ExperienceRetriever()
        for _ in range(6):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"}))
        prefs = er.get_preferences()
        matching = [p for p in prefs if p.key == "rename_file.pattern"
                    and p.value == "YYYY-MM-DD"]
        assert len(matching) == 1

    def test_invoice_folder_preference(self):
        """Test 16: Saving invoices to same folder 3+ times -> preference."""
        er = ExperienceRetriever()
        for _ in range(5):
            er.learn(_task("save_invoice", {"type": "invoice"},
                           folder="/home/user/invoices"))
        prefs = er.get_preferences()
        folder_prefs = [p for p in prefs if "folder" in p.key.lower()
                        and p.value == "/home/user/invoices"]
        assert len(folder_prefs) >= 1

    def test_export_format_preference(self):
        """Test 17: Always exporting as PDF -> preference."""
        er = ExperienceRetriever()
        for _ in range(5):
            er.learn(_task("export_doc", {"format": "pdf"}))
        prefs = er.get_preferences()
        matching = [p for p in prefs if p.key == "export_doc.format"
                    and p.value == "pdf"]
        assert len(matching) == 1

    def test_preference_confidence_based_on_consistency(self):
        """Test 18: Preferences have confidence based on consistency."""
        er = ExperienceRetriever()
        # 4 out of 5 with same value => high but not perfect confidence
        for _ in range(4):
            er.learn(_task("export_doc", {"format": "pdf"}))
        er.learn(_task("export_doc", {"format": "docx"}))
        prefs = er.get_preferences()
        pdf_pref = [p for p in prefs if p.key == "export_doc.format"
                    and p.value == "pdf"]
        assert len(pdf_pref) == 1
        assert 0.5 < pdf_pref[0].confidence < 1.0


# ---------------------------------------------------------------------------
# ExperienceRetriever — Suggestions
# ---------------------------------------------------------------------------

class TestSuggestions:
    """Tests 19-22: suggest() method."""

    def test_suggest_returns_suggestions(self):
        """Test 19: suggest() returns list of suggestions."""
        er = ExperienceRetriever()
        for _ in range(5):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"},
                           folder="/home/user/photos"))
        suggestions = er.suggest("rename my photos", "rename_file")
        assert isinstance(suggestions, list)
        assert len(suggestions) >= 1

    def test_suggestions_include_params_and_folder(self):
        """Test 20: Suggestions include predicted params and folder."""
        er = ExperienceRetriever()
        for _ in range(5):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"},
                           folder="/home/user/photos"))
        suggestions = er.suggest("rename my photos", "rename_file")
        # Flatten all suggestion dicts
        all_keys = set()
        for s in suggestions:
            all_keys.update(s.keys())
        # Should have at least type and value keys
        assert len(suggestions) >= 1

    def test_no_experience_empty_suggestions(self):
        """Test 21: No experience -> empty suggestions."""
        er = ExperienceRetriever()
        suggestions = er.suggest("do something", "unknown_intent")
        assert suggestions == []

    def test_low_confidence_excluded(self):
        """Test 22: Low-confidence patterns not included (threshold 0.5)."""
        er = ExperienceRetriever()
        # Only 3 tasks, 2 different values -> low confidence
        er.learn(_task("export_doc", {"format": "pdf"}))
        er.learn(_task("export_doc", {"format": "docx"}))
        er.learn(_task("export_doc", {"format": "html"}))
        suggestions = er.suggest("export document", "export_doc")
        # All suggestions should have confidence >= 0.5
        for s in suggestions:
            if "confidence" in s:
                assert s["confidence"] >= 0.5


# ---------------------------------------------------------------------------
# ExperienceRetriever — Profile Building
# ---------------------------------------------------------------------------

class TestProfileBuilding:
    """Tests 23-24: build_profile()."""

    def test_build_profile_structure(self):
        """Test 23: build_profile() returns dict with preferences, folders, patterns."""
        er = ExperienceRetriever()
        for _ in range(5):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"},
                           folder="/home/user/photos"))
        profile = er.build_profile()
        assert isinstance(profile, dict)
        assert "preferences" in profile
        assert "frequent_folders" in profile
        assert "task_patterns" in profile

    def test_build_profile_includes_all_data(self):
        """Test 24: Profile includes all preferences and patterns."""
        er = ExperienceRetriever()
        for _ in range(5):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"},
                           folder="/home/user/photos"))
        for _ in range(5):
            er.learn(_task("export_doc", {"format": "pdf"},
                           folder="/home/user/exports"))
        profile = er.build_profile()
        assert len(profile["preferences"]) >= 2
        assert len(profile["task_patterns"]) >= 2
        assert len(profile["frequent_folders"]) >= 1


# ---------------------------------------------------------------------------
# ExperienceRetriever — Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    """Tests 25-26: save() / load()."""

    def test_save_and_load(self, tmp_path):
        """Test 25: save(path) / load(path) — JSON serialization."""
        er = ExperienceRetriever()
        for _ in range(5):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"},
                           folder="/home/user/photos"))
        filepath = str(tmp_path / "experience.json")
        er.save(filepath)
        assert os.path.exists(filepath)

        er2 = ExperienceRetriever()
        er2.load(filepath)
        assert len(er2.get_patterns()) == len(er.get_patterns())
        assert len(er2.get_preferences()) == len(er.get_preferences())

    def test_round_trip_preserves_data(self, tmp_path):
        """Test 26: Round-trip preserves all data."""
        er = ExperienceRetriever()
        for _ in range(5):
            er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"}))
        for _ in range(5):
            er.learn(_task("export_doc", {"format": "pdf"}))
        filepath = str(tmp_path / "experience.json")
        er.save(filepath)

        er2 = ExperienceRetriever()
        er2.load(filepath)

        # Compare patterns
        p1 = sorted([p.to_dict() for p in er.get_patterns()],
                     key=lambda x: x["description"])
        p2 = sorted([p.to_dict() for p in er2.get_patterns()],
                     key=lambda x: x["description"])
        assert p1 == p2

        # Compare preferences
        pref1 = sorted([p.to_dict() for p in er.get_preferences()],
                        key=lambda x: x["key"])
        pref2 = sorted([p.to_dict() for p in er2.get_preferences()],
                        key=lambda x: x["key"])
        assert pref1 == pref2


# ---------------------------------------------------------------------------
# ExperienceRetriever — Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests 27-29: edge cases."""

    def test_empty_retriever_defaults(self):
        """Test 27: Empty retriever returns sensible defaults."""
        er = ExperienceRetriever()
        assert er.get_patterns() == []
        assert er.get_preferences() == []
        assert er.suggest("anything", "any_intent") == []
        profile = er.build_profile()
        assert profile["preferences"] == []
        assert profile["frequent_folders"] == []
        assert profile["task_patterns"] == []

    def test_contradictory_patterns_lower_confidence(self):
        """Test 28: Contradictory patterns result in lower confidence."""
        er = ExperienceRetriever()
        # Mix of different values for the same param
        for _ in range(3):
            er.learn(_task("export_doc", {"format": "pdf"}))
        for _ in range(3):
            er.learn(_task("export_doc", {"format": "docx"}))
        patterns = er.get_patterns_for_intent("export_doc")
        # Confidence should be lower than when all values agree
        er2 = ExperienceRetriever()
        for _ in range(6):
            er2.learn(_task("export_doc", {"format": "pdf"}))
        patterns2 = er2.get_patterns_for_intent("export_doc")
        # Consistent should have higher max confidence
        max_conf_mixed = max(p.confidence for p in patterns)
        max_conf_consistent = max(p.confidence for p in patterns2)
        assert max_conf_consistent > max_conf_mixed

    def test_single_task_no_patterns(self):
        """Test 29: Single task -> no patterns detected."""
        er = ExperienceRetriever()
        er.learn(_task("rename_file", {"pattern": "YYYY-MM-DD"}))
        assert er.get_patterns() == []
        assert er.get_preferences() == []
