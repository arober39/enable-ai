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

from anthropic import AsyncAnthropic
from anthropic.types import ToolUseBlock

from coordinator.schemas import EnablementPlan
from core.identity import UserContext
from core.roles import Role
from core.tool_catalog import load_tool

logger = logging.getLogger(__name__)

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]

#: Model used for live UI runs. Haiku is ~2x faster than Sonnet for this
#: structured-output task, with similar plan quality on a 4-tool stack.
#: The CLI/SDK path still defaults to whatever the agent definition pins —
#: this override is UI-only. Set UI_LIVE_MODEL=claude-sonnet-4-5-20250929
#: (or another id) if you want slower-but-deeper reasoning.
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 4096


def _gather_catalog_context(tools: list[str], user: UserContext) -> str:
    """Build the catalog section the model uses to reason.

    Reads each tool through `core.tool_catalog.load_tool`, which checks
    the user's researched cache first and falls back to the seed
    catalog. Researched tools and seed tools are presented identically
    to the model — both conform to ToolCapability.
    """
    chunks: list[str] = []
    for tool_name in tools:
        cap = load_tool(user, tool_name)
        if cap is None:
            chunks.append(
                json.dumps(
                    {
                        "tool_name": tool_name,
                        "error": "tool not found in catalog or user cache",
                    },
                    indent=2,
                )
            )
            continue
        combined = {
            "tool_name": cap.canonical_name,
            "vendor": cap.vendor,
            "categories": cap.categories,
            "native_ai_features": [
                f.model_dump() for f in cap.native_ai_features
            ],
            "api_surface": cap.api_surface.model_dump(),
            "integration_patterns": cap.integration_patterns,
            "notes": cap.notes,
            "mcp_server": cap.mcp_server.model_dump(),
            "mcp_fallback_if_unavailable": cap.fallback_if_unavailable,
            "source": cap.source,
        }
        chunks.append(json.dumps(combined, indent=2))
    return "\n\n".join(chunks)


def _build_user_message(
    tools: list[str], session_id: str, role: Role, user: UserContext
) -> str:
    """Compose the single user-message that drives the run."""
    catalog_context = _gather_catalog_context(tools, user)
    cap_bullet_list = "\n".join(f"- {c}" for c in role.capabilities)
    role_lower = role.display_name.lower()
    return f"""\
You are the {role.display_name} Enablement Agent for Enable AI.

Your task: produce a structured EnablementPlan for a {role_lower} function based on the declared tool stack below. Call `submit_enablement_plan` exactly once when your work is complete.

## Declared stack ({len(tools)} tools)

{catalog_context}

## Required metadata for your submitted plan

- `department`: "{role.department}"
- `metadata.agent_name`: "{role.agent_name}" (this UI invokes the agent's logic directly)
- `metadata.agent_version`: "0.1.0"
- `metadata.coordinator_session_id`: "{session_id}"
- `metadata.stack_file_hash`: a hex string, sha256 of the tool list — already computed for you, use: "{hashlib.sha256(','.join(sorted(tools)).encode()).hexdigest()}"
- `metadata.generated_at`: an ISO 8601 UTC timestamp for *now*

## How to think about this

Compare the declared stack against these {len(role.capabilities)} AI-enabled {role_lower} capabilities:

{cap_bullet_list}

For each capability decide: covered, partial, gap, or redundant — based on the tool catalog data above.

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

`ai_configs_to_create` should be `["{role.id}-orchestrator-config"]`.

`env_vars_required` should be a subset of: ANTHROPIC_API_KEY, LAUNCHDARKLY_SDK_KEY, INTERCOM_API_KEY, ZENDESK_API_TOKEN, SLACK_BOT_TOKEN, HUBSPOT_API_KEY.

## When you call the tool

Call `submit_enablement_plan` exactly once. The tool's input schema IS the EnablementPlan schema — put `department`, `summary`, `capability_coverage`, `recommendations`, `orchestrator_pr_plan`, and `metadata` **at the top level of the tool input**. Do NOT wrap them in a `plan`, `enablement_plan`, `result`, or `data` envelope. Every required field of EnablementPlan must be present and correctly typed. Enum values must match exactly. No extra fields.
"""


def _build_system_prompt(role: Role) -> str:
    """Compose the system prompt from the role's domain knowledge file."""
    dk_path = role.domain_knowledge_path
    dk = dk_path.read_text(encoding="utf-8") if dk_path.exists() else ""
    return f"""\
You are the {role.display_name} Enablement Agent for Enable AI.

Your job: reason over a declared {role.display_name.lower()} tool stack and produce a structured EnablementPlan describing what AI-enabled {role.display_name.lower()} could look like with that stack.

You output the plan by calling the `submit_enablement_plan` tool exactly once. You do not produce free-text reports. You do not call external APIs. You do not invent tools the user didn't include.

Your domain knowledge follows. Ground your reasoning against it; don't freelance capability lists from memory.

---

{dk}
"""


#: Single-key envelopes the model sometimes wraps its output in even though
#: the tool input_schema doesn't have one. We unwrap before Pydantic validation.
_KNOWN_ENVELOPE_KEYS = frozenset({"plan", "enablement_plan", "result", "data", "output"})


def _unwrap_envelope(args: dict[str, Any]) -> dict[str, Any]:
    """If args is a single-key envelope around the real plan, unwrap it.

    The submit_enablement_plan tool schema IS the EnablementPlan schema —
    no `plan` key. Some Claude responses wrap the fields in `{"plan": {...}}`
    anyway. Detecting and stripping is cheap and avoids a hard failure.
    """
    if len(args) == 1:
        sole_key = next(iter(args.keys()))
        if sole_key.lower() in _KNOWN_ENVELOPE_KEYS and isinstance(
            args[sole_key], dict
        ):
            logger.warning(
                "live runner: unwrapping %r envelope before validation",
                sole_key,
            )
            return args[sole_key]
    return args


def _extract_submit_args(tool_use_blocks: list[ToolUseBlock]) -> dict[str, Any]:
    """Find the submit_enablement_plan tool_use call and return its arguments."""
    for block in tool_use_blocks:
        if block.name == "submit_enablement_plan":
            args = block.input
            if isinstance(args, dict):
                return _unwrap_envelope(args)
    raise RuntimeError(
        "Model did not call submit_enablement_plan. Cannot construct a plan."
    )


async def run_live_plan(
    tools: list[str], role: Role, user: UserContext
) -> EnablementPlan:
    """Generate an EnablementPlan via direct Anthropic API call.

    Args:
        tools: List of canonical tool names selected in the UI. Must be
            resolvable via `core.tool_catalog.load_tool(user, name)` —
            either seed catalog or user's researched cache.
        role: The selected role — drives the agent's domain knowledge,
            department label, and capability list.
        user: Identity context — used to resolve tools via the unified
            catalog (researched + seed).

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
    system_prompt = _build_system_prompt(role)
    user_message = _build_user_message(tools, session_id, role, user)

    # The tool's input_schema is literally the EnablementPlan JSON Schema —
    # so the model's tool_use call is guaranteed to produce well-shaped data
    # (Anthropic validates against this server-side).
    plan_schema = EnablementPlan.model_json_schema()

    client = AsyncAnthropic()
    model = os.environ.get("UI_LIVE_MODEL", _DEFAULT_MODEL)
    logger.info(
        "live runner: model=%s role=%s tools=%s session=%s",
        model,
        role.id,
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
