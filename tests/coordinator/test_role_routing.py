"""Deterministic tests for Coordinator role-to-subagent routing.

No LLM, no network. Asserts that every role in the registry is registered
as a Coordinator subagent, and that the hub prompt names the non-support
departments so the Coordinator can hand off to them.
"""

from __future__ import annotations

import pytest

from coordinator.agent import _register_subagents
from coordinator.definition import COORDINATOR_SYSTEM_PROMPT
from core.roles import list_roles, load_role
from enablement_agents.role_agent import ROLE_AGENT_MODEL


@pytest.mark.parametrize("role_id", [role.id for role in list_roles()])
def test_role_agent_is_registered(role_id: str) -> None:
    """Each registry role id maps to `{id}_enablement_agent` on the hub."""
    role = load_role(role_id)
    agents = _register_subagents()
    assert role.agent_name in agents
    definition = agents[role.agent_name]
    assert definition.model == ROLE_AGENT_MODEL
    # Prompt body is the role's domain_knowledge.md (shared factory contract).
    domain = role.domain_knowledge_path.read_text(encoding="utf-8")
    assert domain.strip()
    assert domain in definition.prompt


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
