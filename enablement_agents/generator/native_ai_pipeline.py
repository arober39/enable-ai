"""Native-AI setup pipeline for `use_native_ai` recommendations.

A `use_native_ai` recommendation means "the vendor's native feature is
sufficient — don't build a custom orchestrator on top." Instead of a
runtime workflow we produce a step-by-step configuration guide:

  1. Reuse stage 1 (tool research) from the workflow pipeline.
  2. Emit a `NativeAISetupArtifact` via forced tool_use against its schema.

The result is a deliverable the user acts on (clicks through the
vendor's UI to enable + configure the feature) rather than something the
Enable AI runtime executes.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from anthropic import AsyncAnthropic
from anthropic.types import ToolUseBlock

from .artifacts import BuildResult, NativeAISetupArtifact
from .schemas import GeneratorContext, StageResult
from .workflow_pipeline import _stage1_research

logger = logging.getLogger(__name__)

_EMIT_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 3072


_EMIT_SYSTEM = """\
You are the Native-AI Setup stage of a recommendation-driven build pipeline.

The recommendation is a `use_native_ai` kind — the user is being told
"the vendor's native feature is enough; turn it on and connect it." DO
NOT propose custom orchestration, LLM steps, or workflow logic. The
deliverable is configuration guidance, not runtime code.

Produce a `NativeAISetupArtifact` describing:

- primary_tool: the tool whose native AI is being enabled (one of the
  selected stack tools).
- feature_name: the vendor's actual product name for the feature
  (e.g., "Fin", "Intelligent triage", "AI Compose", "Zendesk AI
  Agents"). Read it from the per-tool research provided in stage 1.
- setup_steps: a numbered list of concrete UI actions: where to click,
  what to enable, what to connect. Each step has a short title and a
  detail sentence describing what to look for. Be specific to the
  vendor's actual UI — don't write generic instructions.
- connected_sources: other tools/sources the feature needs connected
  to be useful (e.g., a knowledge base for an answer bot).
- success_criteria: 2-4 observable signals the user can check to
  confirm the feature is working (e.g., "Fin shows up as the assignee
  on resolved tier-1 conversations").

If a step requires a feature that isn't available on the user's plan or
in the vendor's catalog data, say so in the step's detail rather than
inventing instructions.

Call `submit_native_ai_setup` exactly once.
"""


async def _emit_native_ai_setup(
    ctx: GeneratorContext, research_payload: str
) -> tuple[NativeAISetupArtifact, str]:
    """Single Claude call → validated NativeAISetupArtifact + explanation."""
    schema = NativeAISetupArtifact.model_json_schema()
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

Produce a NativeAISetupArtifact. Hard constraints:
- primary_tool MUST be one of the tool canonical_names in the research
- feature_name MUST come from the vendor's actual catalog of features
  (look at native_ai_features in the research data)
- setup_steps MUST be ordered starting at 1 and contain at least 2 steps
- success_criteria MUST contain at least one observable signal
"""

    client = AsyncAnthropic()
    response = await client.messages.create(
        model=_EMIT_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_EMIT_SYSTEM,
        tools=[
            {
                "name": "submit_native_ai_setup",
                "description": "Submit the NativeAISetupArtifact + a short explanation. Call exactly once.",
                "input_schema": wrapper_schema,
            }
        ],
        tool_choice={"type": "tool", "name": "submit_native_ai_setup"},
        messages=[{"role": "user", "content": user_message}],
    )
    blocks = [b for b in response.content if isinstance(b, ToolUseBlock)]
    if not blocks:
        raise RuntimeError(
            f"native_ai pipeline: model returned no tool_use; "
            f"stop_reason={response.stop_reason}"
        )
    args = blocks[0].input
    if not isinstance(args, dict):
        raise RuntimeError("native_ai pipeline: tool_use args were not a dict")
    raw_artifact = args.get("artifact")
    if not isinstance(raw_artifact, dict):
        raise RuntimeError("native_ai pipeline: response missing `artifact`")
    return (
        NativeAISetupArtifact.model_validate(raw_artifact),
        str(args.get("explanation") or ""),
    )


def _now() -> datetime:
    return datetime.now(UTC)


async def build_native_ai_setup(ctx: GeneratorContext) -> BuildResult:
    """2-stage pipeline: tool research → emit native-AI setup artifact."""
    stages: list[StageResult] = []

    # Stage 1 — reuse the workflow pipeline's research stage
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

    # Stage 2 — emit
    s_start = _now()
    try:
        artifact, explanation = await _emit_native_ai_setup(ctx, research_payload)
        # Sanity check: primary_tool must be a tool the user selected
        allowed = {c.canonical_name for c in ctx.tool_capabilities}
        if artifact.primary_tool not in allowed:
            raise RuntimeError(
                f"primary_tool {artifact.primary_tool!r} not in user's "
                f"selected tools: {sorted(allowed)}"
            )
        stages.append(
            StageResult(
                name="plan",
                ok=True,
                started_at=s_start,
                ended_at=_now(),
                detail=f"emitted {len(artifact.setup_steps)} setup step(s)",
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
        artifact_kind="native_ai_setup",
        native_ai_setup=artifact,
        explanation=explanation,
    )
