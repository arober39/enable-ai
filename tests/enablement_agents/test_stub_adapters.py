"""Tests for stub-first adapters (gainsight, gong, vitally, github).

These adapters exist so workflows can name CS / marketing / DevRel tools
without an unknown-tool error. They never report `mode: "real"` — even
when a placeholder credential is set — until HTTP is implemented.
"""

from __future__ import annotations

import pytest

from core.workflow import WorkflowDefinition, WorkflowStep
from enablement_agents.tool_adapters import builtin as _builtin  # noqa: F401
from enablement_agents.tool_adapters import (
    discord,
    discourse,
    gainsight,
    github,
    gong,
    klaviyo,
    marketo,
    vitally,
)
from enablement_agents.tool_adapters.registry import (
    ACTION_CATALOG,
    describe_actions,
    get_adapter,
    list_tools,
)
from enablement_agents.workflow_interpreter import run_workflow


class _FakeCreds:
    def __init__(self, data: dict[str, str]):
        self._d = data

    def get(self, key: str) -> str | None:
        return self._d.get(key)

    def require(self, key: str) -> str:
        v = self.get(key)
        if v is None:
            raise KeyError(key)
        return v


_STUB_TOOLS = [
    (
        gainsight,
        "gainsight",
        "GAINSIGHT_API_KEY",
        "get_account_health",
        {"account_id": "a1"},
        "health",
    ),
    (gong, "gong", "GONG_API_KEY", "search_calls", {"query": "renewal"}, "calls"),
    (
        vitally,
        "vitally",
        "VITALLY_API_KEY",
        "get_account",
        {"account_id": "a1"},
        "account",
    ),
    (github, "github", "GITHUB_TOKEN", "search_issues", {"query": "bug"}, "issues"),
    (
        klaviyo,
        "klaviyo",
        "KLAVIYO_API_KEY",
        "list_campaigns",
        {},
        "campaigns",
    ),
    (marketo, "marketo", "MARKETO_API_KEY", "get_lead", {"email": "a@b.co"}, "lead"),
    (
        discord,
        "discord",
        "DISCORD_BOT_TOKEN",
        "search_messages",
        {"query": "sdk"},
        "messages",
    ),
    (
        discourse,
        "discourse",
        "DISCOURSE_API_KEY",
        "search_topics",
        {"query": "auth"},
        "topics",
    ),
]


@pytest.mark.parametrize("module,tool,cred,action,params,top_key", _STUB_TOOLS)
async def test_missing_creds_returns_stub(module, tool, cred, action, params, top_key):
    out = await module.adapter(action, params, _FakeCreds({}))
    assert out["mode"] == "stub"
    assert out["tool"] == tool
    assert cred in out["reason"]
    assert top_key in out


@pytest.mark.parametrize("module,tool,cred,action,params,top_key", _STUB_TOOLS)
async def test_creds_present_still_stub_http_not_implemented(
    module, tool, cred, action, params, top_key
):
    out = await module.adapter(action, params, _FakeCreds({cred: "placeholder"}))
    assert out["mode"] == "stub", "must never report real without an API call"
    assert out["reason"] == "http_not_implemented"
    assert top_key in out


@pytest.mark.parametrize("module,tool,_cred,action,_params,_key", _STUB_TOOLS)
async def test_unknown_action_is_still_stub(module, tool, _cred, action, _params, _key):
    out = await module.adapter("not_a_real_action", {}, _FakeCreds({}))
    assert out["mode"] == "stub"
    assert "error" in out
    assert tool in out["error"]


def test_stub_adapters_are_registered():
    names = set(list_tools())
    for tool in (
        "gainsight",
        "gong",
        "vitally",
        "github",
        "klaviyo",
        "marketo",
        "discord",
        "discourse",
        "slack",
        "hubspot",
    ):
        assert tool in names
        assert get_adapter(tool) is not None


def test_action_catalog_lists_new_tools():
    catalog = describe_actions()
    assert "get_account_health" in catalog["gainsight"]
    assert "list_ctas" in catalog["gainsight"]
    assert "search_calls" in catalog["gong"]
    assert "get_transcript" in catalog["gong"]
    assert "get_account" in catalog["vitally"]
    assert "list_accounts" in catalog["vitally"]
    assert "get_issue" in catalog["github"]
    assert "search_issues" in catalog["github"]
    assert "list_campaigns" in catalog["klaviyo"]
    assert "get_lead" in catalog["marketo"]
    assert "search_messages" in catalog["discord"]
    assert "search_topics" in catalog["discourse"]
    assert "post_message" in catalog["slack"]
    assert "lookup_contact" in catalog["hubspot"]
    # Catalog and registry stay in lockstep for the new tools.
    for tool in (
        "gainsight",
        "gong",
        "vitally",
        "github",
        "klaviyo",
        "marketo",
        "discord",
        "discourse",
    ):
        assert tool in ACTION_CATALOG


async def test_interpreter_names_stub_tools_without_unknown_error():
    definition = WorkflowDefinition(
        name="cs-health-check",
        description="Name a stub-first tool from a workflow step.",
        role_id="r1",
        recommendation_id="R-001",
        tools_used=["gainsight"],
        steps=[
            WorkflowStep(
                id="health",
                tool="gainsight",
                action="get_account_health",
                params={"account_id": "a1"},
            ),
            WorkflowStep(
                id="done",
                tool="return",
                action="value",
                params={"mode": {"$ref": "steps.health.mode"}},
            ),
        ],
    )
    result = await run_workflow(definition, {}, _FakeCreds({}))
    assert result.ok
    assert result.error is None
    assert result.output["mode"] == "stub"
