"""Required vault keys for a declared tool list."""

from __future__ import annotations

from core.tool_credentials import keys_for_tools, keys_for_workflow, missing_keys


def test_zendesk_needs_three_keys() -> None:
    pairs = keys_for_tools(["zendesk", "slack"])
    assert ("zendesk", "ZENDESK_SUBDOMAIN") in pairs
    assert ("zendesk", "ZENDESK_EMAIL") in pairs
    assert ("zendesk", "ZENDESK_API_TOKEN") in pairs
    assert ("slack", "SLACK_BOT_TOKEN") in pairs


def test_missing_keys_ignores_present_ones() -> None:
    missing = missing_keys(
        ["slack", "hubspot"],
        {"SLACK_BOT_TOKEN"},
    )
    assert missing == ["HUBSPOT_API_KEY"]


def test_llm_steps_require_anthropic_even_if_undeclared() -> None:
    pairs = keys_for_workflow(["llm", "llm", "return"], [])
    assert pairs == [("llm", "ANTHROPIC_API_KEY")]


def test_workflow_keys_include_tool_and_declared() -> None:
    pairs = keys_for_workflow(["slack", "llm"], ["SLACK_BOT_TOKEN", "CUSTOM_TOKEN"])
    assert ("slack", "SLACK_BOT_TOKEN") in pairs
    assert ("llm", "ANTHROPIC_API_KEY") in pairs
    assert ("workflow", "CUSTOM_TOKEN") in pairs
    assert [key for _source, key in pairs].count("SLACK_BOT_TOKEN") == 1


def test_unknown_tool_adds_no_key() -> None:
    assert keys_for_tools(["not_a_tool"]) == []
    assert missing_keys(["not_a_tool"], set()) == []
