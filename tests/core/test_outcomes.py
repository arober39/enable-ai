"""Deterministic tests for the Measure outcome store.

Writes only under tmp_path. No network, no LLM.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from core.identity import UserContext
from core.outcomes import (
    OutcomeRecord,
    RecommendationMetrics,
    RollbackError,
    StepSummary,
    list_outcomes,
    recommendation_metrics,
    record_outcome,
    rollback_recommendation,
    step_summaries_from_trace,
    summarize_step,
)
from core.workflow import WorkflowDefinition, WorkflowStep
from core.workflow_storage import load_workflow, save_workflow


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Route outcome files under tmp_path instead of repo agent-state/."""

    def _state_path(user: UserContext, *parts: str) -> Path:
        return tmp_path.joinpath(user.user_id, *parts)

    monkeypatch.setattr("core.outcomes.state_path", _state_path)
    monkeypatch.setattr("core.workflow_storage.state_path", _state_path)
    return tmp_path


def _user(user_id: str = "alice") -> UserContext:
    return UserContext(user_id=user_id)


def _started() -> datetime:
    return datetime(2026, 9, 23, 15, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_outcome_record_rejects_extra_keys() -> None:
    with pytest.raises(ValidationError):
        OutcomeRecord(
            id="out_abc",
            user_id="alice",
            role_id="support",
            status="ok",
            started_at=_started(),
            finished_at=_started() + timedelta(milliseconds=12),
            duration_ms=12,
            surprise=True,  # type: ignore[call-arg]
        )


def test_outcome_record_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        OutcomeRecord(
            id="out_abc",
            user_id="alice",
            role_id="support",
            status="maybe",  # type: ignore[arg-type]
            started_at=_started(),
            finished_at=_started(),
            duration_ms=0,
        )


# ---------------------------------------------------------------------------
# Step summaries — mode / error extraction
# ---------------------------------------------------------------------------


def test_summarize_step_pulls_adapter_mode() -> None:
    summary = summarize_step(
        tool="intercom",
        action="search_conversations",
        output={"mode": "stub", "results": []},
    )
    assert summary == StepSummary(
        tool="intercom",
        action="search_conversations",
        mode="stub",
        ok=True,
        error=None,
    )


def test_summarize_step_mode_absent_when_not_in_output() -> None:
    summary = summarize_step(tool="return", action="emit", output={"text": "done"})
    assert summary.mode is None
    assert summary.ok is True


def test_summarize_step_adapter_error_in_output() -> None:
    summary = summarize_step(
        tool="zendesk",
        action="get_ticket",
        output={"mode": "real", "error": "missing required param: id"},
    )
    assert summary.mode == "real"
    assert summary.ok is False
    assert summary.error == "missing required param: id"


def test_summarize_step_trace_error_wins() -> None:
    summary = summarize_step(
        tool="llm",
        action="complete",
        output={"mode": "stub"},
        error="RuntimeError: boom",
    )
    assert summary.ok is False
    assert summary.error == "RuntimeError: boom"
    assert summary.mode == "stub"


def test_step_summaries_from_real_step_trace() -> None:
    from enablement_agents.workflow_interpreter import StepTrace

    started = _started()
    ended = started + timedelta(milliseconds=4)
    summaries = step_summaries_from_trace(
        [
            StepTrace(
                id="search",
                tool="intercom",
                action="search_conversations",
                skipped=False,
                started_at=started,
                ended_at=ended,
                params_resolved={"query": "refund"},
                output={"mode": "stub", "results": []},
            )
        ]
    )
    assert summaries == [
        StepSummary(
            tool="intercom",
            action="search_conversations",
            mode="stub",
            ok=True,
            error=None,
        )
    ]


def test_step_summaries_from_trace_duck_types_interpreter_steps() -> None:
    trace = [
        SimpleNamespace(
            tool="intercom",
            action="search_conversations",
            output={"mode": "real", "results": [1]},
            error=None,
        ),
        SimpleNamespace(
            tool="return",
            action="emit",
            output=None,
            error=None,
        ),
    ]
    summaries = step_summaries_from_trace(trace)
    assert summaries[0].mode == "real"
    assert summaries[0].ok is True
    assert summaries[1].mode is None
    assert summaries[1].ok is True


# ---------------------------------------------------------------------------
# Persist + list
# ---------------------------------------------------------------------------


def test_record_and_list_newest_first(isolated_state: Path) -> None:
    user = _user()
    t0 = _started()
    first = record_outcome(
        user,
        role_id="support",
        recommendation_id="R-001",
        status="ok",
        started_at=t0,
        finished_at=t0 + timedelta(milliseconds=40),
        step_summaries=[
            summarize_step(
                tool="intercom",
                action="search_conversations",
                output={"mode": "stub"},
            )
        ],
    )
    second = record_outcome(
        user,
        role_id="support",
        recommendation_id="R-001",
        status="failed",
        started_at=t0 + timedelta(seconds=10),
        finished_at=t0 + timedelta(seconds=10, milliseconds=8),
        error="no adapter registered for tool 'nope'",
    )

    listed = list_outcomes(user)
    assert [r.id for r in listed] == [second.id, first.id]
    assert listed[0].status == "failed"
    assert listed[1].status == "ok"
    assert listed[1].recommendation_id == "R-001"
    assert listed[1].step_summaries[0].mode == "stub"
    assert listed[1].duration_ms == 40
    assert listed[0].error == "no adapter registered for tool 'nope'"


def test_record_computes_duration_ms(isolated_state: Path) -> None:
    started = _started()
    record = record_outcome(
        user=_user(),
        role_id="support",
        status="ok",
        started_at=started,
        finished_at=started + timedelta(seconds=1, milliseconds=250),
    )
    assert record.duration_ms == 1250


def test_record_defaults_finished_at_and_empty_steps(isolated_state: Path) -> None:
    started = datetime.now(UTC) - timedelta(milliseconds=5)
    record = record_outcome(
        user=_user(),
        role_id="support",
        status="failed",
        started_at=started,
        error="RuntimeError: exploded",
    )
    assert record.finished_at >= started
    assert record.step_summaries == []
    assert record.recommendation_id is None
    assert record.error == "RuntimeError: exploded"
    assert record.id.startswith("out_")


def test_users_are_isolated(isolated_state: Path) -> None:
    alice = _user("alice")
    bob = _user("bob")
    t0 = _started()
    record_outcome(
        alice,
        role_id="support",
        status="ok",
        started_at=t0,
        finished_at=t0 + timedelta(milliseconds=1),
    )
    record_outcome(
        bob,
        role_id="support",
        status="failed",
        started_at=t0,
        finished_at=t0 + timedelta(milliseconds=2),
        error="bob failed",
    )

    alice_rows = list_outcomes(alice)
    bob_rows = list_outcomes(bob)
    assert len(alice_rows) == 1
    assert alice_rows[0].user_id == "alice"
    assert alice_rows[0].status == "ok"
    assert len(bob_rows) == 1
    assert bob_rows[0].user_id == "bob"
    assert bob_rows[0].error == "bob failed"


def test_list_empty_when_no_file(isolated_state: Path) -> None:
    assert list_outcomes(_user()) == []


def test_list_skips_malformed_entries(isolated_state: Path) -> None:
    user = _user()
    path = isolated_state / user.user_id / "outcomes.json"
    path.parent.mkdir(parents=True)
    good = record_outcome(
        user,
        role_id="support",
        status="ok",
        started_at=_started(),
        finished_at=_started() + timedelta(milliseconds=3),
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.append({"not": "an outcome"})
    raw.append("skip-me")
    path.write_text(json.dumps(raw), encoding="utf-8")

    listed = list_outcomes(user)
    assert [r.id for r in listed] == [good.id]


def test_list_recovers_from_non_list_file(isolated_state: Path) -> None:
    user = _user()
    path = isolated_state / user.user_id / "outcomes.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"oops": true}', encoding="utf-8")
    assert list_outcomes(user) == []


def _workflow(recommendation_id: str = "R-001") -> WorkflowDefinition:
    return WorkflowDefinition(
        name="health",
        description="installed runtime",
        role_id="customer_success",
        recommendation_id=recommendation_id,
        steps=[
            WorkflowStep(
                id="health",
                tool="gainsight",
                action="get_account_health",
                params={"account_id": "a1"},
            )
        ],
    )


def test_metrics_rates_ignore_rollbacks_and_count_real_calls(isolated_state: Path) -> None:
    user = _user()
    t0 = _started()
    record_outcome(
        user,
        role_id="customer_success",
        recommendation_id="R-001",
        status="ok",
        started_at=t0,
        finished_at=t0 + timedelta(milliseconds=10),
        step_summaries=[
            StepSummary(tool="gainsight", action="get_account_health", mode="real", ok=True)
        ],
    )
    record_outcome(
        user,
        role_id="customer_success",
        recommendation_id="R-001",
        status="failed",
        started_at=t0,
        finished_at=t0 + timedelta(milliseconds=20),
        step_summaries=[
            StepSummary(tool="gainsight", action="get_account_health", mode="stub", ok=False)
        ],
        error="adapter failed",
    )
    record_outcome(
        user,
        role_id="customer_success",
        recommendation_id="R-001",
        status="rolled_back",
        started_at=t0,
        finished_at=t0,
        error="uninstalled",
    )

    metrics = recommendation_metrics(user)
    assert len(metrics) == 1
    row = metrics[0]
    assert isinstance(row, RecommendationMetrics)
    assert row.runs == 2
    assert row.successes == 1
    assert row.failures == 1
    assert row.rollbacks == 1
    assert row.success_rate == 0.5
    assert row.error_rate == 0.5
    assert row.real_steps == 1
    assert row.stub_steps == 1
    assert row.real_call_rate == 0.5
    assert row.installed is False


def test_installed_workflow_is_measurable_before_any_run(isolated_state: Path) -> None:
    user = _user()
    save_workflow(user, _workflow("R-001"))
    metrics = recommendation_metrics(user)
    assert len(metrics) == 1
    assert metrics[0].installed is True
    assert metrics[0].runs == 0
    assert metrics[0].recommendation_id == "R-001"


def test_rollback_uninstalls_matching_recommendation(isolated_state: Path) -> None:
    user = _user()
    save_workflow(user, _workflow("R-001"))
    record = rollback_recommendation(user, "customer_success", "R-001")
    assert record.status == "rolled_back"
    assert load_workflow(user, "customer_success") is None
    metrics = recommendation_metrics(user)
    assert metrics[0].installed is False
    assert metrics[0].rollbacks == 1


def test_rollback_refuses_a_different_recommendation(isolated_state: Path) -> None:
    user = _user()
    save_workflow(user, _workflow("R-001"))
    with pytest.raises(RollbackError) as exc:
        rollback_recommendation(user, "customer_success", "R-999")
    assert exc.value.status_code == 409
    assert load_workflow(user, "customer_success") is not None


def test_rollback_missing_workflow(isolated_state: Path) -> None:
    with pytest.raises(RollbackError) as exc:
        rollback_recommendation(_user(), "customer_success", "R-001")
    assert exc.value.status_code == 404


def test_store_path_mirrors_credentials_convention(isolated_state: Path) -> None:
    user = _user("local")
    t0 = _started()
    record_outcome(
        user,
        role_id="support",
        status="ok",
        started_at=t0,
        finished_at=t0 + timedelta(milliseconds=1),
    )
    stored = isolated_state / "local" / "outcomes.json"
    assert stored.exists()
    payload = json.loads(stored.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    OutcomeRecord.model_validate(payload[0])
