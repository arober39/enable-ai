"""2-stage LLM pipeline that emits a `WorkflowDefinition` (Phase 2.1).

Stage 1: tool research — reuses `_stage1_research` from the 1.4 codegen
pipeline. Per-tool surface area for THIS recommendation.

Stage 2: emit a WorkflowDefinition via forced tool_use. Structured
output validated by Pydantic — no Python is ever generated or executed
from LLM output.

The output is `WorkflowDefinition`, persisted as JSON by the API layer.
The interpreter (reviewed Python) runs it.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import ToolUseBlock
from pydantic import BaseModel, ConfigDict, Field

from core.credentials import runtime_credentials
from core.identity import UserContext
from core.tool_catalog import ToolCapability
from core.workflow import WorkflowDefinition, WorkflowStep, referenced_tools

from .artifacts import BuildResult
from .pipeline import _stage1_research  # reused from 1.4
from .schemas import GeneratorContext, StageResult, ToolResearch
from ..tool_adapters import builtin as _builtin  # noqa: F401 — registers builtins
from ..tool_adapters.registry import describe_actions

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_EMIT_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 4096


#: Match `{{ request.foo }}` / `{{request.foo.bar}}` in string interpolation.
_TEMPLATE_REQUEST_REF = re.compile(
    r"\{\{\s*request\.([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}"
)


def _collect_top_level_request_refs(definition: WorkflowDefinition) -> set[str]:
    """Return every top-level `request.X` key referenced by any step.

    Walks step params (both `{"$ref": "request.X"}` and string interpolation
    forms) and condition operands. Returns just the top-level key (X), so
    `request.customer.email` contributes `customer`. The interpreter resolves
    `null` for paths missing in the actual payload, so we only need to
    ensure the top-level keys exist.
    """
    refs: set[str] = set()

    def add(path: str) -> None:
        head = path.split(".", 1)[0]
        if head:
            refs.add(head)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if set(value.keys()) == {"$ref"} and isinstance(value["$ref"], str):
                ref = value["$ref"]
                if ref.startswith("request."):
                    add(ref[len("request."):])
                return
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
        elif isinstance(value, str):
            for m in _TEMPLATE_REQUEST_REF.finditer(value):
                add(m.group(1))

    step: WorkflowStep
    for step in definition.steps:
        walk(step.params)
        if step.condition is not None:
            walk(step.condition.left)
            walk(step.condition.right)
    return refs


def _augment_sample_request(definition: WorkflowDefinition) -> list[str]:
    """Ensure sample_request has every key the workflow's steps reference.

    The LLM tends to write a sample that *sounds* useful (CRM context, tier
    info) but doesn't match the keys the workflow actually reads. We can't
    rely on the model to keep these aligned, so after emit we extract the
    refs and add placeholder values for any keys missing from sample_request.

    Returns the list of keys that were augmented (for logging).
    """
    refs = _collect_top_level_request_refs(definition)
    existing = set(definition.sample_request.keys())
    missing = sorted(refs - existing)
    if missing:
        for key in missing:
            definition.sample_request[key] = f"<replace with your {key}>"
    return missing


_EMIT_SYSTEM = """\
You are the Workflow Emit stage of a 2-stage workflow builder.

Given a recommendation, the per-tool research from stage 1, and a
catalog of which actions each tool supports, you produce a
WorkflowDefinition: a small ordered list of steps the runtime
interpreter will execute.

Hard rules for the steps you emit:

- Step ids are lowercase_snake_case and unique within the workflow.
- Use ONLY tool names listed in `available_tools_and_actions` plus the
  three special tools: `llm` (Claude calls), `return` (final output),
  `set` (context reshape). Never invent a tool or action.
- Use ONLY action names listed for each tool. Never invent an action.
- params is a JSON object. Two ways to reference earlier values:
    (a) Atomic refs in dict form: {"$ref": "<dotted.path>"} preserves the
        resolved value's type. Use this for ids, lists, structured data.
        Examples:
          {"$ref": "request.body"}
          {"$ref": "steps.search.articles.0.id"}
    (b) String interpolation inside string params: `{{ dotted.path }}`
        — the runtime substitutes the value (json-encoded for dicts/lists).
        Use this inside `llm` `system`/`user` prompts where you want to
        inline an earlier step's output as part of a longer instruction.
        Example:
          "user": "Ticket: {{ steps.fetch_ticket }}\\nDecide intent."
- For llm steps, the `model` param is OPTIONAL. If you set it, use EXACTLY
  one of: "claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001".
  Otherwise omit the model param and the runtime will pick a sensible
  default. Do NOT use older model ids like `claude-3-5-sonnet-*`.
- Conditions are tiny equality checks: {"op": "eq", "left": <ref>, "right": <literal>}.
  Anything more complex is not supported in v1 — design the workflow
  without it.
- The LAST step MUST be a `return` step. Its params become the
  workflow's final response.
- Refer only to env vars listed in `available_credentials`. The
  generated workflow's `env_vars_required` lists what it actually uses.

Call `submit_workflow_definition` exactly once.
"""


async def _stage2_emit(
    ctx: GeneratorContext, research: list[ToolResearch]
) -> tuple[WorkflowDefinition, str]:
    # Filter the action catalog to ONLY the user's selected tools plus the
    # always-available special tools. The model can't reference what it
    # can't see, which prevents the "model emits hubspot step when user
    # only picked zendesk" failure mode.
    full_actions = describe_actions()
    allowed_tools = {c.canonical_name for c in ctx.tool_capabilities}
    special = {"llm", "return", "set"}
    actions = {
        tool: actions_map
        for tool, actions_map in full_actions.items()
        if tool in allowed_tools or tool in special
    }

    schema = WorkflowDefinition.model_json_schema()
    # WorkflowDefinition has `default_factory=dict` on sample_request so
    # legacy persisted files load cleanly — but that makes Pydantic mark
    # the field optional in the JSON schema, and the LLM skips it. For
    # new generations we force `sample_request` into `required` and
    # require it be non-empty (≥1 property). Loading is unaffected.
    schema_required = list(schema.get("required") or [])
    if "sample_request" not in schema_required:
        schema_required.append("sample_request")
    schema["required"] = schema_required
    if (props := schema.get("properties")) and "sample_request" in props:
        props["sample_request"]["minProperties"] = 1

    # Force a top-level explanation alongside the definition.
    wrapper_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "definition": schema,
            "explanation": {
                "type": "string",
                "description": "Short paragraph the UI shows next to the build result.",
            },
        },
        "required": ["definition", "explanation"],
    }

    user_message = f"""\
## Recommendation
{ctx.recommendation.model_dump_json(indent=2)}

## Per-tool research (stage 1)
{json.dumps([r.model_dump(mode="json") for r in research], indent=2)}

## Available tools and actions (use ONLY these)
{json.dumps(actions, indent=2)}

## Available credentials (env var names already stored in the vault)
{json.dumps(sorted(ctx.available_credentials))}

## Role context
- role_id: {ctx.role_id}
- role_display_name: {ctx.role_display_name}

Produce a WorkflowDefinition. Field requirements:
- role_id: {ctx.role_id!r}
- recommendation_id: {ctx.recommendation.id!r}
- name: short title for this workflow
- description: one-paragraph explanation
- tools_used: every non-special tool referenced in steps
- env_vars_required: every credential the steps need
- steps: ordered list ending with a `return` step
- request_schema / response_schema: shape hints (informational)
- sample_request: a CONCRETE example request the user can paste into the
  UI to test the workflow. CRITICAL: its keys MUST exactly match every
  top-level `request.X` reference your steps make via `{{request.X}}` or
  `{{"$ref": "request.X"}}`. If your first step reads
  `{{"$ref": "request.conversation_id"}}`, sample_request must include
  `"conversation_id"`. Do not add aspirational keys the workflow won't
  read; do not omit keys the workflow does read.
"""

    client = AsyncAnthropic()
    response = await client.messages.create(
        model=_EMIT_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_EMIT_SYSTEM,
        tools=[
            {
                "name": "submit_workflow_definition",
                "description": (
                    "Submit the structured WorkflowDefinition + a user-facing "
                    "explanation. Call exactly once."
                ),
                "input_schema": wrapper_schema,
            }
        ],
        tool_choice={"type": "tool", "name": "submit_workflow_definition"},
        messages=[{"role": "user", "content": user_message}],
    )
    tool_uses = [b for b in response.content if isinstance(b, ToolUseBlock)]
    if not tool_uses:
        raise RuntimeError(
            f"model returned no tool_use for emit; stop_reason={response.stop_reason}"
        )
    args = tool_uses[0].input
    if not isinstance(args, dict):
        raise RuntimeError("emit tool_use args were not a dict")

    raw_def = args.get("definition")
    if not isinstance(raw_def, dict):
        raise RuntimeError("emit response missing `definition`")
    # Force the role_id / recommendation_id fields to match the request — the
    # model occasionally rewrites these.
    raw_def["role_id"] = ctx.role_id
    raw_def["recommendation_id"] = ctx.recommendation.id
    explanation = str(args.get("explanation") or "")
    return WorkflowDefinition.model_validate(raw_def), explanation


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


async def build_workflow(
    user: UserContext, ctx: GeneratorContext
) -> BuildResult:
    """Run the 2-stage workflow pipeline. Returns a `BuildResult`.

    The caller (API layer) decides whether to persist the resulting
    `WorkflowDefinition` via `core.workflow_storage.save_workflow`.
    """
    creds = runtime_credentials()
    if not creds.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. The workflow pipeline requires it. "
            "Add it via the Settings page in the UI."
        )

    stages: list[StageResult] = []
    definition: WorkflowDefinition | None = None
    explanation: str | None = None
    env_vars: list[str] = []

    # --- Stage 1 — reuse 1.4's tool research stage
    s_start = _now()
    try:
        research = await _stage1_research(ctx)
        stages.append(
            StageResult(
                name="research",
                ok=True,
                started_at=s_start,
                ended_at=_now(),
                detail=f"researched {len(research)} tool(s)",
                output_preview=json.dumps([r.canonical_name for r in research]),
            )
        )
    except Exception as exc:  # noqa: BLE001
        stages.append(
            StageResult(
                name="research",
                ok=False,
                started_at=s_start,
                ended_at=_now(),
                detail=str(exc),
            )
        )
        return BuildResult(ok=False, stages=stages, artifact_kind="none")

    # --- Stage 2 — emit WorkflowDefinition
    s_start = _now()
    try:
        definition, explanation = await _stage2_emit(ctx, research)
        env_vars = list(definition.env_vars_required)
        # Sanity check: every non-special tool the workflow references must
        # be in `referenced_tools` of the catalog we sent — i.e., the model
        # didn't hallucinate a tool. Validate now to fail fast.
        referenced = set(referenced_tools(definition))
        allowed = {c.canonical_name for c in ctx.tool_capabilities}
        unknown = referenced - allowed
        if unknown:
            raise RuntimeError(
                f"workflow references tools not in the catalog: {sorted(unknown)}"
            )
        # Align sample_request with the keys the steps actually read.
        # The model often writes an aspirational sample that doesn't
        # match its own steps' `request.X` refs — replace missing keys
        # with placeholders the user can fill in.
        augmented_keys = _augment_sample_request(definition)
        if augmented_keys:
            logger.warning(
                "sample_request augmented with placeholders for refs the model "
                "missed: %s",
                augmented_keys,
            )
        detail = f"emitted {len(definition.steps)} step(s)"
        if augmented_keys:
            detail += (
                f"; sample_request gained {len(augmented_keys)} placeholder "
                f"key(s) to match step refs: {augmented_keys}"
            )
        stages.append(
            StageResult(
                name="plan",
                ok=True,
                started_at=s_start,
                ended_at=_now(),
                detail=detail,
                output_preview=definition.description[:200],
            )
        )
    except Exception as exc:  # noqa: BLE001
        stages.append(
            StageResult(
                name="plan",
                ok=False,
                started_at=s_start,
                ended_at=_now(),
                detail=str(exc),
            )
        )
        return BuildResult(ok=False, stages=stages, artifact_kind="none")

    return BuildResult(
        ok=True,
        stages=stages,
        artifact_kind="workflow",
        workflow=definition,
        explanation=explanation,
        env_vars_required=env_vars,
    )
