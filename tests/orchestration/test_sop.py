"""Tests for the SOP (Standard Operating Procedure) Engine — Phase 2B.3."""

import pytest
from core.orchestration.sop import (
    Phase,
    PhaseResult,
    RecoveryAction,
    SOPExecutor,
    SOPResult,
)


# ---------------------------------------------------------------------------
# Phase enum
# ---------------------------------------------------------------------------

class TestPhaseEnum:
    """1-2: Phase enum basics."""

    def test_seven_phases_exist(self):
        names = [p.name for p in Phase]
        assert names == [
            "PARSE", "PLAN", "VALIDATE", "PREVIEW",
            "EXECUTE", "VERIFY", "REPORT",
        ]

    def test_phases_have_defined_order(self):
        ordered = list(Phase)
        for earlier, later in zip(ordered, ordered[1:]):
            assert earlier.value < later.value


# ---------------------------------------------------------------------------
# PhaseResult model
# ---------------------------------------------------------------------------

class TestPhaseResult:
    """3-4: PhaseResult data model."""

    def test_contains_required_fields(self):
        pr = PhaseResult(
            phase=Phase.PARSE,
            status="success",
            output={"intent": "create file"},
            duration_ms=42,
        )
        assert pr.phase is Phase.PARSE
        assert pr.status == "success"
        assert pr.output == {"intent": "create file"}
        assert pr.duration_ms == 42

    def test_optional_error_message(self):
        pr = PhaseResult(
            phase=Phase.EXECUTE,
            status="error",
            output=None,
            duration_ms=10,
            error_message="boom",
        )
        assert pr.error_message == "boom"

    def test_serialization_roundtrip(self):
        pr = PhaseResult(
            phase=Phase.PLAN,
            status="success",
            output=[1, 2, 3],
            duration_ms=7,
        )
        data = pr.model_dump()
        restored = PhaseResult.model_validate(data)
        assert restored.phase is Phase.PLAN
        assert restored.status == pr.status
        assert restored.output == pr.output
        assert restored.duration_ms == pr.duration_ms


# ---------------------------------------------------------------------------
# SOPExecutor — Phase Transitions (5-10)
# ---------------------------------------------------------------------------

class TestPhaseTransitions:

    def test_starts_at_parse(self):
        ex = SOPExecutor()
        assert ex.current_phase is Phase.PARSE

    def test_advances_to_next_phase_on_success(self):
        ex = SOPExecutor()
        ex.register_handler(Phase.PARSE, lambda inp, ctx: "parsed")
        ex.register_handler(Phase.PLAN, lambda inp, ctx: "planned")
        # Run only the first two phases to check advancement.
        # We'll rely on run() stopping on missing handlers (skipped).
        result = ex.run("hello")
        # After PARSE succeeds, PLAN should have been reached.
        phase_names = [pr.phase for pr in result.phases]
        assert Phase.PARSE in phase_names
        assert Phase.PLAN in phase_names
        parse_r = result.get_phase(Phase.PARSE)
        assert parse_r.status == "success"

    def test_cannot_skip_phases(self):
        """Phases must execute in order; you cannot jump from PARSE to EXECUTE."""
        ex = SOPExecutor()
        # Only register PARSE and EXECUTE — intermediate phases should still
        # appear (as skipped) between them.
        ex.register_handler(Phase.PARSE, lambda inp, ctx: "parsed")
        ex.register_handler(Phase.EXECUTE, lambda inp, ctx: "executed")
        result = ex.run("go")
        phase_names = [pr.phase for pr in result.phases]
        # Every phase up to and including EXECUTE must appear in order.
        assert phase_names[:5] == [
            Phase.PARSE, Phase.PLAN, Phase.VALIDATE, Phase.PREVIEW, Phase.EXECUTE,
        ]
        # Intermediate unregistered phases are skipped, not omitted.
        assert result.get_phase(Phase.PLAN).status == "skipped"
        assert result.get_phase(Phase.VALIDATE).status == "skipped"

    def test_can_go_backwards_on_error_replan(self):
        """EXECUTE fails -> error handler returns REPLAN -> back to PLAN."""
        call_counts: dict[str, int] = {"plan": 0, "execute": 0}

        def plan_handler(inp, ctx):
            call_counts["plan"] += 1
            return "plan-v" + str(call_counts["plan"])

        def execute_handler(inp, ctx):
            call_counts["execute"] += 1
            if call_counts["execute"] == 1:
                raise RuntimeError("transient failure")
            return "done"

        ex = SOPExecutor()
        ex.register_handler(Phase.PARSE, lambda inp, ctx: inp)
        ex.register_handler(Phase.PLAN, plan_handler)
        ex.register_handler(Phase.EXECUTE, execute_handler)
        ex.register_error_handler(lambda pr: RecoveryAction.REPLAN)
        result = ex.run("data")
        # Plan should have been called twice (original + replan).
        assert call_counts["plan"] >= 2
        assert result.overall_status == "success"

    def test_current_phase_property(self):
        ex = SOPExecutor()
        assert ex.current_phase is Phase.PARSE

    def test_is_complete_after_report(self):
        ex = SOPExecutor()
        for phase in Phase:
            ex.register_handler(phase, lambda inp, ctx: inp)
        result = ex.run("x")
        assert ex.is_complete is True
        assert result.succeeded is True

    def test_is_not_complete_before_report(self):
        ex = SOPExecutor()
        ex.register_handler(Phase.PARSE, lambda inp, ctx: (_ for _ in ()).throw(RuntimeError("fail")))
        ex.register_error_handler(lambda pr: RecoveryAction.ABORT)
        result = ex.run("x")
        assert ex.is_complete is False


# ---------------------------------------------------------------------------
# Phase Handlers (11-14)
# ---------------------------------------------------------------------------

class TestPhaseHandlers:

    def test_register_handler(self):
        ex = SOPExecutor()
        handler = lambda inp, ctx: "ok"
        ex.register_handler(Phase.PARSE, handler)
        # Internal check — handler is stored.
        assert ex._handlers[Phase.PARSE] is handler

    def test_handler_receives_input_returns_phase_result(self):
        received = {}

        def handler(inp, ctx):
            received["inp"] = inp
            return "output"

        ex = SOPExecutor()
        ex.register_handler(Phase.PARSE, handler)
        result = ex.run("my_input")
        assert received["inp"] == "my_input"
        pr = result.get_phase(Phase.PARSE)
        assert pr.status == "success"
        assert pr.output == "output"

    def test_missing_handler_auto_skips(self):
        ex = SOPExecutor()
        # No handlers at all — every phase should be skipped.
        result = ex.run("x")
        for pr in result.phases:
            assert pr.status == "skipped"

    def test_handler_exception_converted_to_error(self):
        def bad_handler(inp, ctx):
            raise ValueError("oh no")

        ex = SOPExecutor()
        ex.register_handler(Phase.PARSE, bad_handler)
        result = ex.run("x")
        pr = result.get_phase(Phase.PARSE)
        assert pr.status == "error"
        assert "oh no" in pr.error_message


# ---------------------------------------------------------------------------
# Execution (15-18)
# ---------------------------------------------------------------------------

class TestExecution:

    def test_run_executes_all_phases_returns_sop_result(self):
        ex = SOPExecutor()
        for phase in Phase:
            ex.register_handler(phase, lambda inp, ctx, p=phase: f"{p.name}-done")
        result = ex.run("start")
        assert isinstance(result, SOPResult)
        assert len(result.phases) == len(Phase)

    def test_run_stops_on_first_error(self):
        ex = SOPExecutor()
        ex.register_handler(Phase.PARSE, lambda inp, ctx: "ok")
        ex.register_handler(Phase.PLAN, lambda inp, ctx: (_ for _ in ()).throw(RuntimeError("fail")))
        ex.register_handler(Phase.VALIDATE, lambda inp, ctx: "should not run")
        result = ex.run("go")
        phases_executed = [pr.phase for pr in result.phases]
        assert Phase.PARSE in phases_executed
        assert Phase.PLAN in phases_executed
        # VALIDATE should NOT appear because we stopped on PLAN error.
        assert Phase.VALIDATE not in phases_executed
        assert result.overall_status == "error"

    def test_run_skips_preview_when_not_needed(self):
        ex = SOPExecutor()
        for phase in Phase:
            ex.register_handler(phase, lambda inp, ctx, p=phase: f"{p.name}")
        result = ex.run("go", skip_preview=True)
        pr = result.get_phase(Phase.PREVIEW)
        assert pr.status == "skipped"

    def test_each_phase_receives_previous_output(self):
        outputs = []

        def make_handler(phase):
            def handler(inp, ctx):
                outputs.append((phase.name, inp))
                return f"{phase.name}:{inp}"
            return handler

        ex = SOPExecutor()
        for phase in Phase:
            ex.register_handler(phase, make_handler(phase))
        ex.run("seed")
        # PARSE receives initial input.
        assert outputs[0] == ("PARSE", "seed")
        # PLAN receives output of PARSE.
        assert outputs[1] == ("PLAN", "PARSE:seed")


# ---------------------------------------------------------------------------
# SOPResult (19-21)
# ---------------------------------------------------------------------------

class TestSOPResult:

    def test_sop_result_fields(self):
        pr = PhaseResult(phase=Phase.PARSE, status="success", output="x", duration_ms=5)
        sr = SOPResult(phases=[pr], overall_status="success", total_duration_ms=5)
        assert sr.phases == [pr]
        assert sr.overall_status == "success"
        assert sr.total_duration_ms == 5

    def test_get_phase(self):
        pr1 = PhaseResult(phase=Phase.PARSE, status="success", output="a", duration_ms=1)
        pr2 = PhaseResult(phase=Phase.PLAN, status="success", output="b", duration_ms=2)
        sr = SOPResult(phases=[pr1, pr2], overall_status="success", total_duration_ms=3)
        assert sr.get_phase(Phase.PLAN) is pr2

    def test_get_phase_returns_none_for_missing(self):
        sr = SOPResult(phases=[], overall_status="error", total_duration_ms=0)
        assert sr.get_phase(Phase.VERIFY) is None

    def test_succeeded_property(self):
        sr_ok = SOPResult(phases=[], overall_status="success", total_duration_ms=0)
        sr_err = SOPResult(phases=[], overall_status="error", total_duration_ms=0)
        assert sr_ok.succeeded is True
        assert sr_err.succeeded is False


# ---------------------------------------------------------------------------
# Preview Skip Logic (22-23)
# ---------------------------------------------------------------------------

class TestPreviewSkipLogic:

    def test_needs_preview_with_destructive_action(self):
        subtasks = [{"action": "delete", "target": "/tmp/x"}]
        assert SOPExecutor.needs_preview(subtasks) is True

    def test_needs_preview_with_move_action(self):
        subtasks = [{"action": "move", "src": "a", "dst": "b"}]
        assert SOPExecutor.needs_preview(subtasks) is True

    def test_needs_preview_with_large_batch(self):
        subtasks = [{"action": "create"}] * 6
        assert SOPExecutor.needs_preview(subtasks) is True

    def test_no_preview_for_safe_small_batch(self):
        subtasks = [{"action": "create"}, {"action": "update"}]
        assert SOPExecutor.needs_preview(subtasks) is False

    def test_preview_phase_skipped_when_not_needed(self):
        ex = SOPExecutor()
        for phase in Phase:
            ex.register_handler(phase, lambda inp, ctx, p=phase: p.name)
        result = ex.run("go", skip_preview=True)
        assert result.get_phase(Phase.PREVIEW).status == "skipped"


# ---------------------------------------------------------------------------
# Phase Context (24-26)
# ---------------------------------------------------------------------------

class TestPhaseContext:

    def test_executor_accepts_context(self):
        ctx = {"user": "alice"}
        ex = SOPExecutor(context=ctx)
        assert ex.context["user"] == "alice"

    def test_context_passed_to_handlers(self):
        seen_ctx = {}

        def handler(inp, ctx):
            seen_ctx.update(ctx)
            return "ok"

        ex = SOPExecutor(context={"key": "val"})
        ex.register_handler(Phase.PARSE, handler)
        ex.run("x")
        assert seen_ctx["key"] == "val"

    def test_handler_can_modify_context(self):
        def parse_handler(inp, ctx):
            ctx["parsed"] = True
            return "parsed"

        def plan_handler(inp, ctx):
            return ctx.get("parsed", False)

        ex = SOPExecutor(context={})
        ex.register_handler(Phase.PARSE, parse_handler)
        ex.register_handler(Phase.PLAN, plan_handler)
        result = ex.run("x")
        assert result.get_phase(Phase.PLAN).output is True


# ---------------------------------------------------------------------------
# Error Recovery (27-31)
# ---------------------------------------------------------------------------

class TestErrorRecovery:

    def test_on_error_callback_called_on_failure(self):
        errors = []

        def on_err(pr):
            errors.append(pr)
            return RecoveryAction.ABORT

        ex = SOPExecutor()
        ex.register_handler(Phase.PARSE, lambda i, c: (_ for _ in ()).throw(RuntimeError("x")))
        ex.register_error_handler(on_err)
        ex.run("go")
        assert len(errors) == 1
        assert errors[0].phase is Phase.PARSE

    def test_retry_reruns_same_phase(self):
        attempts = {"count": 0}

        def flaky(inp, ctx):
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise RuntimeError("transient")
            return "ok"

        def recovery(pr):
            if pr.phase is Phase.PARSE:
                return RecoveryAction.RETRY
            return RecoveryAction.ABORT

        ex = SOPExecutor()
        ex.register_handler(Phase.PARSE, flaky)
        ex.register_error_handler(recovery)
        result = ex.run("go")
        assert attempts["count"] == 2
        assert result.get_phase(Phase.PARSE).status == "success"

    def test_replan_goes_back_to_plan(self):
        plan_calls = {"n": 0}

        def plan_h(inp, ctx):
            plan_calls["n"] += 1
            return "plan"

        execute_calls = {"n": 0}

        def execute_h(inp, ctx):
            execute_calls["n"] += 1
            if execute_calls["n"] == 1:
                raise RuntimeError("fail first time")
            return "done"

        def recovery(pr):
            if pr.phase is Phase.EXECUTE and execute_calls["n"] == 1:
                return RecoveryAction.REPLAN
            return RecoveryAction.ABORT

        ex = SOPExecutor()
        ex.register_handler(Phase.PARSE, lambda i, c: i)
        ex.register_handler(Phase.PLAN, plan_h)
        ex.register_handler(Phase.EXECUTE, execute_h)
        ex.register_error_handler(recovery)
        result = ex.run("x")
        assert plan_calls["n"] >= 2
        assert result.overall_status == "success"

    def test_abort_stops_execution(self):
        ex = SOPExecutor()
        ex.register_handler(Phase.PARSE, lambda i, c: (_ for _ in ()).throw(RuntimeError("die")))
        ex.register_error_handler(lambda pr: RecoveryAction.ABORT)
        result = ex.run("x")
        assert result.overall_status == "error"
        assert len(result.phases) == 1


# ---------------------------------------------------------------------------
# Event Hooks (32-33)
# ---------------------------------------------------------------------------

class TestEventHooks:

    def test_on_phase_start_called(self):
        started = []
        ex = SOPExecutor()
        ex.on_phase_start = lambda phase, inp: started.append(phase)
        ex.register_handler(Phase.PARSE, lambda i, c: "ok")
        ex.run("go")
        assert Phase.PARSE in started

    def test_on_phase_complete_called(self):
        completed = []
        ex = SOPExecutor()
        ex.on_phase_complete = lambda pr: completed.append(pr)
        ex.register_handler(Phase.PARSE, lambda i, c: "ok")
        ex.run("go")
        assert any(pr.phase is Phase.PARSE for pr in completed)

    def test_on_phase_complete_called_on_failure_too(self):
        completed = []
        ex = SOPExecutor()
        ex.on_phase_complete = lambda pr: completed.append(pr)
        ex.register_handler(Phase.PARSE, lambda i, c: (_ for _ in ()).throw(RuntimeError("x")))
        ex.run("go")
        assert any(pr.phase is Phase.PARSE and pr.status == "error" for pr in completed)
