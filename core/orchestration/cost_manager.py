"""CostManager — token usage tracking and budget enforcement.

Inspired by MetaGPT's CostManager pattern. Provides:
- Per-model and per-task token/cost tracking
- Budget limits with optional strict enforcement
- Cost estimation for known and custom model pricing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Default model pricing (USD per 1M tokens)
# ---------------------------------------------------------------------------

MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "claude-haiku": {"input": 0.25, "output": 1.25},
    "gpt-4o": {"input": 2.50, "output": 10.0},
}

_DEFAULT_PRICING = {"input": 1.0, "output": 3.0}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TokenUsage:
    """Tracks token counts and cost for a model or task."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    call_count: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, other: TokenUsage) -> None:
        """Accumulate another TokenUsage into this one."""
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cost_usd += other.cost_usd
        self.call_count += other.call_count


@dataclass
class CostReport:
    """Aggregated cost report."""

    total_spent_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    by_model: Dict[str, TokenUsage] = field(default_factory=dict)
    by_task: Dict[str, TokenUsage] = field(default_factory=dict)
    call_count: int = 0

    def to_dict(self) -> dict:
        return {
            "total_spent_usd": self.total_spent_usd,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "by_model": {
                k: {
                    "input_tokens": v.input_tokens,
                    "output_tokens": v.output_tokens,
                    "total_tokens": v.total_tokens,
                    "cost_usd": v.cost_usd,
                    "call_count": v.call_count,
                }
                for k, v in self.by_model.items()
            },
            "by_task": {
                k: {
                    "input_tokens": v.input_tokens,
                    "output_tokens": v.output_tokens,
                    "total_tokens": v.total_tokens,
                    "cost_usd": v.cost_usd,
                    "call_count": v.call_count,
                }
                for k, v in self.by_task.items()
            },
            "call_count": self.call_count,
        }


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class BudgetExceededException(Exception):
    """Raised when a usage recording would exceed the budget in strict mode."""

    def __init__(self, requested_cost: float, remaining_budget: float, total_spent: float):
        self.requested_cost = requested_cost
        self.remaining_budget = remaining_budget
        self.total_spent = total_spent
        super().__init__(
            f"Budget exceeded: requested ${requested_cost:.4f}, "
            f"remaining ${remaining_budget:.4f}, total spent ${total_spent:.4f}"
        )


# ---------------------------------------------------------------------------
# CostManager
# ---------------------------------------------------------------------------

class CostManager:
    """Tracks token usage across models/tasks and enforces spending limits."""

    def __init__(self, budget: Optional[float] = None, strict: bool = False):
        self._budget = budget
        self._strict = strict
        self._total_spent: float = 0.0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._call_count: int = 0
        self._by_model: Dict[str, TokenUsage] = {}
        self._by_task: Dict[str, TokenUsage] = {}
        self._custom_pricing: Dict[str, Dict[str, float]] = {}

    # -- Budget management --------------------------------------------------

    def check_budget(self, estimated_cost: float) -> bool:
        """Return True if estimated_cost fits within the remaining budget."""
        if self._budget is None:
            return True
        return self._total_spent + estimated_cost <= self._budget

    @property
    def remaining_budget(self) -> Optional[float]:
        if self._budget is None:
            return None
        return self._budget - self._total_spent

    @property
    def budget_utilization(self) -> float:
        """Return 0.0-1.0+ ratio of spent/budget; 0.0 if unlimited."""
        if self._budget is None:
            return 0.0
        if self._budget == 0.0:
            return 0.0 if self._total_spent == 0.0 else 1.0
        return self._total_spent / self._budget

    # -- Recording usage ----------------------------------------------------

    def record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        task_id: Optional[str] = None,
    ) -> None:
        if cost < 0:
            raise ValueError("cost must be non-negative")

        # Strict budget enforcement
        if self._strict and self._budget is not None:
            remaining = self._budget - self._total_spent
            if self._total_spent + cost > self._budget:
                raise BudgetExceededException(cost, remaining, self._total_spent)

        usage = TokenUsage(input_tokens, output_tokens, cost, 1)

        # Totals
        self._total_spent += cost
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._call_count += 1

        # By model
        if model not in self._by_model:
            self._by_model[model] = TokenUsage()
        self._by_model[model].add(usage)

        # By task
        if task_id is not None:
            if task_id not in self._by_task:
                self._by_task[task_id] = TokenUsage()
            self._by_task[task_id].add(usage)

    # -- Cost estimation ----------------------------------------------------

    def estimate_cost(
        self, model: str, estimated_input_tokens: int, estimated_output_tokens: int
    ) -> float:
        pricing = self._custom_pricing.get(
            model, MODEL_PRICING.get(model, _DEFAULT_PRICING)
        )
        input_cost = (estimated_input_tokens / 1_000_000) * pricing["input"]
        output_cost = (estimated_output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def register_pricing(
        self, model: str, input_price_per_million: float, output_price_per_million: float
    ) -> None:
        self._custom_pricing[model] = {
            "input": input_price_per_million,
            "output": output_price_per_million,
        }

    # -- Reporting ----------------------------------------------------------

    def get_report(self) -> CostReport:
        return CostReport(
            total_spent_usd=self._total_spent,
            total_input_tokens=self._total_input_tokens,
            total_output_tokens=self._total_output_tokens,
            by_model=dict(self._by_model),
            by_task=dict(self._by_task),
            call_count=self._call_count,
        )

    def get_task_report(self, task_id: str) -> Optional[TokenUsage]:
        return self._by_task.get(task_id)

    # -- Reset --------------------------------------------------------------

    def reset(self) -> None:
        """Clear all usage data but preserve budget settings."""
        self._total_spent = 0.0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._call_count = 0
        self._by_model.clear()
        self._by_task.clear()

    def reset_budget(self, new_budget: Optional[float]) -> None:
        self._budget = new_budget
