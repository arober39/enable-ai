"""Deterministic tests for coordinator.schemas Pydantic models.

Each model has at least:
  - a canonical-input acceptance test
  - one or more rejection tests for invalid enum values, missing required
    fields, and extra (forbidden) keys
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from coordinator.schemas import (
    CapabilityFinding,
    CoordinatorRunResult,
    EnablementPlan,
    OrchestratorPRPlan,
    OrchestratorRunResult,
    PlanMetadata,
    Recommendation,
)

# ---------------------------------------------------------------------------
# Builders for canonical-shaped instances
# ---------------------------------------------------------------------------


def _canonical_metadata() -> PlanMetadata:
    return PlanMetadata(
        generated_at=datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC),
        agent_name="support_enablement_agent",
        agent_version="0.1.0",
        stack_file_hash="a" * 64,
        coordinator_session_id="sess-test",
    )


def _canonical_capability_finding() -> CapabilityFinding:
    return CapabilityFinding(
        capability="intent_classification",
        status="covered",
        tools_involved=["intercom"],
        notes=None,
    )


def _canonical_recommendation() -> Recommendation:
    return Recommendation(
        id="R-001",
        kind="orchestrate",
        description="Compose the stack into a unified surface.",
        tools_affected=["intercom", "zendesk", "slack", "hubspot"],
        effort="medium",
        notes=None,
    )


def _canonical_orchestrator_pr_plan() -> OrchestratorPRPlan:
    return OrchestratorPRPlan(
        branch="enable-ai/support",
        files_to_create=["orchestrator.py", "agent_definition.py"],
        mcp_servers_used=["intercom", "zendesk", "slack"],
        mcp_servers_to_generate=["hubspot"],
        ai_configs_to_create=["support-orchestrator-config"],
        env_vars_required=["ANTHROPIC_API_KEY", "LAUNCHDARKLY_SDK_KEY"],
    )


def _canonical_plan() -> EnablementPlan:
    return EnablementPlan(
        department="support",
        summary="Augment Intercom + Zendesk with a custom orchestrator.",
        capability_coverage=[_canonical_capability_finding()],
        recommendations=[_canonical_recommendation()],
        orchestrator_pr_plan=_canonical_orchestrator_pr_plan(),
        metadata=_canonical_metadata(),
    )


# ---------------------------------------------------------------------------
# Canonical acceptance
# ---------------------------------------------------------------------------


def test_plan_metadata_canonical_roundtrip() -> None:
    m = _canonical_metadata()
    dumped = m.model_dump(mode="json")
    rebuilt = PlanMetadata.model_validate(dumped)
    assert rebuilt == m


def test_capability_finding_canonical() -> None:
    f = _canonical_capability_finding()
    assert f.status == "covered"
    assert f.tools_involved == ["intercom"]


def test_recommendation_canonical() -> None:
    r = _canonical_recommendation()
    assert r.kind == "orchestrate"
    assert r.effort == "medium"


def test_orchestrator_pr_plan_canonical() -> None:
    p = _canonical_orchestrator_pr_plan()
    assert "hubspot" in p.mcp_servers_to_generate
    assert "intercom" in p.mcp_servers_used


def test_enablement_plan_canonical() -> None:
    plan = _canonical_plan()
    assert plan.department == "support"
    assert plan.metadata.coordinator_session_id == "sess-test"
    # full JSON round-trip
    dumped = plan.model_dump(mode="json")
    rebuilt = EnablementPlan.model_validate(dumped)
    assert rebuilt == plan


def test_orchestrator_run_result_canonical() -> None:
    result = OrchestratorRunResult(
        department="support",
        files_created=["orchestrator.py"],
        mcp_servers_generated=["hubspot"],
        ai_configs_manifest_path="orchestrators/support/ai_configs.manifest.yaml",
        env_vars_required=["ANTHROPIC_API_KEY"],
        plan_reference=_canonical_metadata(),
    )
    assert result.department == "support"


def test_coordinator_run_result_canonical() -> None:
    result = CoordinatorRunResult(
        plan=_canonical_plan(),
        coordinator_session_id="sess-test",
    )
    assert result.coordinator_session_id == "sess-test"


# ---------------------------------------------------------------------------
# Rejections — invalid enum values, extras, missing required fields
# ---------------------------------------------------------------------------


def test_capability_finding_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        CapabilityFinding(
            capability="x",
            status="nope",  # type: ignore[arg-type]
            tools_involved=[],
            notes=None,
        )


def test_recommendation_rejects_invalid_kind() -> None:
    with pytest.raises(ValidationError):
        Recommendation(
            id="R",
            kind="nope",  # type: ignore[arg-type]
            description="x",
            tools_affected=[],
            effort="small",
            notes=None,
        )


def test_recommendation_rejects_invalid_effort() -> None:
    with pytest.raises(ValidationError):
        Recommendation(
            id="R",
            kind="consolidate",
            description="x",
            tools_affected=[],
            effort="extra-large",  # type: ignore[arg-type]
            notes=None,
        )


def test_enablement_plan_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EnablementPlan(
            department="support",
            summary="x",
            capability_coverage=[],
            recommendations=[],
            orchestrator_pr_plan=None,
            metadata=_canonical_metadata(),
            extra_field="bad",  # type: ignore[call-arg]
        )


def test_plan_metadata_rejects_missing_required() -> None:
    with pytest.raises(ValidationError):
        PlanMetadata.model_validate(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "agent_name": "x",
                # missing agent_version, stack_file_hash, coordinator_session_id
            }
        )


def test_orchestrator_pr_plan_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        OrchestratorPRPlan(
            branch="x",
            files_to_create=[],
            mcp_servers_used=[],
            mcp_servers_to_generate=[],
            ai_configs_to_create=[],
            env_vars_required=[],
            unexpected="bad",  # type: ignore[call-arg]
        )
