"""PreToolUse hook: block real external API calls in demo mode.

When `ENABLE_AI_DEMO_MODE=true` (the default), this hook inspects every
PreToolUse event and denies the call if it appears to reach a real
LaunchDarkly or supported SaaS API. The denial surfaces a structured
refusal message so the agent can adapt (use local static data instead).

The hook never disables itself silently — if demo mode is off, real calls
are allowed. If it is on, real calls are deterministically blocked.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from claude_agent_sdk import HookContext, HookInput
from claude_agent_sdk.types import SyncHookJSONOutput

logger = logging.getLogger(__name__)

# Domain / endpoint patterns that indicate a real external API call.
# Matched against Bash command strings and any URL-like tool inputs.
_BLOCKED_HOST_PATTERNS = [
    re.compile(r"\bapp\.launchdarkly\.com\b", re.I),
    re.compile(r"\bsdk\.launchdarkly\.com\b", re.I),
    re.compile(r"\bclientstream\.launchdarkly\.com\b", re.I),
    re.compile(r"\bevents\.launchdarkly\.com\b", re.I),
    re.compile(r"\bapi\.intercom\.io\b", re.I),
    re.compile(r"\bapi\.zendesk\.com\b", re.I),
    re.compile(r"\.zendesk\.com/api/", re.I),
    re.compile(r"\bslack\.com/api/", re.I),
    re.compile(r"\bapi\.hubapi\.com\b", re.I),
    re.compile(r"\bapi\.anthropic\.com\b", re.I),
    re.compile(r"\bapi\.openai\.com\b", re.I),
]

# Bash subcommands that almost always indicate an external HTTP call.
_BLOCKED_BASH_TOKENS = [
    re.compile(r"\bcurl\s+(?:[^|;&]*?)https?://", re.I),
    re.compile(r"\bwget\s+(?:[^|;&]*?)https?://", re.I),
    re.compile(r"\bhttpx\s+\w+\s+https?://", re.I),
]


def _demo_mode_enabled() -> bool:
    raw = os.environ.get("ENABLE_AI_DEMO_MODE", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _scan_text(text: str) -> str | None:
    """Return the matched pattern if `text` references a blocked endpoint."""
    for pat in _BLOCKED_HOST_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0)
    for pat in _BLOCKED_BASH_TOKENS:
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


def _scan_tool_input(tool_name: str, tool_input: dict[str, Any]) -> str | None:
    """Inspect a tool_input for blocked external references.

    For Bash, scan the `command` field. For everything else, walk the input
    and scan any string value.
    """
    if tool_name == "Bash":
        cmd = str(tool_input.get("command", ""))
        return _scan_text(cmd)

    def walk(value: Any) -> str | None:
        if isinstance(value, str):
            return _scan_text(value)
        if isinstance(value, dict):
            for v in value.values():
                hit = walk(v)
                if hit:
                    return hit
        if isinstance(value, list):
            for item in value:
                hit = walk(item)
                if hit:
                    return hit
        return None

    return walk(tool_input)


async def enforce_credentials(
    input_data: HookInput,
    tool_use_id: str | None,
    context: HookContext,  # noqa: ARG001 — required by SDK signature
) -> SyncHookJSONOutput:
    """PreToolUse hook implementation.

    Returns a deny decision if demo mode is on and the tool call references
    a real external API. Otherwise returns an empty dict (allow by default).
    """
    if not _demo_mode_enabled():
        return {}

    # input_data is a TypedDict (PreToolUseHookInput at runtime); reading via
    # .get is safe because all SDK hook inputs share a `dict`-shaped base.
    tool_name = str(input_data.get("tool_name", ""))
    tool_input_raw = input_data.get("tool_input") or {}
    tool_input: dict[str, Any] = tool_input_raw if isinstance(tool_input_raw, dict) else {}

    hit = _scan_tool_input(tool_name, tool_input)
    if hit is None:
        return {}

    reason = (
        f"Demo mode is active (ENABLE_AI_DEMO_MODE=true). Tool call '{tool_name}' "
        f"references a real external endpoint matched on '{hit}'. Real external "
        f"API calls are blocked. Use the local static data under stacks/, tools/, "
        f"mcp_registry/, and data/ instead. To allow real API calls, set "
        f"ENABLE_AI_DEMO_MODE=false (e.g., for production runs)."
    )
    logger.info(
        "enforce_credentials denied tool=%s tool_use_id=%s match=%s",
        tool_name,
        tool_use_id,
        hit,
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }
