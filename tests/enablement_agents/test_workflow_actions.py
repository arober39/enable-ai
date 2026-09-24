"""Install-time check: a workflow may only name reviewed adapter actions."""

from __future__ import annotations

from core.workflow import WorkflowDefinition, WorkflowStep
from enablement_agents.generator.workflow_pipeline import (
    stamp_env_vars,
    unknown_adapter_actions,
)
from enablement_agents.tool_adapters import builtin as _builtin  # noqa: F401


def _definition(*steps: WorkflowStep) -> WorkflowDefinition:
    return WorkflowDefinition(
        name="check",
        description="action catalog check",
        role_id="customer_success",
        recommendation_id="R-001",
        steps=list(steps),
    )


def test_llm_steps_record_the_vault_key_without_a_prompt() -> None:
    definition = _definition(
        WorkflowStep(
            id="brief",
            tool="llm",
            action="complete",
            params={"system": "Summarize.", "user": "{{ request.inquiry }}"},
        ),
        WorkflowStep(id="done", tool="return", action="value", params={"ok": True}),
    )
    stamped = stamp_env_vars(
        definition.model_copy(update={"env_vars_required": []})
    )
    assert stamped.env_vars_required == ["ANTHROPIC_API_KEY"]


def test_known_actions_are_installable() -> None:
    definition = _definition(
        WorkflowStep(
            id="health",
            tool="gainsight",
            action="get_account_health",
            params={"account_id": "a1"},
        ),
        WorkflowStep(id="done", tool="return", action="value", params={"ok": True}),
    )
    assert unknown_adapter_actions(definition) == []


def test_unknown_action_is_rejected() -> None:
    definition = _definition(
        WorkflowStep(id="bad", tool="gainsight", action="delete_account"),
    )
    assert unknown_adapter_actions(definition) == ["gainsight.delete_account"]


def test_unknown_tool_is_rejected() -> None:
    definition = _definition(
        WorkflowStep(id="bad", tool="salesforce", action="get_account"),
    )
    assert unknown_adapter_actions(definition) == ["salesforce.get_account"]
