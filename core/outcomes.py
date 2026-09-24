"""Per-user workflow outcomes — the Measure step of Diagnose → Recommend → Execute → Measure.

After a stored workflow runs, we persist whether the recommendation
actually executed: status, duration, per-step tool/action/mode, and the
role / recommendation it belonged to.

Phase 1 single-user-local: a JSON list at
`agent-state/<user_id>/outcomes.json`. Same directory convention as
credentials and workflows. Phase 2+ can swap the backend without
changing call sites.

This is the product-honest measure for now — a local log, not a SaaS
analytics product.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from core.identity import UserContext
from core.state import state_path

logger = logging.getLogger(__name__)

_OUTCOMES_FILE = "outcomes.json"

OutcomeStatus = Literal["ok", "failed", "rolled_back"]


class StepSummary(BaseModel):
    """One executed (or skipped) step, as Measure needs it."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    action: str
    mode: str | None = None
    ok: bool
    error: str | None = None


class OutcomeRecord(BaseModel):
    """One measured workflow run."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    role_id: str = Field(min_length=1)
    recommendation_id: str | None = None
    status: OutcomeStatus
    started_at: datetime
    finished_at: datetime
    duration_ms: int = Field(ge=0)
    step_summaries: list[StepSummary] = Field(default_factory=list)
    error: str | None = None
    escalated: bool | None = None
    escalation_mode: str | None = None
    escalation_source: str | None = None


class _StepLike(Protocol):
    """Duck type matching `StepTrace` without importing the interpreter."""

    tool: str
    action: str
    output: dict[str, Any] | None
    error: str | None


def _path_for(user: UserContext) -> Path:
    return state_path(user, _OUTCOMES_FILE)


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    delta = finished_at - started_at
    return max(0, int(delta.total_seconds() * 1000))


def _mode_from_output(output: dict[str, Any] | None) -> str | None:
    if not output:
        return None
    mode = output.get("mode")
    return mode if isinstance(mode, str) else None


def _error_from_step(output: dict[str, Any] | None, error: str | None) -> str | None:
    if error:
        return error
    if output:
        raw = output.get("error")
        if raw:
            return str(raw)
    return None


def summarize_step(
    *,
    tool: str,
    action: str,
    output: dict[str, Any] | None = None,
    error: str | None = None,
) -> StepSummary:
    """Build a step summary, pulling adapter `mode` / `error` out of `output`."""
    step_error = _error_from_step(output, error)
    return StepSummary(
        tool=tool,
        action=action,
        mode=_mode_from_output(output),
        ok=step_error is None,
        error=step_error,
    )


def step_summaries_from_trace(trace: Sequence[_StepLike]) -> list[StepSummary]:
    """Convert interpreter step traces into Measure summaries."""
    return [
        summarize_step(
            tool=step.tool,
            action=step.action,
            output=step.output,
            error=step.error,
        )
        for step in trace
    ]


def _read(user: UserContext) -> list[OutcomeRecord]:
    path = _path_for(user)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8") or "[]")
    if not isinstance(raw, list):
        logger.warning("outcomes store at %s is not a JSON list; ignoring", path)
        return []
    out: list[OutcomeRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            out.append(OutcomeRecord.model_validate(item))
        except Exception:  # noqa: BLE001 — skip malformed entries
            continue
    return out


def _write(user: UserContext, items: list[OutcomeRecord]) -> None:
    path = _path_for(user)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [item.model_dump(mode="json") for item in items]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def record_outcome(
    user: UserContext,
    *,
    role_id: str,
    recommendation_id: str | None = None,
    status: OutcomeStatus,
    started_at: datetime,
    finished_at: datetime | None = None,
    step_summaries: list[StepSummary] | None = None,
    error: str | None = None,
    escalated: bool | None = None,
    escalation_mode: str | None = None,
    escalation_source: str | None = None,
) -> OutcomeRecord:
    """Persist one workflow-run outcome for `user` and return it."""
    ended = finished_at or datetime.now(UTC)
    record = OutcomeRecord(
        id=f"out_{uuid.uuid4().hex[:12]}",
        user_id=user.user_id,
        role_id=role_id,
        recommendation_id=recommendation_id,
        status=status,
        started_at=started_at,
        finished_at=ended,
        duration_ms=_duration_ms(started_at, ended),
        step_summaries=list(step_summaries or []),
        error=error,
        escalated=escalated,
        escalation_mode=escalation_mode,
        escalation_source=escalation_source,
    )
    items = _read(user)
    items.append(record)
    _write(user, items)
    return record


def list_outcomes(user: UserContext) -> list[OutcomeRecord]:
    """Return this user's outcomes, newest first."""
    return sorted(_read(user), key=lambda r: r.finished_at, reverse=True)


class RecommendationMetrics(BaseModel):
    """Run success, error rate, and real-vs-stub calls for one recommendation."""

    model_config = ConfigDict(extra="forbid")

    role_id: str
    recommendation_id: str | None = None
    runs: int = Field(ge=0)
    successes: int = Field(ge=0)
    failures: int = Field(ge=0)
    rollbacks: int = Field(ge=0)
    success_rate: float = Field(ge=0, le=1)
    error_rate: float = Field(ge=0, le=1)
    real_steps: int = Field(ge=0)
    stub_steps: int = Field(ge=0)
    real_call_rate: float = Field(ge=0, le=1)
    escalation_rate: float = Field(ge=0, le=1)
    installed: bool = False


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def recommendation_metrics(user: UserContext) -> list[RecommendationMetrics]:
    """Aggregate outcomes per (role, recommendation).

    `rolled_back` records count as rollbacks, not as failed runs.
    `real_call_rate` is the share of tool steps that actually called an
    API (`mode == "real"`) versus a stub. `installed` is true when the
    user's stored workflow for that role is still this recommendation.
    """
    from core.workflow_storage import list_workflows

    installed = {workflow.role_id: workflow.recommendation_id for workflow in list_workflows(user)}
    grouped: dict[tuple[str, str | None], list[OutcomeRecord]] = {}
    for role_id, recommendation_id in installed.items():
        grouped.setdefault((role_id, recommendation_id), [])
    for record in _read(user):
        grouped.setdefault((record.role_id, record.recommendation_id), []).append(record)

    metrics: list[RecommendationMetrics] = []
    for (role_id, recommendation_id), records in grouped.items():
        successes = sum(1 for record in records if record.status == "ok")
        failures = sum(1 for record in records if record.status == "failed")
        rollbacks = sum(1 for record in records if record.status == "rolled_back")
        decided = successes + failures
        real_steps = 0
        stub_steps = 0
        labeled = 0
        escalations = 0
        for record in records:
            if record.status == "rolled_back":
                continue
            if record.escalated is not None:
                labeled += 1
                if record.escalated:
                    escalations += 1
            for step in record.step_summaries:
                if step.mode == "real":
                    real_steps += 1
                elif step.mode == "stub":
                    stub_steps += 1
        metrics.append(
            RecommendationMetrics(
                role_id=role_id,
                recommendation_id=recommendation_id,
                runs=decided,
                successes=successes,
                failures=failures,
                rollbacks=rollbacks,
                success_rate=_rate(successes, decided),
                error_rate=_rate(failures, decided),
                real_steps=real_steps,
                stub_steps=stub_steps,
                real_call_rate=_rate(real_steps, real_steps + stub_steps),
                escalation_rate=_rate(escalations, labeled),
                installed=installed.get(role_id) == recommendation_id
                and recommendation_id is not None,
            )
        )
    return sorted(
        metrics,
        key=lambda item: (item.role_id, item.recommendation_id or ""),
    )


class RollbackError(Exception):
    """The installed workflow cannot be rolled back for this recommendation."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def rollback_recommendation(
    user: UserContext,
    role_id: str,
    recommendation_id: str,
) -> OutcomeRecord:
    """Uninstall the workflow installed for this recommendation and record it.

    Refuses to delete a workflow that belongs to a different recommendation.
    """
    from core.workflow_storage import delete_workflow, load_workflow

    definition = load_workflow(user, role_id)
    if definition is None:
        raise RollbackError(
            f"No workflow installed for role {role_id!r}.",
            404,
        )
    if definition.recommendation_id != recommendation_id:
        raise RollbackError(
            f"Installed workflow is recommendation {definition.recommendation_id!r}, "
            f"not {recommendation_id!r}.",
            409,
        )
    delete_workflow(user, role_id)
    now = datetime.now(UTC)
    return record_outcome(
        user,
        role_id=role_id,
        recommendation_id=recommendation_id,
        status="rolled_back",
        started_at=now,
        finished_at=now,
        error=f"uninstalled workflow for recommendation {recommendation_id}",
    )
