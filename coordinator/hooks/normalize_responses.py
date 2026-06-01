"""PostToolUse hook: normalize MCP tool errors to the structured-error schema.

When an MCP tool returns an error in a free-text shape, this hook wraps the
response so the agent always sees a structured error object:

    {
        "isError": True,
        "errorCategory": "internal" | "permission" | "not_found" | ...,
        "isRetryable": False,
        "message": "...",
    }

Successful responses pass through unmodified. The hook only fires on tool
calls whose name starts with `mcp__` (the SDK convention for MCP tools).
"""

from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import HookContext, HookInput
from claude_agent_sdk.types import SyncHookJSONOutput

logger = logging.getLogger(__name__)

_MCP_TOOL_PREFIX = "mcp__"
_VALID_CATEGORIES = {
    "permission",
    "not_found",
    "rate_limit",
    "upstream_unavailable",
    "validation",
    "internal",
}


def _looks_already_structured(payload: dict[str, Any]) -> bool:
    """An already-conforming structured error has isError, errorCategory, isRetryable, message."""
    if not payload.get("isError"):
        return False
    if not isinstance(payload.get("errorCategory"), str):
        return False
    if payload["errorCategory"] not in _VALID_CATEGORIES:
        return False
    if not isinstance(payload.get("isRetryable"), bool):
        return False
    if not isinstance(payload.get("message"), str):
        return False
    return True


def _coerce_payload_to_dict(tool_response: Any) -> dict[str, Any] | None:
    """Best-effort coerce a tool_response into a dict we can inspect/wrap."""
    if isinstance(tool_response, dict):
        return tool_response
    return None


def _build_structured_error(original: Any) -> dict[str, Any]:
    """Wrap a non-conforming error into the structured-error schema."""
    if isinstance(original, dict):
        message = str(original.get("message") or original.get("error") or original)
    else:
        message = str(original)
    return {
        "isError": True,
        "errorCategory": "internal",
        "isRetryable": False,
        "message": message,
        "wrapped_by": "normalize_responses",
    }


async def normalize_responses(
    input_data: HookInput,
    tool_use_id: str | None,
    context: HookContext,  # noqa: ARG001 — required by SDK signature
) -> SyncHookJSONOutput:
    """PostToolUse hook implementation."""
    tool_name = str(input_data.get("tool_name", ""))
    if not tool_name.startswith(_MCP_TOOL_PREFIX):
        return {}

    tool_response = input_data.get("tool_response")
    payload = _coerce_payload_to_dict(tool_response)

    # If we can't parse it as a dict and there's no clear error signal, leave alone.
    if payload is None:
        return {}

    # Already-conforming responses pass through.
    if not payload.get("isError") or _looks_already_structured(payload):
        return {}

    # Wrap it.
    wrapped = _build_structured_error(payload)
    logger.info(
        "normalize_responses wrapped non-structured error for tool=%s tool_use_id=%s",
        tool_name,
        tool_use_id,
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedMCPToolOutput": wrapped,
        },
    }
