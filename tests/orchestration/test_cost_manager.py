"""Tests for CostManager — token usage tracking and budget enforcement."""

import pytest

from core.orchestration.cost_manager import (
    BudgetExceededException,
    CostManager,
    CostReport,
    TokenUsage,
)


# ---------------------------------------------------------------------------
# TokenUsage model
# ---------------------------------------------------------------------------

class TestTokenUsage:
    """Tests 1-2: TokenUsage dataclass behaviour."""

    def test_total_tokens_computed(self):
        """Test 1: total_tokens is sum of input + output."""
        usage = TokenUsage(input_tokens=100, output_tokens=50, cost_usd=0.01, call_count=1)
        assert usage.total_tokens == 150

    def test_add_accumulates(self):
        """Test 2: add() accumulates all fields."""
        a = TokenUsage(input_tokens=100, output_tokens=50, cost_usd=0.01, call_count=1)
        b = TokenUsage(input_tokens=200, output_tokens=100, cost_usd=0.02, call_count=1)
        a.add(b)
        assert a.input_tokens == 300
        assert a.output_tokens == 150
        assert a.total_tokens == 450
        assert a.cost_usd == pytest.approx(0.03)
        assert a.call_count == 2


# ---------------------------------------------------------------------------
# CostReport model
# ---------------------------------------------------------------------------

class TestCostReport:
    """Tests 3-4: CostReport dataclass behaviour."""

    def test_cost_report_fields(self):
        """Test 3: CostReport contains expected fields."""
        report = CostReport(
            total_spent_usd=0.05,
            total_input_tokens=1000,
            total_output_tokens=500,
            by_model={"claude-sonnet-4": TokenUsage(1000, 500, 0.05, 2)},
            by_task={"task-1": TokenUsage(1000, 500, 0.05, 2)},
            call_count=2,
        )
        assert report.total_spent_usd == 0.05
        assert report.total_input_tokens == 1000
        assert report.total_output_tokens == 500
        assert "claude-sonnet-4" in report.by_model
        assert "task-1" in report.by_task
        assert report.call_count == 2

    def test_to_dict_serialization(self):
        """Test 4: to_dict() returns a plain dict."""
        report = CostReport(
            total_spent_usd=0.05,
            total_input_tokens=1000,
            total_output_tokens=500,
            by_model={},
            by_task={},
            call_count=1,
        )
        d = report.to_dict()
        assert isinstance(d, dict)
        assert d["total_spent_usd"] == 0.05
        assert d["call_count"] == 1


# ---------------------------------------------------------------------------
# Budget Management
# ---------------------------------------------------------------------------

class TestBudgetManagement:
    """Tests 5-9: Budget initialization and checking."""

    def test_no_budget_unlimited(self):
        """Test 5: No budget means check_budget always True."""
        cm = CostManager()
        assert cm.check_budget(999999.0) is True

    def test_under_budget_returns_true(self):
        """Test 6: Under budget returns True."""
        cm = CostManager(budget=10.0)
        assert cm.check_budget(5.0) is True

    def test_over_budget_returns_false(self):
        """Test 7: Exceeding budget returns False."""
        cm = CostManager(budget=10.0)
        cm.record_usage("m", 100, 50, 8.0)
        assert cm.check_budget(5.0) is False

    def test_remaining_budget_property(self):
        """Test 8: remaining_budget reflects usage."""
        cm = CostManager(budget=10.0)
        cm.record_usage("m", 100, 50, 3.0)
        assert cm.remaining_budget == pytest.approx(7.0)

    def test_zero_budget_rejects_nonzero(self):
        """Test 9: Budget of 0 rejects any non-zero cost."""
        cm = CostManager(budget=0.0)
        assert cm.check_budget(0.001) is False


# ---------------------------------------------------------------------------
# Recording Usage
# ---------------------------------------------------------------------------

class TestRecordUsage:
    """Tests 10-14: Usage recording."""

    def test_record_usage_tracks(self):
        """Test 10: Single record_usage tracked correctly."""
        cm = CostManager()
        cm.record_usage("claude-sonnet-4", 1000, 500, 0.01)
        report = cm.get_report()
        assert report.total_spent_usd == pytest.approx(0.01)
        assert report.total_input_tokens == 1000
        assert report.total_output_tokens == 500

    def test_same_model_accumulates(self):
        """Test 11: Multiple calls to same model accumulate."""
        cm = CostManager()
        cm.record_usage("claude-sonnet-4", 100, 50, 0.01)
        cm.record_usage("claude-sonnet-4", 200, 100, 0.02)
        report = cm.get_report()
        assert report.by_model["claude-sonnet-4"].input_tokens == 300
        assert report.by_model["claude-sonnet-4"].call_count == 2

    def test_multiple_models_separate(self):
        """Test 12: Different models tracked separately."""
        cm = CostManager()
        cm.record_usage("claude-sonnet-4", 100, 50, 0.01)
        cm.record_usage("gpt-4o", 200, 100, 0.02)
        report = cm.get_report()
        assert "claude-sonnet-4" in report.by_model
        assert "gpt-4o" in report.by_model
        assert report.by_model["claude-sonnet-4"].input_tokens == 100
        assert report.by_model["gpt-4o"].input_tokens == 200

    def test_task_id_tracking(self):
        """Test 13: record_usage with task_id tracks per-task."""
        cm = CostManager()
        cm.record_usage("m", 100, 50, 0.01, task_id="task-1")
        cm.record_usage("m", 200, 100, 0.02, task_id="task-1")
        report = cm.get_report()
        assert "task-1" in report.by_task
        assert report.by_task["task-1"].cost_usd == pytest.approx(0.03)

    def test_record_usage_updates_total(self):
        """Test 14: record_usage updates total spent."""
        cm = CostManager(budget=10.0)
        cm.record_usage("m", 100, 50, 2.5)
        cm.record_usage("m", 100, 50, 1.5)
        assert cm.remaining_budget == pytest.approx(6.0)


# ---------------------------------------------------------------------------
# Cost Estimation
# ---------------------------------------------------------------------------

class TestCostEstimation:
    """Tests 15-18: Cost estimation logic."""

    def test_estimate_cost_returns_float(self):
        """Test 15: estimate_cost returns a USD float."""
        cm = CostManager()
        cost = cm.estimate_cost("claude-sonnet-4", 1_000_000, 1_000_000)
        assert isinstance(cost, float)
        assert cost > 0

    def test_known_model_pricing(self):
        """Test 16: Default pricing for known models."""
        cm = CostManager()
        # claude-sonnet-4: $3/1M in, $15/1M out
        assert cm.estimate_cost("claude-sonnet-4", 1_000_000, 0) == pytest.approx(3.0)
        assert cm.estimate_cost("claude-sonnet-4", 0, 1_000_000) == pytest.approx(15.0)
        # claude-haiku: $0.25/1M in, $1.25/1M out
        assert cm.estimate_cost("claude-haiku", 1_000_000, 0) == pytest.approx(0.25)
        assert cm.estimate_cost("claude-haiku", 0, 1_000_000) == pytest.approx(1.25)
        # gpt-4o: $2.50/1M in, $10/1M out
        assert cm.estimate_cost("gpt-4o", 1_000_000, 0) == pytest.approx(2.50)
        assert cm.estimate_cost("gpt-4o", 0, 1_000_000) == pytest.approx(10.0)

    def test_unknown_model_default_pricing(self):
        """Test 17: Unknown model uses default pricing ($1/$3)."""
        cm = CostManager()
        assert cm.estimate_cost("unknown-model", 1_000_000, 0) == pytest.approx(1.0)
        assert cm.estimate_cost("unknown-model", 0, 1_000_000) == pytest.approx(3.0)

    def test_custom_pricing(self):
        """Test 18: Custom pricing can be registered."""
        cm = CostManager()
        cm.register_pricing("my-model", input_price_per_million=5.0, output_price_per_million=20.0)
        assert cm.estimate_cost("my-model", 1_000_000, 0) == pytest.approx(5.0)
        assert cm.estimate_cost("my-model", 0, 1_000_000) == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

class TestReporting:
    """Tests 19-22: Report generation."""

    def test_get_report_aggregated(self):
        """Test 19: get_report returns CostReport with all data."""
        cm = CostManager()
        cm.record_usage("m1", 100, 50, 0.01, task_id="t1")
        cm.record_usage("m2", 200, 100, 0.02, task_id="t2")
        report = cm.get_report()
        assert isinstance(report, CostReport)
        assert report.total_spent_usd == pytest.approx(0.03)
        assert report.total_input_tokens == 300
        assert report.total_output_tokens == 150

    def test_get_task_report(self):
        """Test 20: get_task_report returns per-task usage."""
        cm = CostManager()
        cm.record_usage("m", 100, 50, 0.01, task_id="t1")
        task_usage = cm.get_task_report("t1")
        assert task_usage is not None
        assert task_usage.cost_usd == pytest.approx(0.01)

    def test_get_task_report_missing(self):
        """Test 20b: get_task_report returns None for unknown task."""
        cm = CostManager()
        assert cm.get_task_report("nonexistent") is None

    def test_report_includes_call_count(self):
        """Test 21: Report includes call_count."""
        cm = CostManager()
        cm.record_usage("m", 100, 50, 0.01)
        cm.record_usage("m", 100, 50, 0.01)
        report = cm.get_report()
        assert report.call_count == 2

    def test_report_by_model(self):
        """Test 22: Report by_model breaks down per model."""
        cm = CostManager()
        cm.record_usage("m1", 100, 50, 0.01)
        cm.record_usage("m2", 200, 100, 0.02)
        report = cm.get_report()
        assert len(report.by_model) == 2
        assert report.by_model["m1"].cost_usd == pytest.approx(0.01)
        assert report.by_model["m2"].cost_usd == pytest.approx(0.02)


# ---------------------------------------------------------------------------
# Budget Enforcement
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:
    """Tests 23-25: Strict mode and utilization."""

    def test_strict_mode_raises(self):
        """Test 23: BudgetExceededException in strict mode."""
        cm = CostManager(budget=1.0, strict=True)
        cm.record_usage("m", 100, 50, 0.5)
        with pytest.raises(BudgetExceededException) as exc_info:
            cm.record_usage("m", 100, 50, 0.8)
        assert exc_info.value.requested_cost == 0.8
        assert exc_info.value.remaining_budget == pytest.approx(0.5)

    def test_non_strict_records_but_check_fails(self):
        """Test 24: Non-strict records usage but check_budget returns False."""
        cm = CostManager(budget=1.0, strict=False)
        cm.record_usage("m", 100, 50, 0.8)
        cm.record_usage("m", 100, 50, 0.5)  # exceeds budget, but allowed
        assert cm.check_budget(0.01) is False

    def test_budget_utilization(self):
        """Test 25: budget_utilization returns ratio 0.0-1.0."""
        cm = CostManager(budget=10.0)
        assert cm.budget_utilization == pytest.approx(0.0)
        cm.record_usage("m", 100, 50, 5.0)
        assert cm.budget_utilization == pytest.approx(0.5)

    def test_budget_utilization_unlimited(self):
        """Test 25b: budget_utilization is 0.0 when unlimited."""
        cm = CostManager()
        cm.record_usage("m", 100, 50, 5.0)
        assert cm.budget_utilization == 0.0


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestReset:
    """Tests 26-27: Reset behaviour."""

    def test_reset_clears_usage_preserves_budget(self):
        """Test 26: reset() clears usage but keeps budget."""
        cm = CostManager(budget=10.0)
        cm.record_usage("m", 100, 50, 5.0, task_id="t1")
        cm.reset()
        report = cm.get_report()
        assert report.total_spent_usd == 0.0
        assert report.call_count == 0
        assert len(report.by_model) == 0
        assert len(report.by_task) == 0
        assert cm.remaining_budget == pytest.approx(10.0)

    def test_reset_budget(self):
        """Test 27: reset_budget changes the budget."""
        cm = CostManager(budget=10.0)
        cm.record_usage("m", 100, 50, 5.0)
        cm.reset_budget(20.0)
        assert cm.remaining_budget == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests 28-30: Edge cases."""

    def test_zero_tokens_report(self):
        """Test 28: Zero tokens — report shows zeros."""
        cm = CostManager()
        report = cm.get_report()
        assert report.total_spent_usd == 0.0
        assert report.total_input_tokens == 0
        assert report.total_output_tokens == 0
        assert report.call_count == 0

    def test_negative_cost_rejected(self):
        """Test 29: Negative cost raises ValueError."""
        cm = CostManager()
        with pytest.raises(ValueError):
            cm.record_usage("m", 100, 50, -0.01)

    def test_none_budget_unlimited(self):
        """Test 30: None budget treated as unlimited."""
        cm = CostManager(budget=None)
        assert cm.check_budget(999999.0) is True
        assert cm.remaining_budget is None
