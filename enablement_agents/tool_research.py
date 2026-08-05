"""LLM-driven tool researcher.

Given a free-form tool name from the UI typeahead, hits Claude with a
forced `submit_tool_capability` tool_use that conforms to
`ToolCapability`. The validated result is cached via
`core.tool_catalog.cache_tool` so the next lookup is free.

Architectural note: this module talks to Anthropic directly (same
pattern as `ui/api/live_runner.py`). The build-time agent path
(coordinator + claude-agent-sdk) does not own typeahead — typeahead is a
short, latency-sensitive runtime lookup.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import ToolUseBlock

from core.credentials import runtime_credentials
from core.identity import UserContext
from core.tool_catalog import ToolCapability, cache_tool, normalize_name

logger = logging.getLogger(__name__)

_RESEARCH_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 2048


def _schema_for_submit() -> dict[str, Any]:
    """ToolCapability JSON schema minus the loader-populated `source` field."""
    schema = ToolCapability.model_json_schema()
    props = schema.get("properties") or {}
    if "source" in props:
        del props["source"]
    required = schema.get("required") or []
    schema["required"] = [r for r in required if r != "source"]
    return schema


_SYSTEM_PROMPT = """\
You are a Tool Capability Researcher for Enable AI.

Given a SaaS / developer / business tool name, produce a structured
ToolCapability record describing:

- vendor (human-readable display name; canonical_name is given to you)
- categories (e.g., crm, ticketing, marketing_automation, knowledge_base)
- native_ai_features — each with name, description, maturity (ga / beta /
  preview / deprecated / unknown), and coverage (low / medium / high /
  unknown). Empty list is fine if the vendor has no AI features.
- api_surface (has_rest_api, has_webhooks, rate_limits: standard /
  strict / generous / unknown)
- integration_patterns — choose from: use_native_ai,
  augment_with_custom_ai, consolidate, orchestrate_into_unified_surface
- notes — one short paragraph framing the tool's AI strengths and limits
- mcp_server — set `available: true` ONLY if you are confident the
  vendor or a credible community publishes an MCP server. Otherwise
  `available: false` with the rest of the MCP fields null/empty.
- fallback_if_unavailable — usually "direct_api"

Be honest about uncertainty. If you don't know a tool, set maturity /
coverage / rate_limits to "unknown" and write that into the notes field.
NEVER invent MCP server URLs — that misleads downstream code generation.

Call `submit_tool_capability` exactly once with the result.
"""


async def research_tool(
    name: str,
    user: UserContext,
    *,
    cache: bool = True,
) -> ToolCapability:
    """Research a tool with Claude, validate against `ToolCapability`, cache.

    Args:
        name: Free-form tool name typed by the user. Normalized to a
            canonical lowercase slug before research.
        user: Identity context — used for cache-write only.
        cache: If True, persist the validated result to the user's
            tool cache. Set False for one-off previews.

    Returns:
        Validated `ToolCapability` with `source="researched"`.

    Raises:
        RuntimeError: missing API key, model didn't call the tool, or
            validation fails.
        ValueError: if `name` cannot be normalized.
    """
    creds = runtime_credentials()
    if not creds.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Tool research requires it. "
            "Add it via the Settings page in the UI."
        )

    canonical = normalize_name(name)
    schema = _schema_for_submit()

    user_message = (
        f"Research the tool: {name!r} (canonical name: {canonical!r}).\n\n"
        f"Produce a ToolCapability record. canonical_name MUST be "
        f"exactly {canonical!r}. vendor should be the human-readable "
        f"display name (e.g. 'Mailchimp', 'Salesforce Marketing Cloud')."
    )

    # Anthropic SDK reads ANTHROPIC_API_KEY from env. The credential
    # context manager in ui.api.server populates it for this process.
    client = AsyncAnthropic()
    model = os.environ.get("UI_RESEARCH_MODEL", _RESEARCH_MODEL)
    logger.info("tool research: model=%s name=%s canonical=%s", model, name, canonical)

    response = await client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        tools=[
            {
                "name": "submit_tool_capability",
                "description": (
                    "Submit the structured ToolCapability record. Call "
                    "exactly once when your research is complete."
                ),
                "input_schema": schema,
            }
        ],
        tool_choice={"type": "tool", "name": "submit_tool_capability"},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_uses = [b for b in response.content if isinstance(b, ToolUseBlock)]
    if not tool_uses:
        raise RuntimeError(
            f"Tool researcher: model returned no tool_use for {name!r}. "
            f"stop_reason={response.stop_reason}."
        )

    args = tool_uses[0].input
    if not isinstance(args, dict):
        raise RuntimeError(
            f"Tool researcher: tool_use args were not a dict for {name!r}."
        )

    # Force canonical_name to match the slug we requested — the model
    # sometimes echoes the user-typed form back.
    args["canonical_name"] = canonical
    args["source"] = "researched"

    try:
        capability = ToolCapability.model_validate(args)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Tool researcher: validation failed for {name!r}: {exc}"
        ) from exc

    if cache:
        cache_tool(user, capability)
    return capability
