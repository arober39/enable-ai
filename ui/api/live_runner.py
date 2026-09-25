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

Claude Opus 5.5 rejects forced tool use (tool_choice type "tool" or
"any"). For that model this module sends tool_choice auto, strict tool
use, and an effort setting. Models that still allow a forced call
(including a Sonnet override) keep tool_choice type "tool".

Inputs: the user's tool selection + the local catalog data.
Output:  a fully-validated EnablementPlan, same Pydantic shape as the
         routed Coordinator path produces.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import ToolUseBlock

from coordinator.schemas import EnablementPlan
from core.identity import UserContext
from core.plan_grounding import apply_tool_grounding
from core.roles import Role
from core.tool_catalog import ToolCapability, load_tool
from enablement_agents.role_agent import resolve_role_agent_model

logger = logging.getLogger(__name__)

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]

#: Optional UI-only override. When set and non-empty, it wins over
#: ENABLEMENT_AGENT_MODEL for this module only. Unset, the live plan uses
#: the shared planner model (Opus 5.5, or ENABLEMENT_AGENT_MODEL).
_UI_LIVE_MODEL_ENV = "UI_LIVE_MODEL"
_SUBMIT_TOOL_NAME = "submit_enablement_plan"

#: Ceiling for models that do not spend output tokens on adaptive thinking.
_MAX_TOKENS = 4096

#: Opus 5.5 always thinks, and ``max_tokens`` covers thinking plus the
#: tool-call JSON. 4096 fit a plan when the model ran without thinking;
#: 16k leaves room for high-effort reasoning and a full EnablementPlan.
#: A truncated first reply retries once at 32k.
_OPUS_55_MAX_TOKENS = 16384
_OPUS_55_RETRY_MAX_TOKENS = 32768

#: Opus 5.5's default effort is medium. The live plan is the user-visible
#: deliverable, so we ask for high: more thinking than the default, short
#: of the xhigh/max budgets whose docs start ``max_tokens`` at 64k.
_OPUS_55_EFFORT = "high"

#: Strict tool use returns HTTP 400 above these caps.
_STRICT_MAX_OPTIONAL_PARAMS = 24
_STRICT_MAX_UNION_PARAMS = 16
_STRICT_STRING_FORMATS = frozenset(
    {
        "date-time",
        "time",
        "date",
        "duration",
        "email",
        "hostname",
        "uri",
        "ipv4",
        "ipv6",
        "uuid",
    }
)
_STRICT_UNSUPPORTED_KEYS = frozenset(
    {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "maxItems",
        "uniqueItems",
        "pattern",
    }
)


def resolve_live_plan_model() -> str:
    """Model id for the UI live enablement plan (steps 4 and 5).

    Resolution: ``UI_LIVE_MODEL`` if set and non-empty, else the shared
    enablement planner model (``ENABLEMENT_AGENT_MODEL``, else Opus 5.5).
    """
    ui_override = os.environ.get(_UI_LIVE_MODEL_ENV, "").strip()
    if ui_override:
        return ui_override
    return resolve_role_agent_model()


def _model_rejects_forced_tool_choice(model: str) -> bool:
    """True for Claude Opus 5.5, which rejects forced ``tool_choice``.

    Matches the fixed id ``claude-opus-5-5`` and provider-prefixed forms
    such as ``anthropic.claude-opus-5-5``. Opus 5 (``claude-opus-5``) and
    earlier Opus, Sonnet, and Haiku ids still allow ``type: tool``.
    """
    normalized = model.strip().lower()
    marker = "claude-opus-5-5"
    start = normalized.find(marker)
    if start < 0:
        return False
    end = start + len(marker)
    # ``claude-opus-5-50`` contains the marker as a prefix of a longer number.
    if end < len(normalized) and normalized[end].isdigit():
        return False
    return True


def _is_union_schema(prop: Any) -> bool:
    """True when a property schema is an anyOf/oneOf or a type array."""
    if not isinstance(prop, dict):
        return False
    if "anyOf" in prop or "oneOf" in prop:
        return True
    type_value = prop.get("type")
    return isinstance(type_value, list) and len(type_value) > 1


def _schema_allows_strict_tool(schema: dict[str, Any]) -> bool:
    """True when Anthropic strict tool use can accept this JSON Schema.

    Every object must set ``additionalProperties: false``. Unsupported
    constraints, external ``$ref``s, and the optional/union caps (24 and
    16) also make ``strict: true`` return HTTP 400.
    """
    optional = 0
    unions = 0
    problems: list[str] = []

    def walk(node: Any) -> None:
        nonlocal optional, unions
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return

        ref = node.get("$ref")
        if isinstance(ref, str) and not ref.startswith("#/"):
            problems.append("external $ref")

        fmt = node.get("format")
        if isinstance(fmt, str) and fmt not in _STRICT_STRING_FORMATS:
            problems.append(f"format {fmt}")

        if "minItems" in node and node["minItems"] not in (0, 1):
            problems.append("minItems")

        for key in _STRICT_UNSUPPORTED_KEYS:
            if key in node:
                problems.append(key)

        is_object = node.get("type") == "object" or "properties" in node
        if is_object and node.get("additionalProperties") is not False:
            problems.append("additionalProperties")

        properties = node.get("properties")
        if isinstance(properties, dict):
            required = set(node.get("required") or [])
            for name, prop in properties.items():
                if name not in required:
                    optional += 1
                if _is_union_schema(prop):
                    unions += 1

        for key, value in node.items():
            if key == "additionalProperties" and not isinstance(value, dict):
                continue
            walk(value)

    walk(schema)
    if optional > _STRICT_MAX_OPTIONAL_PARAMS:
        problems.append(f"optional parameters {optional}")
    if unions > _STRICT_MAX_UNION_PARAMS:
        problems.append(f"union parameters {unions}")
    if problems:
        logger.warning(
            "live runner: strict tool use disabled (%s)",
            ", ".join(dict.fromkeys(problems)),
        )
        return False
    return True


@dataclass(frozen=True)
class _LivePlanRequestShape:
    """Messages API tool settings for one resolved planner model."""

    tool_choice: dict[str, str]
    strict: bool
    max_tokens: int
    output_config: dict[str, str] | None


def _live_plan_request_shape(
    model: str, plan_schema: dict[str, Any]
) -> _LivePlanRequestShape:
    """Pick tool_choice, strictness, effort, and max_tokens for ``model``.

    Opus 5.5 uses automatic tool choice (forced tool use is a 400) and
    strict tool use when the schema allows it. Other models keep a forced
    ``submit_enablement_plan`` call and omit effort, thinking, and sampling
    overrides.
    """
    if _model_rejects_forced_tool_choice(model):
        return _LivePlanRequestShape(
            tool_choice={"type": "auto"},
            strict=_schema_allows_strict_tool(plan_schema),
            max_tokens=_OPUS_55_MAX_TOKENS,
            output_config={"effort": _OPUS_55_EFFORT},
        )
    return _LivePlanRequestShape(
        tool_choice={"type": "tool", "name": _SUBMIT_TOOL_NAME},
        strict=False,
        max_tokens=_MAX_TOKENS,
        output_config=None,
    )


def _assistant_content_for_retry(content: list[Any]) -> list[Any]:
    """Echo assistant blocks unchanged, including empty thinking signatures.

    Opus 5.5 rejects a follow-up turn that drops, edits, or reorders
    thinking blocks. ``exclude_none`` keeps an empty ``thinking`` string.
    """
    echoed: list[Any] = []
    for block in content:
        dump = getattr(block, "model_dump", None)
        if dump is None:
            echoed.append(block)
            continue
        echoed.append(dump(mode="json", exclude_none=True))
    return echoed


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
    role_lower = role.display_name.lower()
    return f"""\
You are the {role.display_name} Enablement Agent for Enable AI.

Your task: produce a structured EnablementPlan for the tools listed below, for a person whose job is {role_lower}. Call `submit_enablement_plan` exactly once when your work is complete. That call is required even when tool choice is automatic — a text-only reply cannot be turned into a plan.

## Selected tool ids

{", ".join(tools)}

These ids are the only tools in this run. A previous plan for this role is not an input. Do not reuse its themes.

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

Selected tools override the role playbook. Invent findings and recommendations from the catalog entries above (categories, notes, native AI features, API surface). The role ({role.display_name}) only says who will use the workflow.

For each selected tool, write a capability finding whose name is work that tool can actually do. Decide a status of covered, partial, gap, or redundant from the catalog data. Those four words belong only in `capability_coverage.status`. Every finding's `tools_involved` must be a subset of the selected tool ids.

Then translate those findings into recommendations that use the selected tools. Each recommendation `kind` must be exactly one of these four strings:
- `use_native_ai` — only when the native feature is genuinely sufficient with no augmentation
- `augment_with_custom_ai` — when native AI covers something but doesn't see cross-tool data
- `consolidate` — when two tools redundantly cover the same capability
- `orchestrate` — when value comes from composing multiple tools, including a capability whose status is gap

Never set recommendation `kind` to covered, partial, gap, or redundant.

Every recommendation must name the selected tools it uses, and `tools_affected` must be a subset of the selected tool ids. If the tools look unrelated, invent one coherent workflow that uses each tool for the job its catalog describes. Do not recommend a role-playbook theme — tutorials, code samples, docs-site work, or any other theme from domain knowledge — unless that theme appears in the catalog text above.

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

Call `submit_enablement_plan` exactly once when the plan is ready. Do not stop after reasoning in text. The tool's input schema IS the EnablementPlan schema — put `department`, `summary`, `capability_coverage`, `recommendations`, `orchestrator_pr_plan`, and `metadata` **at the top level of the tool input**. Do NOT wrap them in a `plan`, `enablement_plan`, `result`, or `data` envelope. Every required field of EnablementPlan must be present and correctly typed. Enum values must match exactly. No extra fields.
"""


def _build_system_prompt(role: Role) -> str:
    """Compose the system prompt from the role's domain knowledge.

    Researched roles carry markdown on `role.domain_knowledge` and have no
    directory. Seeded roles still load `domain_knowledge.md` from disk.
    """
    dk = role.domain_knowledge_text()
    return f"""\
You are the {role.display_name} Enablement Agent for Enable AI.

Your job: reason over the tools the user selected and produce a structured EnablementPlan for a {role.display_name.lower()} teammate using those tools.

You output the plan by calling the `submit_enablement_plan` tool exactly once when the plan is ready. That call is required even if tool choice is left on automatic — a prose-only reply is a failed run. You do not produce free-text reports. You do not call external APIs. You do not invent tools the user didn't include.

Selected tools override the role playbook. Domain knowledge below is background for the job, not a checklist of findings. Do not emit a theme from that background unless the selected tools' catalog entries are about that work. Do not reuse an earlier plan's themes when the tool list changed. If the tools look unrelated, invent one coherent cross-tool workflow from their catalog capabilities.

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


_VALID_KINDS = frozenset(
    {"use_native_ai", "augment_with_custom_ai", "consolidate", "orchestrate"}
)
# Coverage words the model sometimes copies into recommendation.kind.
_KIND_FROM_STATUS = {
    "gap": "orchestrate",
    "partial": "augment_with_custom_ai",
    "covered": "use_native_ai",
    "redundant": "consolidate",
}


def _coerce_recommendation_kinds(args: dict[str, Any]) -> dict[str, Any]:
    """Map a coverage status used as recommendation.kind onto a real kind."""
    recommendations = args.get("recommendations")
    if not isinstance(recommendations, list):
        return args
    for rec in recommendations:
        if not isinstance(rec, dict):
            continue
        kind = rec.get("kind")
        if not isinstance(kind, str) or kind in _VALID_KINDS:
            continue
        mapped = _KIND_FROM_STATUS.get(kind.strip().lower())
        if mapped is None:
            continue
        logger.warning("live runner: mapping recommendation kind %r to %r", kind, mapped)
        rec["kind"] = mapped
    return args


def _extract_submit_args(tool_use_blocks: list[ToolUseBlock]) -> dict[str, Any]:
    """Find the submit_enablement_plan tool_use call and return its arguments."""
    for block in tool_use_blocks:
        if block.name == _SUBMIT_TOOL_NAME:
            args = block.input
            if isinstance(args, dict):
                return _unwrap_envelope(args)
    raise RuntimeError(
        "Model did not call submit_enablement_plan. Cannot construct a plan."
    )


def _no_tool_use_error(response: Any) -> RuntimeError:
    """Build the existing no-tool_use error from text blocks, not content[0].

    Opus 5.5 responses can begin with thinking blocks. Selecting by ``type``
    keeps the preview on the text the model actually wrote.
    """
    text_blocks = [
        block for block in response.content if getattr(block, "type", None) == "text"
    ]
    debug = (
        text_blocks[0].text[:300]  # type: ignore[union-attr]
        if text_blocks
        else "(no text or tool_use blocks)"
    )
    return RuntimeError(
        f"Live runner: model returned no tool_use. "
        f"stop_reason={response.stop_reason}. preview: {debug}"
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

    # The tool's input_schema is the EnablementPlan JSON Schema. Opus 5.5
    # marks the tool strict when that schema meets Anthropic's subset, so
    # the API constrains the call. Other models still go through Pydantic
    # after the forced tool_use.
    plan_schema = EnablementPlan.model_json_schema()

    client = AsyncAnthropic()
    model = resolve_live_plan_model()
    shape = _live_plan_request_shape(model, plan_schema)
    logger.info(
        "live runner: model=%s tool_choice=%s strict=%s max_tokens=%s role=%s tools=%s session=%s",
        model,
        shape.tool_choice.get("type"),
        shape.strict,
        shape.max_tokens,
        role.id,
        tools,
        session_id,
    )

    tool_def: dict[str, Any] = {
        "name": _SUBMIT_TOOL_NAME,
        "description": (
            "Submit the final structured EnablementPlan. Call this "
            "exactly once when your reasoning is complete. The input "
            "must conform to the EnablementPlan schema."
        ),
        "input_schema": plan_schema,
    }
    # Strict is omitted unless the schema passed the Opus 5.5 checks.
    # Sampling parameters and ``thinking`` are never set: Opus 5.5 rejects
    # non-default temperature/top_p/top_k and ``thinking: disabled``.
    if shape.strict:
        tool_def["strict"] = True

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
    create_kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": shape.max_tokens,
        "system": system_prompt,
        "tools": [tool_def],
        "tool_choice": shape.tool_choice,
    }
    if shape.output_config is not None:
        create_kwargs["output_config"] = shape.output_config

    # Automatic tool choice does not guarantee a call. One follow-up echoes
    # the assistant turn unchanged (thinking blocks included) and asks again.
    # Forced tool choice already requires the call, so it does not retry.
    attempts = 2 if shape.tool_choice.get("type") == "auto" else 1
    response: Any = None
    tool_uses: list[ToolUseBlock] = []
    for attempt in range(attempts):
        response = await client.messages.create(
            **create_kwargs,
            messages=list(messages),
        )
        tool_uses = [
            block for block in response.content if isinstance(block, ToolUseBlock)
        ]
        if tool_uses or attempt + 1 >= attempts:
            break
        logger.warning(
            "live runner: no tool_use (stop_reason=%s); retrying once",
            getattr(response, "stop_reason", None),
        )
        if getattr(response, "stop_reason", None) == "max_tokens":
            create_kwargs["max_tokens"] = max(
                int(create_kwargs["max_tokens"]),
                _OPUS_55_RETRY_MAX_TOKENS,
            )
        messages.append(
            {
                "role": "assistant",
                "content": _assistant_content_for_retry(list(response.content)),
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "You did not call submit_enablement_plan. Call it exactly "
                    "once now. Put department, summary, capability_coverage, "
                    "recommendations, orchestrator_pr_plan, and metadata at "
                    "the top level of the tool input."
                ),
            }
        )

    if not tool_uses:
        if response is None:
            raise RuntimeError(
                "Live runner: model returned no tool_use. "
                "stop_reason=None. preview: (no text or tool_use blocks)"
            )
        raise _no_tool_use_error(response)

    args = _coerce_recommendation_kinds(_extract_submit_args(tool_uses))
    try:
        plan = EnablementPlan.model_validate(args)
    except Exception as exc:  # noqa: BLE001 — surface Pydantic error message
        raise RuntimeError(
            f"Live runner: model returned malformed plan: {exc}"
        ) from exc
    loaded: list[ToolCapability] = []
    for tool_name in tools:
        cap = load_tool(user, tool_name)
        if cap is not None:
            loaded.append(cap)
    return apply_tool_grounding(plan, loaded, role)
