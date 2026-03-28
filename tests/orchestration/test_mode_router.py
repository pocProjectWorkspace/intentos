"""
Tests for IntentOS React Mode Router (Phase 2B.4).

TDD tests — written before implementation.
Covers ReactMode enum, ComplexityScore, ModeRouter scoring & selection.
"""

from __future__ import annotations

import pytest

from core.orchestration.mode_router import (
    ComplexityScore,
    ModeRouter,
    ReactMode,
    ScoringWeights,
)


# ============================================================================
# 1. ReactMode enum
# ============================================================================

class TestReactModeEnum:
    """Test 1: Three modes exist."""

    def test_three_modes_exist(self):
        assert ReactMode.BY_ORDER is not None
        assert ReactMode.PLAN_AND_ACT is not None
        assert ReactMode.REACT is not None

    def test_enum_values_are_strings(self):
        assert isinstance(ReactMode.BY_ORDER.value, str)
        assert isinstance(ReactMode.PLAN_AND_ACT.value, str)
        assert isinstance(ReactMode.REACT.value, str)

    def test_exactly_three_members(self):
        assert len(ReactMode) == 3


# ============================================================================
# 2-3. ComplexityScore model
# ============================================================================

class TestComplexityScore:
    """Tests 2-3: ComplexityScore contains required fields & total_score is weighted sum."""

    def test_contains_all_fields(self):
        score = ComplexityScore(
            token_count_score=0.1,
            task_type_score=0.2,
            ambiguity_score=0.3,
            context_depth_score=0.4,
            agent_count_score=0.5,
        )
        assert score.token_count_score == 0.1
        assert score.task_type_score == 0.2
        assert score.ambiguity_score == 0.3
        assert score.context_depth_score == 0.4
        assert score.agent_count_score == 0.5
        assert isinstance(score.total_score, float)

    def test_total_score_is_weighted_sum_default(self):
        score = ComplexityScore(
            token_count_score=1.0,
            task_type_score=1.0,
            ambiguity_score=1.0,
            context_depth_score=1.0,
            agent_count_score=1.0,
        )
        # Default weights: token=0.15, task_type=0.30, ambiguity=0.25, context=0.10, agent_count=0.20
        expected = 0.15 + 0.30 + 0.25 + 0.10 + 0.20
        assert score.total_score == pytest.approx(expected, abs=1e-6)

    def test_total_score_with_custom_weights(self):
        weights = ScoringWeights(
            token=0.2, task_type=0.2, ambiguity=0.2, context=0.2, agent_count=0.2
        )
        score = ComplexityScore(
            token_count_score=0.5,
            task_type_score=0.5,
            ambiguity_score=0.5,
            context_depth_score=0.5,
            agent_count_score=0.5,
            weights=weights,
        )
        expected = 5 * (0.2 * 0.5)
        assert score.total_score == pytest.approx(expected, abs=1e-6)


# ============================================================================
# 4-11. ModeRouter — Mode Selection
# ============================================================================

class TestModeSelection:
    """Tests 4-11: select_mode returns the correct ReactMode."""

    @pytest.fixture()
    def router(self) -> ModeRouter:
        return ModeRouter()

    # 4. Single subtask, simple action -> BY_ORDER
    def test_single_simple_subtask(self, router: ModeRouter):
        subtasks = [{"id": "1", "agent": "file_agent", "action": "list_files", "params": {}}]
        mode = router.select_mode("list my files", subtasks)
        assert mode == ReactMode.BY_ORDER

    # 5. Single subtask, complex action -> BY_ORDER (still single agent)
    def test_single_complex_subtask(self, router: ModeRouter):
        subtasks = [{"id": "1", "agent": "web_agent", "action": "search_web", "params": {}}]
        mode = router.select_mode("search the web and extract data", subtasks)
        assert mode == ReactMode.BY_ORDER

    # 6. Two subtasks, same agent -> BY_ORDER
    def test_two_subtasks_same_agent(self, router: ModeRouter):
        subtasks = [
            {"id": "1", "agent": "file_agent", "action": "list_files", "params": {}},
            {"id": "2", "agent": "file_agent", "action": "read_file", "params": {}},
        ]
        mode = router.select_mode("list and read files", subtasks)
        assert mode == ReactMode.BY_ORDER

    # 7. Three+ subtasks, multiple agents -> PLAN_AND_ACT
    def test_three_subtasks_multiple_agents(self, router: ModeRouter):
        subtasks = [
            {"id": "1", "agent": "file_agent", "action": "list_files", "params": {}},
            {"id": "2", "agent": "web_agent", "action": "search_web", "params": {}},
            {"id": "3", "agent": "doc_agent", "action": "summarize", "params": {}},
        ]
        mode = router.select_mode("find files then search web and summarize", subtasks)
        assert mode == ReactMode.PLAN_AND_ACT

    # 8. Ambiguous intent -> REACT
    def test_ambiguous_intent(self, router: ModeRouter):
        subtasks = [{"id": "1", "agent": "file_agent", "action": "list_files", "params": {}}]
        mode = router.select_mode("maybe list the files, not sure what I need", subtasks)
        assert mode == ReactMode.REACT

    # 9. Research intent -> REACT
    def test_research_intent(self, router: ModeRouter):
        subtasks = [{"id": "1", "agent": "web_agent", "action": "search_web", "params": {}}]
        mode = router.select_mode("investigate why the server is slow", subtasks)
        assert mode == ReactMode.REACT

    # 10. Single destructive action -> BY_ORDER
    def test_single_destructive_action(self, router: ModeRouter):
        subtasks = [{"id": "1", "agent": "file_agent", "action": "delete_file", "params": {"path": "/tmp/x"}}]
        mode = router.select_mode("delete the temp file", subtasks)
        assert mode == ReactMode.BY_ORDER

    # 11. Batch operation (>5 files) -> PLAN_AND_ACT
    def test_batch_operation(self, router: ModeRouter):
        subtasks = [
            {"id": str(i), "agent": "file_agent", "action": "rename_file", "params": {}}
            for i in range(6)
        ]
        mode = router.select_mode("rename all these files", subtasks)
        assert mode == ReactMode.PLAN_AND_ACT


# ============================================================================
# 12-20. Complexity Scoring
# ============================================================================

class TestComplexityScoring:
    """Tests 12-20: score_complexity returns correct component scores."""

    @pytest.fixture()
    def router(self) -> ModeRouter:
        return ModeRouter()

    # 12. score_complexity returns ComplexityScore
    def test_returns_complexity_score(self, router: ModeRouter):
        result = router.score_complexity("hello", [])
        assert isinstance(result, ComplexityScore)

    # 13. Short input (<20 tokens) -> low token_count_score
    def test_short_input_low_token_score(self, router: ModeRouter):
        result = router.score_complexity("list files", [])
        assert result.token_count_score < 0.3

    # 14. Long input (>100 tokens) -> high token_count_score
    def test_long_input_high_token_score(self, router: ModeRouter):
        long_input = " ".join(["word"] * 120)
        result = router.score_complexity(long_input, [])
        assert result.token_count_score > 0.7

    # 15. Simple task types -> low task_type_score
    def test_simple_task_types_low_score(self, router: ModeRouter):
        subtasks = [{"id": "1", "agent": "file_agent", "action": "list_files", "params": {}}]
        result = router.score_complexity("list files", subtasks)
        assert result.task_type_score < 0.3

    # 16. Complex task types -> high task_type_score
    def test_complex_task_types_high_score(self, router: ModeRouter):
        subtasks = [{"id": "1", "agent": "doc_agent", "action": "research", "params": {}}]
        result = router.score_complexity("research this topic", subtasks)
        assert result.task_type_score > 0.7

    # 17. Single agent -> low agent_count_score
    def test_single_agent_low_score(self, router: ModeRouter):
        subtasks = [{"id": "1", "agent": "file_agent", "action": "list_files", "params": {}}]
        result = router.score_complexity("list files", subtasks)
        assert result.agent_count_score < 0.3

    # 18. 3+ agents -> high agent_count_score
    def test_multiple_agents_high_score(self, router: ModeRouter):
        subtasks = [
            {"id": "1", "agent": "file_agent", "action": "list_files", "params": {}},
            {"id": "2", "agent": "web_agent", "action": "search_web", "params": {}},
            {"id": "3", "agent": "doc_agent", "action": "summarize", "params": {}},
        ]
        result = router.score_complexity("do many things", subtasks)
        assert result.agent_count_score > 0.7

    # 19. Clear intent -> low ambiguity_score
    def test_clear_intent_low_ambiguity(self, router: ModeRouter):
        result = router.score_complexity("list all files in /tmp", [])
        assert result.ambiguity_score < 0.3

    # 20. Vague intent -> high ambiguity_score
    def test_vague_intent_high_ambiguity(self, router: ModeRouter):
        result = router.score_complexity(
            "maybe do something like organize or sort the files?", []
        )
        assert result.ambiguity_score > 0.7


# ============================================================================
# 21-22. Scoring Weights
# ============================================================================

class TestScoringWeights:
    """Tests 21-22: Default and custom weights."""

    # 21. Default weights
    def test_default_weights(self):
        w = ScoringWeights()
        assert w.token == pytest.approx(0.15)
        assert w.task_type == pytest.approx(0.30)
        assert w.ambiguity == pytest.approx(0.25)
        assert w.context == pytest.approx(0.10)
        assert w.agent_count == pytest.approx(0.20)

    # 22. Custom weights
    def test_custom_weights(self):
        w = ScoringWeights(token=0.5, task_type=0.1, ambiguity=0.1, context=0.1, agent_count=0.2)
        assert w.token == pytest.approx(0.5)
        assert w.task_type == pytest.approx(0.1)


# ============================================================================
# 23-25. Thresholds
# ============================================================================

class TestThresholds:
    """Tests 23-25: total_score thresholds map to correct modes."""

    @pytest.fixture()
    def router(self) -> ModeRouter:
        return ModeRouter()

    # 23. total_score < 0.3 -> BY_ORDER
    def test_low_score_by_order(self, router: ModeRouter):
        # Simple single task — should get a low score
        subtasks = [{"id": "1", "agent": "file_agent", "action": "list_files", "params": {}}]
        score = router.score_complexity("list files", subtasks)
        assert score.total_score < 0.3
        mode = router.select_mode("list files", subtasks)
        assert mode == ReactMode.BY_ORDER

    # 24. total_score 0.3-0.7 -> PLAN_AND_ACT
    def test_mid_score_plan_and_act(self, router: ModeRouter):
        subtasks = [
            {"id": str(i), "agent": f"agent_{i}", "action": "organize_by_type", "params": {}}
            for i in range(4)
        ]
        score = router.score_complexity("organize all my project files by type", subtasks)
        assert 0.3 <= score.total_score <= 0.7
        mode = router.select_mode("organize all my project files by type", subtasks)
        assert mode == ReactMode.PLAN_AND_ACT

    # 25. total_score > 0.7 -> REACT
    def test_high_score_react(self, router: ModeRouter):
        subtasks = [
            {"id": str(i), "agent": f"agent_{i}", "action": "research", "params": {}}
            for i in range(5)
        ]
        long_vague = (
            "maybe investigate or perhaps find out something like why the system is "
            "not sure behaving correctly? " + " ".join(["detail"] * 80)
        )
        score = router.score_complexity(long_vague, subtasks)
        assert score.total_score > 0.7
        mode = router.select_mode(long_vague, subtasks)
        assert mode == ReactMode.REACT


# ============================================================================
# 26-27. select_mode() integration
# ============================================================================

class TestSelectModeIntegration:
    """Tests 26-27: select_mode signature & force_mode."""

    @pytest.fixture()
    def router(self) -> ModeRouter:
        return ModeRouter()

    # 26. select_mode takes raw_input and subtasks, returns ReactMode
    def test_select_mode_signature(self, router: ModeRouter):
        result = router.select_mode("hello", [])
        assert isinstance(result, ReactMode)

    # 27. force_mode overrides
    def test_force_mode_overrides(self, router: ModeRouter):
        subtasks = [
            {"id": "1", "agent": "file_agent", "action": "list_files", "params": {}},
            {"id": "2", "agent": "web_agent", "action": "search_web", "params": {}},
            {"id": "3", "agent": "doc_agent", "action": "summarize", "params": {}},
        ]
        # Without force, this would be PLAN_AND_ACT or higher
        mode = router.select_mode("do stuff", subtasks, force_mode=ReactMode.BY_ORDER)
        assert mode == ReactMode.BY_ORDER


# ============================================================================
# 28-30. Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests 28-30: Edge cases."""

    @pytest.fixture()
    def router(self) -> ModeRouter:
        return ModeRouter()

    # 28. Empty subtasks -> BY_ORDER
    def test_empty_subtasks(self, router: ModeRouter):
        assert router.select_mode("do something", []) == ReactMode.BY_ORDER

    # 29. None input -> BY_ORDER
    def test_none_input(self, router: ModeRouter):
        assert router.select_mode(None, []) == ReactMode.BY_ORDER

    # 30. Empty string input -> BY_ORDER
    def test_empty_string_input(self, router: ModeRouter):
        assert router.select_mode("", []) == ReactMode.BY_ORDER
