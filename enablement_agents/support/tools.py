"""Custom MCP tools for the Support Enablement Agent.

`lookup_tool_capability` is the agent's primary read tool. Given a canonical
tool name (e.g., "intercom"), it reads `tools/<tool_name>.yaml` and
`mcp_registry/<tool_name>.yaml` from disk and returns a structured combined
view of:

  - native AI features
  - API surface (REST, webhooks, rate limits)
  - integration patterns
  - MCP server availability and tools_exposed
  - notes

The tool returns a structured `isError` response when a tool isn't found,
following the schema in `.claude/rules/mcp-server-conventions.md`. The
Coordinator's `normalize_responses` hook is a backstop, but this tool emits
already-conformant errors so the backstop is a no-op for it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from claude_agent_sdk import McpServerConfig, create_sdk_mcp_server, tool

logger = logging.getLogger(__name__)

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]
_TOOLS_DIR: Path = _REPO_ROOT / "tools"
_MCP_DIR: Path = _REPO_ROOT / "mcp_registry"

#: Server name when registered on ClaudeAgentOptions.mcp_servers.
SUPPORT_MCP_SERVER_NAME = "support"

#: Fully-qualified tool name the agent uses in allowed_tools.
LOOKUP_TOOL_QUALIFIED_NAME = f"mcp__{SUPPORT_MCP_SERVER_NAME}__lookup_tool_capability"


_LOOKUP_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tool_name": {
            "type": "string",
            "description": (
                "Canonical tool name (e.g., 'intercom', 'zendesk', 'slack', 'hubspot'). "
                "Must match the filename of an entry in the tools/ directory."
            ),
        },
        "capability_filter": {
            "type": "string",
            "description": (
                "Optional. Filter native AI features and integration patterns to those "
                "mentioning this capability area (e.g., 'crm', 'ticketing', "
                "'knowledge_base', 'internal_handoff'). Case-insensitive substring match."
            ),
        },
    },
    "required": ["tool_name"],
    "additionalProperties": False,
}


def _structured_error(category: str, message: str, **extra: Any) -> dict[str, Any]:
    """Build a conforming structured-error payload (matches the convention)."""
    return {
        "isError": True,
        "errorCategory": category,
        "isRetryable": False,
        "message": message,
        **extra,
    }


def _filter_features(features: list[Any] | None, cap_filter: str) -> list[Any]:
    """Return features whose serialized form mentions `cap_filter` (case-insensitive)."""
    if not features:
        return []
    needle = cap_filter.lower().strip()
    out: list[Any] = []
    for feat in features:
        if needle in json.dumps(feat, default=str).lower():
            out.append(feat)
    return out


def _load_yaml(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    return raw


@tool(
    "lookup_tool_capability",
    (
        "Look up the AI capabilities and integration patterns of a specific tool. "
        "Returns structured information about native AI features, API surface, and "
        "known MCP server availability. Use this when assessing how a department's "
        "tool stack could be augmented with AI. Always call this before recommending "
        "a course of action for a tool — do not guess what the tool offers from "
        "memory. On unknown tool, returns a structured isError with errorCategory "
        "'not_found' so you can record a capability gap instead of failing."
    ),
    _LOOKUP_INPUT_SCHEMA,
)
async def lookup_tool_capability(args: dict[str, Any]) -> dict[str, Any]:
    """Implementation: read tools/<name>.yaml + mcp_registry/<name>.yaml, combine."""
    tool_name = args.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        err = _structured_error(
            "validation",
            "tool_name is required and must be a non-empty string.",
        )
        return {
            "content": [{"type": "text", "text": json.dumps(err, indent=2)}],
            "is_error": True,
        }
    tool_name = tool_name.strip().lower()
    cap_filter = args.get("capability_filter")
    cap_filter = cap_filter.strip() if isinstance(cap_filter, str) and cap_filter.strip() else None

    tool_data = _load_yaml(_TOOLS_DIR / f"{tool_name}.yaml")
    mcp_data = _load_yaml(_MCP_DIR / f"{tool_name}.yaml")

    if tool_data is None:
        err = _structured_error(
            "not_found",
            (
                f"No catalog entry for tool '{tool_name}'. Looked at "
                f"{_TOOLS_DIR / (tool_name + '.yaml')}. Record this as a capability gap "
                f"in the EnablementPlan with a note indicating the missing tool catalog entry."
            ),
            tool_name=tool_name,
        )
        logger.info("lookup_tool_capability not_found: %s", tool_name)
        return {
            "content": [{"type": "text", "text": json.dumps(err, indent=2)}],
            "is_error": True,
        }

    result: dict[str, Any] = {
        "tool_name": tool_data.get("canonical_name", tool_name),
        "vendor": tool_data.get("vendor"),
        "categories": tool_data.get("categories", []),
        "native_ai_features": tool_data.get("native_ai_features", []),
        "api_surface": tool_data.get("api_surface", {}),
        "integration_patterns": tool_data.get("integration_patterns", []),
        "notes": tool_data.get("notes"),
        "mcp_server": (mcp_data.get("mcp_server") if mcp_data else None),
        "mcp_fallback_if_unavailable": (
            mcp_data.get("fallback_if_unavailable") if mcp_data else None
        ),
        "mcp_notes": (mcp_data.get("notes") if mcp_data else None),
    }

    if cap_filter is not None:
        result["native_ai_features"] = _filter_features(
            result["native_ai_features"], cap_filter
        )
        result["capability_filter_applied"] = cap_filter

    return {
        "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
    }


def build_support_mcp_server() -> McpServerConfig:
    """Factory: build the in-process MCP server that hosts lookup_tool_capability."""
    return create_sdk_mcp_server(
        name=SUPPORT_MCP_SERVER_NAME,
        version="0.1.0",
        tools=[lookup_tool_capability],
    )
