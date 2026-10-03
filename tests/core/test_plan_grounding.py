"""Findings and recommendations follow the selected tools, not a role playbook."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from coordinator.schemas import (
    CapabilityFinding,
    EnablementPlan,
    OrchestratorPRPlan,
    PlanMetadata,
    Recommendation,
)
from core.identity import UserContext
from core.plan_grounding import apply_tool_grounding
from core.roles import load_role
from core.tool_catalog import (
    APISurface,
    MCPServerInfo,
    ToolCapability,
    cache_tool,
)
from ui.api.live_runner import _build_system_prompt, _build_user_message
from ui.api.synthetic import build_synthetic_plan

_PLAYBOOK = (
    "tutorial",
    "code sample",
    "documentation gap",
    "docs site",
    "docs-site",
    "blog draft",
    "blog post",
)


def _user() -> UserContext:
    return UserContext(user_id="plan-grounding")


def _cap(
    name: str,
    vendor: str,
    categories: list[str],
    notes: str,
    *,
    mcp: bool = False,
) -> ToolCapability:
    return ToolCapability(
        canonical_name=name,
        vendor=vendor,
        categories=categories,
        native_ai_features=[],
        api_surface=APISurface(
            has_rest_api=True,
            has_webhooks=False,
            rate_limits="unknown",
        ),
        integration_patterns=["orchestrate_into_unified_surface"],
        notes=notes,
        mcp_server=MCPServerInfo(available=mcp),
        source="researched",
    )


def _navan() -> ToolCapability:
    return _cap(
        "navan",
        "Navan",
        ["travel", "expense_management"],
        "Books trips and collects expense reports for card and bank charges.",
    )


def _gmail() -> ToolCapability:
    return _cap(
        "gmail",
        "Gmail",
        ["email"],
        "Sends and reads email.",
        mcp=True,
    )


def _plan_blob(plan: EnablementPlan) -> str:
    chunks = [plan.summary]
    for finding in plan.capability_coverage:
        chunks.append(finding.capability)
        chunks.append(finding.notes or "")
        chunks.extend(finding.tools_involved)
    for rec in plan.recommendations:
        chunks.append(rec.description)
        chunks.append(rec.notes or "")
        chunks.extend(rec.tools_affected)
    return "\n".join(chunks).lower()


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def _state_path(user: UserContext, *parts: str) -> Path:
        return tmp_path.joinpath(user.user_id, *parts)

    monkeypatch.setattr("core.tool_catalog.state_path", _state_path)
    return tmp_path


def test_travel_and_email_plan_follows_those_tools(isolated_state: Path) -> None:
    user = _user()
    cache_tool(user, _navan())
    cache_tool(user, _gmail())
    plan = build_synthetic_plan(["navan", "gmail"], load_role("devrel"), user)
    blob = _plan_blob(plan)
    assert "navan" in blob
    assert "gmail" in blob
    assert "expense" in blob
    assert "trip" in blob or "travel" in blob
    assert "email" in blob
    for theme in _PLAYBOOK:
        assert theme not in blob
    selected = {"navan", "gmail"}
    assert plan.recommendations
    for rec in plan.recommendations:
        assert set(rec.tools_affected) <= selected
        assert rec.tools_affected


def test_different_tools_do_not_reuse_the_travel_workflow(isolated_state: Path) -> None:
    user = _user()
    role = load_role("devrel")
    cache_tool(user, _navan())
    cache_tool(user, _gmail())
    travel = build_synthetic_plan(["navan", "gmail"], role, user)
    code = build_synthetic_plan(["github", "discord"], role, user)
    travel_blob = _plan_blob(travel)
    code_blob = _plan_blob(code)
    assert "expense" in travel_blob
    assert "expense report" not in code_blob
    assert "github" in code_blob
    assert "discord" in code_blob
    assert travel.recommendations[0].description != code.recommendations[0].description


def test_stale_playbook_plan_is_replaced() -> None:
    role = load_role("devrel")
    stale = EnablementPlan(
        department=role.department,
        summary="Draft tutorials and code samples for the docs site.",
        capability_coverage=[
            CapabilityFinding(
                capability="tutorial and blog drafting",
                status="gap",
                tools_involved=["navan", "gmail"],
                notes="The stack cannot draft tutorials.",
            )
        ],
        recommendations=[
            Recommendation(
                id="R-001",
                kind="augment_with_custom_ai",
                description="Draft tutorial code samples and publish them to the docs site.",
                tools_affected=["navan", "gmail"],
                effort="medium",
                notes=None,
            )
        ],
        orchestrator_pr_plan=OrchestratorPRPlan(
            branch="enable-ai/devrel",
            files_to_create=["orchestrator.py"],
            mcp_servers_used=["gmail"],
            mcp_servers_to_generate=["navan"],
            ai_configs_to_create=["devrel-orchestrator-config"],
            env_vars_required=["ANTHROPIC_API_KEY"],
        ),
        metadata=PlanMetadata(
            generated_at=datetime.now(UTC),
            agent_name=role.agent_name,
            agent_version="0.1.0",
            stack_file_hash="abc",
            coordinator_session_id="stale",
        ),
    )
    caps = [_navan(), _gmail()]
    grounded = apply_tool_grounding(stale, caps, role)
    blob = _plan_blob(grounded)
    assert grounded.metadata.coordinator_session_id == "stale"
    for theme in _PLAYBOOK:
        assert theme not in blob
    assert "expense" in blob
    assert "navan" in blob and "gmail" in blob


def test_already_grounded_plan_is_kept(isolated_state: Path) -> None:
    user = _user()
    role = load_role("devrel")
    cache_tool(user, _navan())
    cache_tool(user, _gmail())
    plan = build_synthetic_plan(["navan", "gmail"], role, user)
    kept = apply_tool_grounding(plan, [_navan(), _gmail()], role, synthetic=True)
    assert kept.recommendations[0].description == plan.recommendations[0].description
    assert kept.summary == plan.summary


def test_github_and_discord_findings_relate_the_tools(isolated_state: Path) -> None:
    user = _user()
    role = load_role("devrel")
    plan = build_synthetic_plan(["github", "discord"], role, user)
    related = [finding for finding in plan.capability_coverage if finding.focus == "relationship"]
    assert len(related) >= 2
    notes = "\n".join(finding.notes or "" for finding in related).lower()
    assert "github" in notes and "discord" in notes
    assert "combine" in notes
    assert "workflow" in notes
    assert "1." in notes and "2." in notes
    for finding in related:
        assert set(finding.tools_involved) == {"github", "discord"}
    singles = [finding for finding in plan.capability_coverage if finding.focus == "tool"]
    assert ("github",) in {tuple(finding.tools_involved) for finding in singles}
    assert ("discord",) in {tuple(finding.tools_involved) for finding in singles}
    assert len(plan.recommendations) >= 4
    blob = _plan_blob(plan)
    assert "claude" in blob
    assert "chatgpt" in blob or "openai" in blob
    for rec in plan.recommendations:
        assert set(rec.tools_affected) <= {"github", "discord"}
        assert rec.tools_affected
        assert rec.research
        assert all(item.title and item.evidence and item.source for item in rec.research)


def test_jira_and_discord_workflow_uses_both_tools(isolated_state: Path) -> None:
    user = _user()
    cache_tool(
        user,
        _cap(
            "jira",
            "Jira",
            ["issue_tracking"],
            "Tracks work items. Native AI does not read Discord threads.",
            mcp=True,
        ),
    )
    role = load_role("devrel")
    plan = build_synthetic_plan(["jira", "discord"], role, user)
    related = [finding for finding in plan.capability_coverage if finding.focus == "relationship"]
    notes = "\n".join(finding.notes or "" for finding in related).lower()
    assert "jira" in notes and "discord" in notes
    assert "work item" in notes or "track" in notes
    assert "community" in notes or "thread" in notes
    assert any(len(finding.tools_involved) == 2 for finding in related)


def test_travel_plan_skips_idea_generation(isolated_state: Path) -> None:
    user = _user()
    cache_tool(user, _navan())
    cache_tool(user, _gmail())
    plan = build_synthetic_plan(["navan", "gmail"], load_role("devrel"), user)
    blob = _plan_blob(plan)
    assert "chatgpt" not in blob
    assert "openai" not in blob
    assert any(finding.focus == "relationship" for finding in plan.capability_coverage)
    for theme in _PLAYBOOK:
        assert theme not in blob
    assert plan.recommendations
    assert all(rec.research for rec in plan.recommendations)


def test_live_prompt_is_conditioned_on_selected_tool_ids() -> None:
    role = load_role("devrel")
    message = _build_user_message(
        ["navan", "gmail"], "sess-1", role, _user(), friction="", tasks=None
    )
    system = _build_system_prompt(role)
    assert "navan" in message
    assert "gmail" in message
    assert "Selected tools override the role playbook." in message
    assert "Selected tools override the role playbook." in system
    assert "tutorial and blog drafting" not in message
    assert "code sample generation and verification" not in message
    assert "Compare the declared stack against these" not in message
    assert "relationship" in message
    assert "research" in message
    assert "ChatGPT" in message or "OpenAI" in message
    assert "Claude" in message
    assert "relationship" in system
