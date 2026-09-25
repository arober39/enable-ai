"""Deterministic tests for Coordinator role-to-subagent routing.

No LLM, no network. Asserts that every role in the registry is registered
as a Coordinator subagent, and that the hub prompt names the non-support
departments so the Coordinator can hand off to them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from claude_agent_sdk import ClaudeAgentOptions

from coordinator.agent import _register_subagents, run_coordinator
from coordinator.definition import COORDINATOR_SYSTEM_PROMPT
from core.roles import list_roles, load_role
from enablement_agents.role_agent import (
    ENABLEMENT_AGENT_MODEL_ENV,
    ROLE_AGENT_MODEL,
    resolve_role_agent_model,
)
from enablement_agents.support.agent import SupportEnablementAgent


@pytest.mark.parametrize("role_id", [role.id for role in list_roles()])
def test_role_agent_is_registered(role_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each registry role id maps to `{id}_enablement_agent` on the hub."""
    monkeypatch.delenv(ENABLEMENT_AGENT_MODEL_ENV, raising=False)
    role = load_role(role_id)
    agents = _register_subagents()
    assert role.agent_name in agents
    definition = agents[role.agent_name]
    assert definition.model == ROLE_AGENT_MODEL
    assert definition.model == "claude-opus-5-5"
    assert definition.model == resolve_role_agent_model()
    # Prompt body is the role's domain_knowledge.md (shared factory contract).
    domain = role.domain_knowledge_path.read_text(encoding="utf-8")
    assert domain.strip()
    assert domain in definition.prompt


def test_role_agent_model_env_override_selects_sonnet(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENABLEMENT_AGENT_MODEL flips the planner back to Sonnet without a code edit."""
    monkeypatch.setenv(ENABLEMENT_AGENT_MODEL_ENV, "claude-sonnet-4-6")
    role = load_role("support")
    agents = _register_subagents()
    assert agents[role.agent_name].model == "claude-sonnet-4-6"


def test_role_agent_model_blank_env_uses_opus(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whitespace-only override is treated as unset."""
    monkeypatch.setenv(ENABLEMENT_AGENT_MODEL_ENV, "   ")
    assert resolve_role_agent_model() == "claude-opus-5-5"
    role = load_role("support")
    definition = _register_subagents()[role.agent_name]
    assert definition.model == "claude-opus-5-5"


def test_support_direct_plan_path_uses_same_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct support AgentDefinition follows the same env override."""
    monkeypatch.setenv(ENABLEMENT_AGENT_MODEL_ENV, "claude-sonnet-4-6")
    assert SupportEnablementAgent.default().agent_definition.model == "claude-sonnet-4-6"
    monkeypatch.delenv(ENABLEMENT_AGENT_MODEL_ENV, raising=False)
    assert SupportEnablementAgent.default().agent_definition.model == "claude-opus-5-5"


def _stub_mcp_server(*_args: object, **_kwargs: object) -> dict[str, str]:
    """Stand-in for an in-process MCP server. These tests never call tools."""
    return {"type": "sdk"}


async def test_coordinator_session_uses_planner_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The coordinator plan session pins the same model as the role planners."""
    monkeypatch.setenv(ENABLEMENT_AGENT_MODEL_ENV, "claude-sonnet-4-6")
    monkeypatch.setattr("coordinator.agent.create_sdk_mcp_server", _stub_mcp_server)
    monkeypatch.setattr(
        "enablement_agents.support.tools.build_support_mcp_server",
        _stub_mcp_server,
    )
    seen: dict[str, object] = {}

    async def fake_query(*, prompt: str, options: ClaudeAgentOptions) -> AsyncIterator[None]:
        seen["model"] = options.model
        if False:
            yield None

    monkeypatch.setattr("coordinator.agent.query", fake_query)
    with pytest.raises(RuntimeError, match="submit_enablement_plan"):
        await run_coordinator("Enable AI for customer support")
    assert seen["model"] == "claude-sonnet-4-6"


async def test_support_produce_plan_uses_planner_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct produce_plan passes the resolved model into ClaudeAgentOptions."""
    monkeypatch.setenv(ENABLEMENT_AGENT_MODEL_ENV, "claude-sonnet-4-6")
    monkeypatch.setattr("coordinator.agent.create_sdk_mcp_server", _stub_mcp_server)
    monkeypatch.setattr(
        "enablement_agents.support.agent.build_support_mcp_server",
        _stub_mcp_server,
    )
    seen: dict[str, object] = {}

    async def fake_query(*, prompt: str, options: ClaudeAgentOptions) -> AsyncIterator[None]:
        seen["model"] = options.model
        if False:
            yield None

    monkeypatch.setattr("enablement_agents.support.agent.query", fake_query)
    agent = SupportEnablementAgent.default()
    with pytest.raises(RuntimeError, match="without submitting a plan"):
        await agent.produce_plan(agent.parse_stack())
    assert seen["model"] == "claude-sonnet-4-6"


def test_support_enablement_agent_name_still_registered() -> None:
    """Historical Task name must keep working after the factory rewrite."""
    agents = _register_subagents()
    assert "support_enablement_agent" in agents


def test_coordinator_prompt_mentions_other_departments() -> None:
    """Hub prompt must name the non-support departments so routing can fire."""
    prompt = COORDINATOR_SYSTEM_PROMPT.lower()
    assert "customer success" in prompt
    assert "marketing" in prompt
    assert "developer relations" in prompt
    assert "customer_success_enablement_agent" in prompt
    assert "marketing_enablement_agent" in prompt
    assert "devrel_enablement_agent" in prompt
    assert "support_enablement_agent" in prompt
