"""Live-LLM end-to-end tests (`@pytest.mark.live`).

These tests hit a real Claude session via `claude-agent-sdk`. They are:
  - Skipped automatically when ``ANTHROPIC_API_KEY`` is unset (the
    ``pytest_collection_modifyitems`` hook in ``tests/conftest.py``
    installs the skip marker).
  - Excluded from ``make test`` (which passes ``-m "not live"``).
  - Included in ``make test-live`` for explicit, paid runs.

They are the Phase 4.7 and Phase 5.4 smoke tests that were deferred — they
exercise the routed flow end-to-end: the Coordinator delegates to the
Support Enablement Agent, which produces a structured EnablementPlan, then
the agent's ``generate_orchestrator`` materializes a runnable orchestrator
on disk.

Cost note: each test typically runs a 5-15 turn Coordinator + Support
session. Plan for a few cents per `make test-live` invocation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coordinator.agent import run_coordinator
from coordinator.schemas import CoordinatorRunResult, EnablementPlan
from enablement_agents.support.agent import SupportEnablementAgent

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.live


async def test_run_coordinator_produces_valid_enablement_plan() -> None:
    """Full routed flow: Coordinator → Support subagent → EnablementPlan."""
    result = await run_coordinator("Enable AI for customer support")
    assert isinstance(result, CoordinatorRunResult)
    plan = result.plan
    assert isinstance(plan, EnablementPlan)
    assert plan.department == "support"
    assert plan.summary
    assert plan.capability_coverage, "plan should produce at least one capability finding"
    assert plan.recommendations, "plan should produce at least one recommendation"
    # The session id should be non-empty.
    assert result.coordinator_session_id


async def test_produce_plan_directly_validates_against_schema() -> None:
    """Direct invocation of the Support agent (not via Coordinator).

    This exercises ``SupportEnablementAgent.produce_plan`` in isolation —
    bypassing the Coordinator routing. The returned plan must validate
    against the EnablementPlan schema.
    """
    agent = SupportEnablementAgent.default()
    stack = agent.parse_stack()
    plan = await agent.produce_plan(stack)
    # ``produce_plan`` returns a validated EnablementPlan; round-trip via
    # JSON to assert the schema accepts the model's serialized form.
    dumped = plan.model_dump(mode="json")
    rebuilt = EnablementPlan.model_validate(dumped)
    assert rebuilt == plan


async def test_run_coordinator_with_orchestrator_generation() -> None:
    """End-to-end including Phase 5 orchestrator generation.

    The Coordinator's prompt includes a request to also generate the
    runnable orchestrator. The agent's plan must include a populated
    ``orchestrator_pr_plan``. After the Coordinator returns, we invoke
    ``generate_orchestrator`` and verify it produces the runnable tree.
    """
    result = await run_coordinator(
        "Enable AI for customer support, including the runnable orchestrator"
    )
    plan = result.plan
    assert plan.orchestrator_pr_plan is not None, (
        "Coordinator should populate orchestrator_pr_plan when the user "
        "asks for the runnable orchestrator."
    )

    # Run generate_orchestrator with the captured plan.
    agent = SupportEnablementAgent.default()
    orch_result = await agent.generate_orchestrator(plan)
    assert orch_result.department == "support"
    assert orch_result.files_created
    # The generated tree must include the orchestrator runtime entry.
    out = REPO_ROOT / "orchestrators" / "support"
    assert (out / "orchestrator.py").exists()
    assert (out / "prompts" / "v1_baseline.md").exists()
    assert (out / "prompts" / "v2_detailed_responses.md").exists()
    assert (out / "judges" / "factual_accuracy.md").exists()
    assert (out / "ai_configs.manifest.yaml").exists()
