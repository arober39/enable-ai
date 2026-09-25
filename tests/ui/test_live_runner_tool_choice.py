"""Live planner request shape for Opus 5.5 vs models that allow forced tools."""

from __future__ import annotations

from typing import Any

import pytest
from anthropic.types import TextBlock, ThinkingBlock, ToolUseBlock

from coordinator.schemas import EnablementPlan
from core.identity import UserContext
from core.roles import load_role
from enablement_agents.role_agent import ENABLEMENT_AGENT_MODEL_ENV
from ui.api.live_runner import (
    _live_plan_request_shape,
    _model_rejects_forced_tool_choice,
    _schema_allows_strict_tool,
    run_live_plan,
)

_SAMPLING_KEYS = ("thinking", "temperature", "top_p", "top_k")


def _plan_input() -> dict[str, Any]:
    return {
        "department": "support",
        "summary": "Draft the next Intercom reply from the ticket record.",
        "capability_coverage": [
            {
                "capability": "draft the next reply from the Intercom ticket",
                "status": "partial",
                "tools_involved": ["intercom"],
                "notes": None,
            }
        ],
        "recommendations": [
            {
                "id": "R-001",
                "kind": "augment_with_custom_ai",
                "description": "Draft replies in Intercom from the ticket record.",
                "tools_affected": ["intercom"],
                "effort": "medium",
                "notes": None,
            }
        ],
        "orchestrator_pr_plan": {
            "branch": "enable-ai/support",
            "files_to_create": ["orchestrator.py"],
            "mcp_servers_used": ["intercom"],
            "mcp_servers_to_generate": [],
            "ai_configs_to_create": ["support-orchestrator-config"],
            "env_vars_required": ["ANTHROPIC_API_KEY"],
        },
        "metadata": {
            "generated_at": "2026-09-25T00:00:00Z",
            "agent_name": "support_enablement_agent",
            "agent_version": "0.1.0",
            "stack_file_hash": "abc",
            "coordinator_session_id": "sess-tool-choice",
        },
    }


def _tool_use() -> ToolUseBlock:
    return ToolUseBlock(
        id="toolu_plan",
        name="submit_enablement_plan",
        input=_plan_input(),
        type="tool_use",
    )


def _thinking() -> ThinkingBlock:
    return ThinkingBlock(type="thinking", thinking="", signature="sig-keep")


class _Response:
    def __init__(self, content: list[object], stop_reason: str = "end_turn") -> None:
        self.content = content
        self.stop_reason = stop_reason


class _Messages:
    def __init__(self, responses: list[_Response]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("unexpected extra messages.create call")
        return self._responses.pop(0)


class _Client:
    def __init__(self, responses: list[_Response]) -> None:
        self.messages = _Messages(responses)


def _clear_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UI_LIVE_MODEL", raising=False)
    monkeypatch.delenv(ENABLEMENT_AGENT_MODEL_ENV, raising=False)


def _assert_no_sampling(call: dict[str, Any]) -> None:
    for key in _SAMPLING_KEYS:
        assert key not in call


async def _run(monkeypatch: pytest.MonkeyPatch, client: _Client) -> Any:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("ui.api.live_runner.AsyncAnthropic", lambda: client)
    return await run_live_plan(["intercom"], load_role("support"), UserContext(user_id="local"))


def test_opus_55_ids_reject_forced_tool_choice() -> None:
    assert _model_rejects_forced_tool_choice("claude-opus-5-5")
    assert _model_rejects_forced_tool_choice("anthropic.claude-opus-5-5")
    assert _model_rejects_forced_tool_choice("  CLAUDE-OPUS-5-5  ")
    assert _model_rejects_forced_tool_choice("claude-opus-5-5-20260101")
    assert not _model_rejects_forced_tool_choice("claude-opus-5")
    assert not _model_rejects_forced_tool_choice("claude-opus-5-50")
    assert not _model_rejects_forced_tool_choice("claude-opus-4-8")
    assert not _model_rejects_forced_tool_choice("claude-sonnet-4-6")
    assert not _model_rejects_forced_tool_choice("claude-haiku-4-5-20251001")


def test_enablement_plan_schema_allows_strict_tool() -> None:
    schema = EnablementPlan.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["CapabilityFinding"]["additionalProperties"] is False
    assert _schema_allows_strict_tool(schema) is True


def test_open_object_schema_disables_strict_tool() -> None:
    shape = _live_plan_request_shape(
        "claude-opus-5-5",
        {"type": "object", "properties": {"summary": {"type": "string"}}},
    )
    assert shape.tool_choice == {"type": "auto"}
    assert shape.strict is False
    assert shape.output_config == {"effort": "high"}


def test_too_many_optional_fields_disables_strict_tool() -> None:
    properties = {f"field_{index}": {"type": "string"} for index in range(25)}
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": [],
    }
    assert _schema_allows_strict_tool(schema) is False


async def test_opus_request_uses_auto_strict_and_high_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default planner: no forced tool_choice, strict submit tool, effort high."""
    _clear_model_env(monkeypatch)
    client = _Client([_Response([_thinking(), _tool_use()], stop_reason="tool_use")])

    plan = await _run(monkeypatch, client)

    assert len(client.messages.calls) == 1
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["tool_choice"] == {"type": "auto"}
    assert call["max_tokens"] == 16384
    assert call["output_config"] == {"effort": "high"}
    _assert_no_sampling(call)
    tool = call["tools"][0]
    assert tool["name"] == "submit_enablement_plan"
    assert tool["strict"] is True
    assert tool["input_schema"]["additionalProperties"] is False
    assert "prose-only" in call["system"]
    assert "tool choice is automatic" in call["messages"][0]["content"]
    assert plan.metadata.coordinator_session_id == "sess-tool-choice"
    assert isinstance(plan, EnablementPlan)


async def test_sonnet_override_keeps_forced_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_model_env(monkeypatch)
    monkeypatch.setenv(ENABLEMENT_AGENT_MODEL_ENV, "claude-sonnet-4-6")
    client = _Client([_Response([_tool_use()])])

    await _run(monkeypatch, client)

    assert len(client.messages.calls) == 1
    call = client.messages.calls[0]
    assert call["model"] == "claude-sonnet-4-6"
    assert call["tool_choice"] == {"type": "tool", "name": "submit_enablement_plan"}
    assert call["max_tokens"] == 4096
    assert "output_config" not in call
    _assert_no_sampling(call)
    assert "strict" not in call["tools"][0]


async def test_ui_live_model_sonnet_overrides_opus_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENABLEMENT_AGENT_MODEL_ENV, raising=False)
    monkeypatch.setenv("UI_LIVE_MODEL", "claude-sonnet-4-6")
    client = _Client([_Response([_tool_use()])])

    await _run(monkeypatch, client)

    call = client.messages.calls[0]
    assert call["model"] == "claude-sonnet-4-6"
    assert call["tool_choice"]["type"] == "tool"
    assert "strict" not in call["tools"][0]


async def test_opus_retries_once_and_echoes_thinking_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_model_env(monkeypatch)
    first = _Response(
        [_thinking(), TextBlock(type="text", text="Still thinking.", citations=None)],
        stop_reason="max_tokens",
    )
    client = _Client([first, _Response([_thinking(), _tool_use()], stop_reason="tool_use")])

    plan = await _run(monkeypatch, client)

    assert len(client.messages.calls) == 2
    assert client.messages.calls[0]["max_tokens"] == 16384
    assert client.messages.calls[1]["max_tokens"] == 32768
    retried = client.messages.calls[1]["messages"]
    assert retried[0]["role"] == "user"
    assert retried[1] == {
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": "", "signature": "sig-keep"},
            {"type": "text", "text": "Still thinking."},
        ],
    }
    assert retried[2]["role"] == "user"
    assert "submit_enablement_plan" in retried[2]["content"]
    assert plan.metadata.coordinator_session_id == "sess-tool-choice"


async def test_opus_no_tool_use_raises_from_text_not_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_model_env(monkeypatch)
    prose = _Response(
        [
            ThinkingBlock(type="thinking", thinking="hidden", signature="sig"),
            TextBlock(type="text", text="I will not call the tool.", citations=None),
        ]
    )
    client = _Client([prose, prose])

    with pytest.raises(RuntimeError, match="I will not call the tool") as raised:
        await _run(monkeypatch, client)

    assert len(client.messages.calls) == 2
    assert "hidden" not in str(raised.value)


async def test_sonnet_no_tool_use_does_not_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_model_env(monkeypatch)
    monkeypatch.setenv(ENABLEMENT_AGENT_MODEL_ENV, "claude-sonnet-4-6")
    client = _Client(
        [
            _Response(
                [
                    _thinking(),
                    TextBlock(type="text", text="No tool from Sonnet.", citations=None),
                ]
            )
        ]
    )

    with pytest.raises(RuntimeError, match="No tool from Sonnet"):
        await _run(monkeypatch, client)

    assert len(client.messages.calls) == 1
