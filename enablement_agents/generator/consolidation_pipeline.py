"""Consolidation pipeline for `consolidate` recommendations.

A `consolidate` recommendation means "two tools redundantly cover the
same capability — pick one and migrate off the other." The deliverable
is not runtime code; it's a structured migration plan the user executes
themselves (or hands to ops).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from anthropic import AsyncAnthropic
from anthropic.types import ToolUseBlock

from .artifacts import BuildResult, ConsolidationPlanArtifact
from .schemas import GeneratorContext, StageResult
from .workflow_pipeline import _stage1_research

logger = logging.getLogger(__name__)

_EMIT_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 3072

_EMIT_SYSTEM = """\
You are the Consolidation Plan stage of a recommendation-driven build
pipeline.

The recommendation is a `consolidate` kind — the user is being told
"two tools cover the same capability; migrate from one to the other."
DO NOT produce custom orchestration or LLM steps. The deliverable is a
structured migration plan.

Produce a `ConsolidationPlanArtifact` describing:

- source_tool / target_tool: canonical tool names. Pick from the user's
  selected stack. Justify the direction in the summary (typically the
  tool with stronger coverage of the capability is the target).
- items_to_migrate: every category of stuff that needs to move (FAQ
  articles, ticket macros, tags, automations, custom fields, etc.).
  Each item has a name, source, target, method (concrete: "Export
  CSV from Zendesk Guide → Import to Intercom Help Center via …"),
  and optional notes.
- pre_migration_checklist: things to verify before starting (e.g.,
  "back up the source tool", "confirm target tool's quota").
- post_migration_checklist: things to verify after (e.g., "all
  articles searchable in target", "redirects in place from old URLs").
- risks: realistic things that could go wrong (orphaned references,
  search-relevance regression, broken deep links).

Be concrete. Use the actual tool names from the research, not generic
language. If a category isn't covered by the catalog data, leave a note
saying you're uncertain rather than fabricating a method.

Call `submit_consolidation_plan` exactly once.
"""


async def _emit_consolidation_plan(
    ctx: GeneratorContext, research_payload: str
) -> tuple[ConsolidationPlanArtifact, str]:
    schema = ConsolidationPlanArtifact.model_json_schema()
    wrapper_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "artifact": schema,
            "explanation": {
                "type": "string",
                "description": "Short paragraph the UI shows next to the result.",
            },
        },
        "required": ["artifact", "explanation"],
    }

    user_message = f"""\
## Recommendation
{ctx.recommendation.model_dump_json(indent=2)}

## Per-tool research (stage 1)
{research_payload}

## Role context
- role_id: {ctx.role_id}
- role_display_name: {ctx.role_display_name}

Produce a ConsolidationPlanArtifact. Hard constraints:
- source_tool and target_tool MUST both be canonical tool names from
  the research and MUST be different from each other
- items_to_migrate MUST contain at least one concrete item
- Each item's method MUST name a real action (export/import/script/etc.),
  not "TBD" or "find a way"
"""

    client = AsyncAnthropic()
    response = await client.messages.create(
        model=_EMIT_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_EMIT_SYSTEM,
        tools=[
            {
                "name": "submit_consolidation_plan",
                "description": "Submit the ConsolidationPlanArtifact + a short explanation. Call exactly once.",
                "input_schema": wrapper_schema,
            }
        ],
        tool_choice={"type": "tool", "name": "submit_consolidation_plan"},
        messages=[{"role": "user", "content": user_message}],
    )
    blocks = [b for b in response.content if isinstance(b, ToolUseBlock)]
    if not blocks:
        raise RuntimeError(
            f"consolidation pipeline: model returned no tool_use; "
            f"stop_reason={response.stop_reason}"
        )
    args = blocks[0].input
    if not isinstance(args, dict):
        raise RuntimeError("consolidation pipeline: tool_use args were not a dict")
    raw_artifact = args.get("artifact")
    if not isinstance(raw_artifact, dict):
        raise RuntimeError("consolidation pipeline: response missing `artifact`")
    return (
        ConsolidationPlanArtifact.model_validate(raw_artifact),
        str(args.get("explanation") or ""),
    )


def _now() -> datetime:
    return datetime.now(UTC)


async def build_consolidation_plan(ctx: GeneratorContext) -> BuildResult:
    """2-stage pipeline: tool research → emit consolidation plan artifact."""
    stages: list[StageResult] = []

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

    research_payload = json.dumps(
        [r.model_dump(mode="json") for r in research], indent=2
    )

    s_start = _now()
    try:
        artifact, explanation = await _emit_consolidation_plan(ctx, research_payload)
        allowed = {c.canonical_name for c in ctx.tool_capabilities}
        if artifact.source_tool not in allowed or artifact.target_tool not in allowed:
            raise RuntimeError(
                f"source/target tools not both in user's selected tools: "
                f"source={artifact.source_tool!r} target={artifact.target_tool!r} "
                f"allowed={sorted(allowed)}"
            )
        if artifact.source_tool == artifact.target_tool:
            raise RuntimeError(
                "source_tool and target_tool are the same — consolidation requires a direction"
            )
        stages.append(
            StageResult(
                name="plan",
                ok=True,
                started_at=s_start,
                ended_at=_now(),
                detail=f"emitted {len(artifact.items_to_migrate)} item(s) to migrate",
                output_preview=artifact.summary[:200],
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
        artifact_kind="consolidation_plan",
        consolidation_plan=artifact,
        explanation=explanation,
    )
