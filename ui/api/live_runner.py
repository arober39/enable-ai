# ruff: noqa: E501  -- prompt strings sit at natural paragraph widths
"""Direct-Anthropic live runner for the UI's live mode.

Architectural deviation from the v1 build plan: the UI's live-mode path
calls the Anthropic Python SDK directly rather than going through
`claude-agent-sdk`. Why:

  - claude-agent-sdk 0.1.81 ships a bundled `claude` CLI binary. On some
    systems that binary returns a contradictory `result` message
    (is_error=true AND subtype=success) and the SDK surfaces it as
    "Claude Code returned an error result: success" — actionable for
    nobody. We hit this reliably from FastAPI.

  - For the UI's purpose ("let me see a plan come back"), we don't need
    Task delegation, hooks, or MCP — those add value in the routed
    Coordinator path but cost nothing to skip here. We get structured
    output via Anthropic's native tool_use, which is what the rest of
    the system uses anyway via the SDK MCP server.

The CLI path (`python -m coordinator "..."`) and the Phase 7 live tests
still use claude-agent-sdk. This module is scoped to ui/api/.

Inputs: the user's tool selection + the local catalog data.
Output:  a fully-validated EnablementPlan, same Pydantic shape as the
         routed Coordinator path produces.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from anthropic import AsyncAnthropic
from anthropic.types import ToolUseBlock

from coordinator.schemas import EnablementPlan

logger = logging.getLogger(__name__)

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]
_DOMAIN_KNOWLEDGE_PATH: Path = (
    _REPO_ROOT
    / "enablement_agents"
    / "support"
    / "domain_knowledge.md"
)
_POLICIES_PATH: Path = _REPO_ROOT / "data" / "support" / "policies.md"
_STACK_FILE_PATH: Path = _REPO_ROOT / "stacks" / "support.yaml"

#: Model used for live UI runs. Haiku is ~2x faster than Sonnet for this
#: structured-output task, with similar plan quality on a 4-tool stack.
#: The CLI/SDK path still defaults to whatever the agent definition pins —
#: this override is UI-only. Set UI_LIVE_MODEL=claude-sonnet-4-5-20250929
#: (or another id) if you want slower-but-deeper reasoning.
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 4096


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _gather_catalog_context(tools: list[str]) -> str:
    """Build the catalog section the model uses to reason.

    Includes each tool's vendor / categories / native AI features / API
    surface / MCP availability. Same data the SDK Support agent would
    fetch via `lookup_tool_capability` — just inlined here so we don't
    need a tool-use round trip.
    """
    chunks: list[str] = []
    for tool_name in tools:
        tool_data = _load_yaml(_REPO_ROOT / "tools" / f"{tool_name}.yaml")
        mcp_data = _load_yaml(_REPO_ROOT / "mcp_registry" / f"{tool_name}.yaml")
        combined = {
            "tool_name": tool_name,
            "vendor": tool_data.get("vendor"),
            "categories": tool_data.get("categories", []),
            "native_ai_features": tool_data.get("native_ai_features", []),
            "api_surface": tool_data.get("api_surface", {}),
            "integration_patterns": tool_data.get("integration_patterns", []),
            "notes": tool_data.get("notes"),
            "mcp_server": mcp_data.get("mcp_server"),
            "mcp_fallback_if_unavailable": mcp_data.get("fallback_if_unavailable"),
        }
        chunks.append(json.dumps(combined, indent=2))
    return "\n\n".join(chunks)


def _build_user_message(tools: list[str], session_id: str) -> str:
    """Compose the single user-message that drives the run."""
    catalog_context = _gather_catalog_context(tools)
    return f"""\
You are the Support Enablement Agent for Enable AI, operating on Serenia & Co.

Your task: produce a structured EnablementPlan for Serenia & Co.'s customer support function based on the declared tool stack below. Call `submit_enablement_plan` exactly once when your work is complete.

## Declared stack ({len(tools)} tools)

{catalog_context}

## Required metadata for your submitted plan

- `department`: "support"
- `metadata.agent_name`: "support_enablement_agent" (this UI invokes the agent's logic directly)
- `metadata.agent_version`: "0.1.0"
- `metadata.coordinator_session_id`: "{session_id}"
- `metadata.stack_file_hash`: a hex string, sha256 of the tool list — already computed for you, use: "{hashlib.sha256(','.join(sorted(tools)).encode()).hexdigest()}"
- `metadata.generated_at`: an ISO 8601 UTC timestamp for *now*

## How to think about this

Compare the declared stack against the seven AI-enabled support capabilities (intent classification, first-response drafting, escalation routing, FAQ retrieval, sentiment analysis, conversation summarization, knowledge base search). For each capability decide: covered, partial, gap, or redundant — based on the tool catalog data above.

Then translate findings into recommendations. Each recommendation has a `kind`:
- `use_native_ai` — only when the native feature is genuinely sufficient with no augmentation
- `augment_with_custom_ai` — when native AI covers something but doesn't see cross-tool data
- `consolidate` — when two tools redundantly cover the same capability
- `orchestrate` — when value comes from composing multiple tools

Set a high bar for `use_native_ai`. Default toward `augment_with_custom_ai` or `orchestrate` when the value is multi-tool.

## Orchestrator PR plan

Populate `orchestrator_pr_plan` describing the orchestrator that would be generated from these recommendations. Files to list under `files_to_create`:

- orchestrator.py
- agent_definition.py
- prompts/v1_baseline.md
- prompts/v2_detailed_responses.md
- judges/factual_accuracy.md
- .mcp.json
- observability.py
- .env.example
- Makefile
- README.md
- ai_configs.manifest.yaml

`mcp_servers_used` should list tool names whose catalog data shows `mcp_server.available: true`. `mcp_servers_to_generate` should list tool names where `mcp_server.available: false` (a stub will be generated).

`ai_configs_to_create` should be `["support-orchestrator-config"]`.

`env_vars_required` should be a subset of: ANTHROPIC_API_KEY, LAUNCHDARKLY_SDK_KEY, INTERCOM_API_KEY, ZENDESK_API_TOKEN, SLACK_BOT_TOKEN, HUBSPOT_API_KEY.

## When you call the tool

Call `submit_enablement_plan` exactly once. Every field of EnablementPlan must be present and correctly typed. Enum values must match exactly. No extra fields.
"""


def _build_system_prompt() -> str:
    """Compose the system prompt from the domain knowledge file."""
    dk = _DOMAIN_KNOWLEDGE_PATH.read_text(encoding="utf-8") if _DOMAIN_KNOWLEDGE_PATH.exists() else ""
    return f"""\
You are the Support Enablement Agent for Enable AI, operating on the fictional company Serenia & Co.

Your job: reason over a declared customer-support tool stack and produce a structured EnablementPlan describing what AI-enabled support could look like with that stack.

You output the plan by calling the `submit_enablement_plan` tool exactly once. You do not produce free-text reports. You do not call external APIs. You do not invent tools the user didn't include.

Your domain knowledge follows. Ground your reasoning against it; don't freelance capability lists from memory.

---

{dk}
"""


def _extract_submit_args(tool_use_blocks: list[ToolUseBlock]) -> dict[str, Any]:
    """Find the submit_enablement_plan tool_use call and return its arguments."""
    for block in tool_use_blocks:
        if block.name == "submit_enablement_plan":
            args = block.input
            if isinstance(args, dict):
                return args
    raise RuntimeError(
        "Model did not call submit_enablement_plan. Cannot construct a plan."
    )


async def run_live_plan(tools: list[str]) -> EnablementPlan:
    """Generate an EnablementPlan via direct Anthropic API call.

    Args:
        tools: List of canonical tool names selected in the UI. Must be a
            subset of the catalog (validated upstream).

    Returns:
        Validated EnablementPlan.

    Raises:
        RuntimeError: If the model doesn't call submit_enablement_plan, or
            if the returned plan fails Pydantic validation.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Live mode requires it. Set it "
            "in .env and restart the backend."
        )

    session_id = f"ui-live-{datetime.now(UTC).timestamp():.0f}"
    system_prompt = _build_system_prompt()
    user_message = _build_user_message(tools, session_id)

    # The tool's input_schema is literally the EnablementPlan JSON Schema —
    # so the model's tool_use call is guaranteed to produce well-shaped data
    # (Anthropic validates against this server-side).
    plan_schema = EnablementPlan.model_json_schema()

    client = AsyncAnthropic()
    model = os.environ.get("UI_LIVE_MODEL", _DEFAULT_MODEL)
    logger.info(
        "live runner: model=%s tools=%s session=%s",
        model,
        tools,
        session_id,
    )

    response = await client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        system=system_prompt,
        tools=[
            {
                "name": "submit_enablement_plan",
                "description": (
                    "Submit the final structured EnablementPlan. Call this "
                    "exactly once when your reasoning is complete. The input "
                    "must conform to the EnablementPlan schema."
                ),
                "input_schema": plan_schema,
            }
        ],
        tool_choice={"type": "tool", "name": "submit_enablement_plan"},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_uses = [block for block in response.content if isinstance(block, ToolUseBlock)]
    if not tool_uses:
        # The model didn't call the tool — surface useful debugging info.
        text_blocks = [
            block for block in response.content if getattr(block, "type", None) == "text"
        ]
        debug = (
            text_blocks[0].text[:300]  # type: ignore[union-attr]
            if text_blocks
            else "(no text or tool_use blocks)"
        )
        raise RuntimeError(
            f"Live runner: model returned no tool_use. "
            f"stop_reason={response.stop_reason}. preview: {debug}"
        )

    args = _extract_submit_args(tool_uses)
    try:
        return EnablementPlan.model_validate(args)
    except Exception as exc:  # noqa: BLE001 — surface Pydantic error message
        raise RuntimeError(
            f"Live runner: model returned malformed plan: {exc}"
        ) from exc
