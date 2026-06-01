"""Deterministic tests for the support agent's `lookup_tool_capability` tool.

Each test exercises the underlying handler directly with constructed args
— no SDK involvement, no LLM. The handler reads from `tools/<name>.yaml`
and `mcp_registry/<name>.yaml` on disk (the Phase 2 data files).
"""

from __future__ import annotations

import json

import pytest

from enablement_agents.support.tools import lookup_tool_capability


async def _call(args: dict[str, object]) -> dict[str, object]:
    return await lookup_tool_capability.handler(args)


def _parse_text_payload(response: dict[str, object]) -> dict[str, object]:
    """Extract the embedded JSON object from the tool's content array."""
    content = response.get("content")
    assert isinstance(content, list)
    text_block = content[0]
    assert isinstance(text_block, dict)
    text = text_block.get("text")
    assert isinstance(text, str)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Known tools (intercom, zendesk, slack, hubspot) — all in the support stack
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", ["intercom", "zendesk", "slack", "hubspot"])
async def test_known_tool_returns_data(tool_name: str) -> None:
    response = await _call({"tool_name": tool_name})
    assert "is_error" not in response
    body = _parse_text_payload(response)
    assert body["tool_name"] == tool_name
    assert isinstance(body["categories"], list)
    assert isinstance(body["native_ai_features"], list)
    # mcp_server may be a dict or None depending on availability
    assert "mcp_server" in body


async def test_intercom_has_fin_feature() -> None:
    body = _parse_text_payload(await _call({"tool_name": "intercom"}))
    feature_names = [f.get("name") for f in body["native_ai_features"]]  # type: ignore[union-attr]
    assert "Fin" in feature_names


async def test_hubspot_mcp_unavailable() -> None:
    body = _parse_text_payload(await _call({"tool_name": "hubspot"}))
    mcp = body.get("mcp_server")
    assert isinstance(mcp, dict)
    assert mcp.get("available") is False


async def test_slack_mcp_reference_origin() -> None:
    body = _parse_text_payload(await _call({"tool_name": "slack"}))
    mcp = body.get("mcp_server")
    assert isinstance(mcp, dict)
    assert mcp.get("available") is True
    assert mcp.get("origin") == "reference"


# ---------------------------------------------------------------------------
# capability_filter narrows the feature list
# ---------------------------------------------------------------------------


async def test_capability_filter_narrows_features() -> None:
    full = _parse_text_payload(await _call({"tool_name": "zendesk"}))
    filtered = _parse_text_payload(
        await _call({"tool_name": "zendesk", "capability_filter": "knowledge"})
    )
    assert "capability_filter_applied" in filtered
    assert filtered["capability_filter_applied"] == "knowledge"
    # Filter should reduce (or preserve, if all match) — never grow.
    assert len(filtered["native_ai_features"]) <= len(full["native_ai_features"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Errors — unknown tool, empty tool_name
# ---------------------------------------------------------------------------


async def test_unknown_tool_returns_structured_not_found() -> None:
    response = await _call({"tool_name": "freshdesk"})
    assert response.get("is_error") is True
    body = _parse_text_payload(response)
    assert body["isError"] is True
    assert body["errorCategory"] == "not_found"
    assert body["isRetryable"] is False
    assert "freshdesk" in body["message"]  # type: ignore[operator]


async def test_empty_tool_name_returns_validation_error() -> None:
    response = await _call({"tool_name": ""})
    assert response.get("is_error") is True
    body = _parse_text_payload(response)
    assert body["errorCategory"] == "validation"


async def test_tool_name_case_normalized() -> None:
    """Tool name lookup should be case-insensitive (we lowercase internally)."""
    response = await _call({"tool_name": "INTERCOM"})
    assert "is_error" not in response
    body = _parse_text_payload(response)
    assert body["tool_name"] == "intercom"
