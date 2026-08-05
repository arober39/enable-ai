"""4-stage LLM-driven orchestrator generator.

Stages run sequentially. Each is one Anthropic API call with forced
tool_use against a Pydantic schema, so structured-output validation is
free. The final stage is a local import check — no LLM call.

Output destination is `orchestrators/<user_id>/<role>/` per the locked
phase 1 commitment #3 (per-user state layout). The legacy committed
`orchestrators/support/` is untouched.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import ToolUseBlock

from core.credentials import runtime_credentials
from core.identity import UserContext
from core.state import orchestrator_path

from .schemas import (
    CodePlan,
    GeneratedCode,
    GeneratorContext,
    GeneratorRunResult,
    StageName,
    StageResult,
    ToolResearch,
)

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_PLAN_MODEL = "claude-haiku-4-5-20251001"
_GENERATE_MODEL = "claude-sonnet-4-6"  # Use a stronger model for codegen
_MAX_TOKENS = 4096


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _strip_source_field(schema: dict[str, Any]) -> dict[str, Any]:
    """JSON schema cleanup: remove `source` field (loader-populated)."""
    props = schema.get("properties") or {}
    if "source" in props:
        del props["source"]
    required = schema.get("required") or []
    schema["required"] = [r for r in required if r != "source"]
    return schema


def _ensure_api_key() -> None:
    creds = runtime_credentials()
    if not creds.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. The generator requires it. "
            "Add it via the Settings page in the UI."
        )


async def _force_tool_use(
    *,
    model: str,
    system: str,
    user_message: str,
    tool_name: str,
    tool_description: str,
    input_schema: dict[str, Any],
) -> dict[str, Any]:
    """One forced-tool-use Claude call → validated dict from tool_use args."""
    client = AsyncAnthropic()
    response = await client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        system=system,
        tools=[
            {
                "name": tool_name,
                "description": tool_description,
                "input_schema": input_schema,
            }
        ],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user_message}],
    )
    tool_uses = [b for b in response.content if isinstance(b, ToolUseBlock)]
    if not tool_uses:
        raise RuntimeError(
            f"model returned no {tool_name} tool_use; "
            f"stop_reason={response.stop_reason}."
        )
    args = tool_uses[0].input
    if not isinstance(args, dict):
        raise RuntimeError(f"{tool_name} args were not a dict")
    return args


# ---------------------------------------------------------------------------
# Stage 1 — research selected tools' API/MCP surface for THIS recommendation
# ---------------------------------------------------------------------------


_STAGE1_SYSTEM = """\
You are the Tool Research stage of a 4-stage orchestrator generator.

Given a recommendation and a set of selected tools, you produce per-tool
ToolResearch records describing exactly what the orchestrator will need
from each tool to implement this recommendation. Be specific: name the
endpoints / MCP tools / env vars that will appear in the generated code.

Do not invent endpoints or MCP tools that aren't listed in the tool's
catalog data. If unclear what's needed, leave the list empty and add a
note explaining the uncertainty.
"""


async def _stage1_research(ctx: GeneratorContext) -> list[ToolResearch]:
    catalog_blob = json.dumps(
        [c.model_dump(mode="json") for c in ctx.tool_capabilities],
        indent=2,
    )
    user_message = f"""\
## Recommendation
{ctx.recommendation.model_dump_json(indent=2)}

## Selected tools (capabilities catalog)
{catalog_blob}

## Available user credentials (env var names already stored in the vault)
{json.dumps(sorted(ctx.available_credentials))}

Produce one ToolResearch record per selected tool. Call
`submit_tool_research` exactly once with the array.
"""
    array_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "researches": {
                "type": "array",
                "items": _strip_source_field(ToolResearch.model_json_schema()),
            }
        },
        "required": ["researches"],
    }
    args = await _force_tool_use(
        model=_DEFAULT_MODEL,
        system=_STAGE1_SYSTEM,
        user_message=user_message,
        tool_name="submit_tool_research",
        tool_description=(
            "Submit the per-tool research array. Call exactly once."
        ),
        input_schema=array_schema,
    )
    raw_items = args.get("researches") or []
    return [ToolResearch.model_validate(r) for r in raw_items]


# ---------------------------------------------------------------------------
# Stage 2 — plan the code structure
# ---------------------------------------------------------------------------


_STAGE2_SYSTEM = """\
You are the Code Plan stage of a 4-stage orchestrator generator.

Given a recommendation + per-tool research, you produce a CodePlan
describing the shape of the orchestrator code that will be generated:
which files, their purposes, the env vars consumed, and the input/output
shapes of the orchestrator's `handle_request` function.

For phase 1, prefer a single-file orchestrator (`orchestrator.py`)
unless the recommendation truly demands more. Keep it simple — this
code will run in single-user-local mode.

The orchestrator MUST read credentials through `core.credentials.runtime_credentials()`,
NOT directly from `os.environ`. Reference only env var names that
appear in the available_credentials list (or note that the user needs
to add a credential).
"""


async def _stage2_plan(
    ctx: GeneratorContext, research: list[ToolResearch]
) -> CodePlan:
    user_message = f"""\
## Recommendation
{ctx.recommendation.model_dump_json(indent=2)}

## Per-tool research from stage 1
{json.dumps([r.model_dump(mode="json") for r in research], indent=2)}

## Available user credentials
{json.dumps(sorted(ctx.available_credentials))}

Produce a CodePlan. Call `submit_code_plan` exactly once.

Hard constraints for the planned code:
- async function `handle_request(payload: dict) -> dict` is the entry point
- credentials read via `core.credentials.runtime_credentials()`
- no shell-out, no subprocess, no file writes outside `orchestrators/<user_id>/<role>/`
- gracefully degrade to a stub response when required creds are missing
"""
    args = await _force_tool_use(
        model=_PLAN_MODEL,
        system=_STAGE2_SYSTEM,
        user_message=user_message,
        tool_name="submit_code_plan",
        tool_description=("Submit the structured CodePlan. Call exactly once."),
        input_schema=CodePlan.model_json_schema(),
    )
    return CodePlan.model_validate(args)


# ---------------------------------------------------------------------------
# Stage 3 — generate the actual Python source
# ---------------------------------------------------------------------------


_STAGE3_SYSTEM = """\
You are the Code Generation stage of a 4-stage orchestrator generator.

Given a CodePlan + tool research + recommendation, produce the complete
Python source for `orchestrator.py`. The file MUST:

1. Define an async function `handle_request(payload: dict) -> dict`
   that implements the recommendation against the selected tools.
2. Read credentials via:
       from core.credentials import runtime_credentials
       _CREDS = runtime_credentials()
       api_key = _CREDS.get("SOME_KEY")
   Never call `os.environ.get` directly for credentials.
3. Load .env transparently:
       from dotenv import find_dotenv, load_dotenv
       load_dotenv(find_dotenv(usecwd=True), override=False)
4. Gracefully degrade when a required credential is missing — return a
   structured stub response with an "error" or "stub" key.
5. Use standard library + `httpx` + `pydantic` for I/O. No external
   SDK imports unless the catalog data confirms the package exists.
6. Be self-contained — no imports from `orchestrators.support.*` or any
   other path under `orchestrators/`. Importable as a single file.
7. Include a brief module docstring naming the recommendation it
   implements and which tools it calls.

Output the source as a single string in the `source` field. Output a
short user-facing explanation in `explanation`.

Call `submit_generated_code` exactly once.
"""


async def _stage3_generate(
    ctx: GeneratorContext,
    research: list[ToolResearch],
    plan: CodePlan,
) -> GeneratedCode:
    user_message = f"""\
## Recommendation
{ctx.recommendation.model_dump_json(indent=2)}

## Per-tool research
{json.dumps([r.model_dump(mode="json") for r in research], indent=2)}

## Code plan
{plan.model_dump_json(indent=2)}

## Role context
- role_id: {ctx.role_id}
- role_display_name: {ctx.role_display_name}

## Available credentials
{json.dumps(sorted(ctx.available_credentials))}

Produce the complete source for orchestrator.py.
"""
    args = await _force_tool_use(
        model=_GENERATE_MODEL,
        system=_STAGE3_SYSTEM,
        user_message=user_message,
        tool_name="submit_generated_code",
        tool_description=(
            "Submit the generated orchestrator.py source. Call exactly once."
        ),
        input_schema=GeneratedCode.model_json_schema(),
    )
    return GeneratedCode.model_validate(args)


# ---------------------------------------------------------------------------
# Stage 4 — write to disk, import-check, validate the contract
# ---------------------------------------------------------------------------


def _stage4_verify(
    user: UserContext, role_id: str, source: str
) -> tuple[Path, str | None]:
    """Write the source to disk, import it, validate handle_request exists.

    Returns (output_path, error_or_none).
    """
    out_dir = orchestrator_path(user, role_id)
    # Clean slate — the generator owns this directory.
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    (out_dir / "__init__.py").touch()
    target = out_dir / "orchestrator.py"
    target.write_text(source, encoding="utf-8")

    # Import-check
    spec = importlib.util.spec_from_file_location(
        f"_generated_orch_{user.user_id}_{role_id}", target
    )
    if spec is None or spec.loader is None:
        return out_dir, "could not create import spec for generated file"
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001
        return out_dir, f"generated file failed to import: {exc!r}"

    handler = getattr(module, "handle_request", None)
    if handler is None:
        return out_dir, "generated file does not export `handle_request`"
    if not inspect.iscoroutinefunction(handler):
        return out_dir, "generated `handle_request` is not async"
    return out_dir, None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_pipeline(
    user: UserContext, ctx: GeneratorContext
) -> GeneratorRunResult:
    """Run the 4-stage generator and return the structured result."""
    _ensure_api_key()
    stages: list[StageResult] = []
    plan: CodePlan | None = None
    explanation: str | None = None
    env_vars: list[str] = []

    # --- Stage 1
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
                output_preview=json.dumps(
                    [r.canonical_name for r in research]
                ),
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
        return _finish(False, "", stages, plan, explanation, env_vars)

    # --- Stage 2
    s_start = _now()
    try:
        plan = await _stage2_plan(ctx, research)
        env_vars = list(plan.env_vars_required)
        stages.append(
            StageResult(
                name="plan",
                ok=True,
                started_at=s_start,
                ended_at=_now(),
                detail=f"planned {len(plan.files)} file(s)",
                output_preview=plan.summary[:200],
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
        return _finish(False, "", stages, plan, explanation, env_vars)

    # --- Stage 3
    s_start = _now()
    try:
        gen = await _stage3_generate(ctx, research, plan)
        explanation = gen.explanation
        stages.append(
            StageResult(
                name="generate",
                ok=True,
                started_at=s_start,
                ended_at=_now(),
                detail=f"generated {len(gen.source.splitlines())} lines",
                output_preview=gen.explanation[:200],
            )
        )
    except Exception as exc:  # noqa: BLE001
        stages.append(
            StageResult(
                name="generate",
                ok=False,
                started_at=s_start,
                ended_at=_now(),
                detail=str(exc),
            )
        )
        return _finish(False, "", stages, plan, explanation, env_vars)

    # --- Stage 4
    s_start = _now()
    try:
        out_dir, err = _stage4_verify(user, ctx.role_id, gen.source)
        if err is None:
            stages.append(
                StageResult(
                    name="verify",
                    ok=True,
                    started_at=s_start,
                    ended_at=_now(),
                    detail="import + handle_request contract OK",
                )
            )
            return _finish(
                True, str(out_dir), stages, plan, explanation, env_vars
            )
        stages.append(
            StageResult(
                name="verify",
                ok=False,
                started_at=s_start,
                ended_at=_now(),
                detail=err,
            )
        )
        return _finish(False, str(out_dir), stages, plan, explanation, env_vars)
    except Exception as exc:  # noqa: BLE001
        stages.append(
            StageResult(
                name="verify",
                ok=False,
                started_at=s_start,
                ended_at=_now(),
                detail=str(exc),
            )
        )
        return _finish(False, "", stages, plan, explanation, env_vars)


def _finish(
    ok: bool,
    output_path: str,
    stages: list[StageResult],
    plan: CodePlan | None,
    explanation: str | None,
    env_vars: list[str],
) -> GeneratorRunResult:
    # Compute repo-relative path for display when possible
    if output_path:
        try:
            from core.state import repo_root

            output_path = str(Path(output_path).relative_to(repo_root()))
        except Exception:  # noqa: BLE001
            pass
    return GeneratorRunResult(
        ok=ok,
        output_path=output_path,
        stages=stages,
        plan=plan,
        explanation=explanation,
        env_vars_required=env_vars,
    )
