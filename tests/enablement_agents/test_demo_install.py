"""Demo install uses the reviewed adapter catalog and runs without a model."""

from __future__ import annotations

import pytest

from coordinator.schemas import Recommendation
from core.identity import local_user
from core.roles import load_role
from core.stacks import declared_tool_names
from core.tool_catalog import ToolCapability, load_tool
from enablement_agents.generator.demo_install import (
    install_demo_consolidation,
    install_demo_native_setup,
    install_demo_workflow,
)
from enablement_agents.generator.schemas import GeneratorContext
from enablement_agents.generator.workflow_pipeline import unknown_adapter_actions
from enablement_agents.workflow_interpreter import run_workflow
from ui.api.synthetic import build_synthetic_plan


class _NoCreds:
    def get(self, key: str) -> None:
        return None

    def require(self, key: str) -> str:
        raise KeyError(key)


def _context(role_id: str, kind: str, tools: list[str]) -> GeneratorContext:
    role = load_role(role_id)
    user = local_user()
    caps: list[ToolCapability] = []
    for name in tools:
        cap = load_tool(user, name)
        assert cap is not None
        caps.append(cap)
    return GeneratorContext(
        role_id=role.id,
        role_display_name=role.display_name,
        recommendation=Recommendation(
            id="R-001",
            kind=kind,  # type: ignore[arg-type]
            description=f"Demo {kind} for {role.display_name}",
            tools_affected=tools,
            effort="small",
        ),
        tool_capabilities=caps,
        available_credentials=[],
    )


@pytest.mark.parametrize(
    "role_id",
    ["support", "customer_success", "marketing", "devrel"],
)
async def test_demo_workflow_runs_as_stubs(role_id: str) -> None:
    tools = declared_tool_names(role_id)
    result = install_demo_workflow(_context(role_id, "orchestrate", tools))
    assert result.ok
    assert result.workflow is not None
    assert unknown_adapter_actions(result.workflow) == []
    assert "model-authored" in (result.explanation or "")

    run = await run_workflow(result.workflow, {"inquiry": "demo"}, _NoCreds())
    assert run.ok, run.error
    tool_steps = [step for step in run.trace if step.tool not in {"return", "llm", "set"}]
    assert tool_steps
    for step in tool_steps:
        assert step.output is not None
        assert step.output["mode"] == "stub"


def test_native_setup_does_not_install_a_runtime() -> None:
    result = install_demo_native_setup(_context("support", "use_native_ai", ["zendesk"]))
    assert result.ok
    assert result.artifact_kind == "native_ai_setup"
    assert result.workflow is None
    assert result.native_ai_setup is not None
    assert result.native_ai_setup.primary_tool == "zendesk"


def test_consolidation_does_not_claim_data_moved() -> None:
    result = install_demo_consolidation(
        _context("customer_success", "consolidate", ["gainsight", "vitally"])
    )
    assert result.ok
    assert result.workflow is None
    plan = result.consolidation_plan
    assert plan is not None
    assert plan.source_tool == "gainsight"
    assert plan.target_tool == "vitally"
    assert "did not move" in plan.items_to_migrate[0].notes


def test_synthetic_plan_installs_for_every_role() -> None:
    user = local_user()
    for role_id in ("support", "customer_success", "marketing", "devrel"):
        role = load_role(role_id)
        tools = declared_tool_names(role_id)
        plan = build_synthetic_plan(tools, role, user)
        runtime = next(
            rec
            for rec in plan.recommendations
            if rec.kind in ("orchestrate", "augment_with_custom_ai")
        )
        caps = [load_tool(user, name) for name in tools]
        ctx = GeneratorContext(
            role_id=role.id,
            role_display_name=role.display_name,
            recommendation=runtime,
            tool_capabilities=[cap for cap in caps if cap is not None],
            available_credentials=[],
        )
        installed = install_demo_workflow(ctx)
        assert installed.ok, role_id
        assert installed.workflow is not None
        assert installed.workflow.role_id == role_id
