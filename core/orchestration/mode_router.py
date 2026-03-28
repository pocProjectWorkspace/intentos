"""
IntentOS React Mode Router (Phase 2B.4).

Decides HOW a task gets executed: sequential (BY_ORDER), plan-first
(PLAN_AND_ACT), or dynamic (REACT). Inspired by MetaGPT's react modes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# ReactMode enum
# ---------------------------------------------------------------------------

class ReactMode(str, Enum):
    """Execution strategy for a task."""

    BY_ORDER = "by_order"
    PLAN_AND_ACT = "plan_and_act"
    REACT = "react"


# ---------------------------------------------------------------------------
# ScoringWeights
# ---------------------------------------------------------------------------

@dataclass
class ScoringWeights:
    """Weights for each complexity dimension.  Must sum to ~1.0."""

    token: float = 0.15
    task_type: float = 0.30
    ambiguity: float = 0.25
    context: float = 0.10
    agent_count: float = 0.20


# ---------------------------------------------------------------------------
# ComplexityScore
# ---------------------------------------------------------------------------

@dataclass
class ComplexityScore:
    """Complexity assessment across five dimensions."""

    token_count_score: float
    task_type_score: float
    ambiguity_score: float
    context_depth_score: float
    agent_count_score: float
    weights: ScoringWeights = field(default_factory=ScoringWeights)

    @property
    def total_score(self) -> float:
        return (
            self.token_count_score * self.weights.token
            + self.task_type_score * self.weights.task_type
            + self.ambiguity_score * self.weights.ambiguity
            + self.context_depth_score * self.weights.context
            + self.agent_count_score * self.weights.agent_count
        )


# ---------------------------------------------------------------------------
# ModeRouter
# ---------------------------------------------------------------------------

class ModeRouter:
    """Selects the appropriate ReactMode for a given task."""

    SIMPLE_ACTIONS: Set[str] = {
        "list_files", "read_file", "get_metadata", "get_current_date", "get_disk_usage",
    }
    COMPLEX_ACTIONS: Set[str] = {
        "organize_by_type", "bulk_rename", "research", "summarize", "extract_data",
    }
    AMBIGUITY_MARKERS: Set[str] = {
        "maybe", "perhaps", "not sure", "or", "?", "something like", "kind of", "I think",
    }
    RESEARCH_MARKERS: Set[str] = {
        "find out", "research", "investigate", "look up", "search for", "what is",
    }

    def __init__(
        self,
        weights: Optional[ScoringWeights] = None,
        by_order_threshold: float = 0.3,
        react_threshold: float = 0.7,
    ) -> None:
        self.weights = weights or ScoringWeights()
        self.by_order_threshold = by_order_threshold
        self.react_threshold = react_threshold

    # -- public API ---------------------------------------------------------

    def select_mode(
        self,
        raw_input: Optional[str],
        subtasks: List[Dict],
        force_mode: Optional[ReactMode] = None,
    ) -> ReactMode:
        """Select execution mode for the task."""
        if force_mode is not None:
            return force_mode

        # Edge cases: missing / trivial input
        if not raw_input or not subtasks:
            return ReactMode.BY_ORDER

        # Rule-based overrides (checked before pure scoring)
        override = self._check_rule_overrides(raw_input, subtasks)
        if override is not None:
            return override

        score = self.score_complexity(raw_input, subtasks)
        return self._mode_from_score(score.total_score)

    def score_complexity(
        self, raw_input: Optional[str], subtasks: List[Dict]
    ) -> ComplexityScore:
        """Score the task complexity across five dimensions."""
        safe_input = raw_input or ""
        return ComplexityScore(
            token_count_score=self._score_token_count(safe_input),
            task_type_score=self._score_task_type(subtasks),
            ambiguity_score=self._score_ambiguity(safe_input),
            context_depth_score=self._score_context_depth(safe_input, subtasks),
            agent_count_score=self._score_agent_count(subtasks),
            weights=self.weights,
        )

    # -- rule-based overrides -----------------------------------------------

    def _check_rule_overrides(
        self, raw_input: str, subtasks: List[Dict]
    ) -> Optional[ReactMode]:
        """Apply rule-based overrides before falling back to scoring."""
        lower = raw_input.lower()

        # Ambiguous intent -> REACT
        ambiguity_hits = sum(1 for m in self.AMBIGUITY_MARKERS if m in lower)
        if ambiguity_hits >= 2:
            return ReactMode.REACT

        # Research intent -> REACT
        if any(m in lower for m in self.RESEARCH_MARKERS):
            return ReactMode.REACT

        # Batch operation (>5 subtasks) -> PLAN_AND_ACT
        if len(subtasks) > 5:
            return ReactMode.PLAN_AND_ACT

        # 3+ subtasks with multiple agents -> PLAN_AND_ACT
        if len(subtasks) >= 3:
            agents = {st.get("agent", "") for st in subtasks}
            if len(agents) >= 2:
                return ReactMode.PLAN_AND_ACT

        return None

    # -- internal scoring ---------------------------------------------------

    def _mode_from_score(self, total: float) -> ReactMode:
        if total < self.by_order_threshold:
            return ReactMode.BY_ORDER
        if total > self.react_threshold:
            return ReactMode.REACT
        return ReactMode.PLAN_AND_ACT

    @staticmethod
    def _score_token_count(raw_input: str) -> float:
        """Approximate token count via whitespace split; normalise to 0-1."""
        token_count = len(raw_input.split())
        if token_count < 20:
            return min(token_count / 20.0 * 0.25, 0.25)
        if token_count > 100:
            return min(0.8 + (token_count - 100) / 200.0 * 0.2, 1.0)
        # 20-100 linear ramp 0.25 -> 0.8
        return 0.25 + (token_count - 20) / 80.0 * 0.55

    def _score_task_type(self, subtasks: List[Dict]) -> float:
        """Score based on action complexity of subtasks."""
        if not subtasks:
            return 0.0
        complex_count = 0
        simple_count = 0
        for st in subtasks:
            action = st.get("action", "")
            if action in self.COMPLEX_ACTIONS:
                complex_count += 1
            elif action in self.SIMPLE_ACTIONS:
                simple_count += 1
        total = len(subtasks)
        if total == 0:
            return 0.0
        # Ratio-based: complex actions push score up, simple pull down
        complex_ratio = complex_count / total
        simple_ratio = simple_count / total
        return max(0.0, min(1.0, complex_ratio * 1.0 - simple_ratio * 0.3 + 0.1 * (1 - simple_ratio - complex_ratio)))

    def _score_ambiguity(self, raw_input: str) -> float:
        """Count ambiguity markers in the input."""
        lower = raw_input.lower()
        hits = sum(1 for marker in self.AMBIGUITY_MARKERS if marker in lower)
        # Normalise: 0 hits -> 0, 3+ hits -> ~1.0
        return min(hits / 3.0, 1.0)

    def _score_context_depth(self, raw_input: str, subtasks: List[Dict]) -> float:
        """Heuristic for how much context the task needs."""
        score = 0.0
        # More subtasks -> more context
        n = len(subtasks)
        score += min(n / 6.0, 0.5)
        # Longer input hints at richer context
        tokens = len(raw_input.split())
        score += min(tokens / 200.0, 0.5)
        return min(score, 1.0)

    @staticmethod
    def _score_agent_count(subtasks: List[Dict]) -> float:
        """Score based on number of unique agents."""
        if not subtasks:
            return 0.0
        agents = {st.get("agent", "") for st in subtasks}
        n = len(agents)
        if n <= 1:
            return 0.0
        if n == 2:
            return 0.4
        # 3+ agents
        return min(0.75 + (n - 3) * 0.1, 1.0)
