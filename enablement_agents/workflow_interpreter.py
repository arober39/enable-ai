"""Fixed runtime for `WorkflowDefinition`s.

This is the code the platform team owns — reviewed, tested, and shared
across every user. LLM output never executes; only WorkflowDefinition
JSON does, and only through the actions registered in the adapter
registry.

Execution model:
1. Build a `context` dict seeded with the inbound request:
   `{"request": <payload>, "steps": {}}`
2. For each step, in order:
   - Resolve $ref markers in params against context.
   - If `condition` is set, evaluate it; skip step if false.
   - Dispatch (tool, action, resolved_params, credentials) to the adapter.
   - Stash output at `context["steps"][step.output_key or step.id]`.
   - If the step's tool is `return`, remember its output as the final result.
3. Return the last `return` output, or a fallback summary if no `return` ran.
"""

from __future__ import annotations

import json as _json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.credentials import Credentials
from core.workflow import EqualityCondition, WorkflowDefinition, WorkflowStep

from .tool_adapters import builtin as _builtin  # noqa: F401 — side-effect: registers adapters
from .tool_adapters.registry import get_adapter

logger = logging.getLogger(__name__)


class StepTrace(BaseModel):
    """Per-step record for the UI to render an execution trace."""

    model_config = ConfigDict(extra="forbid")

    id: str
    tool: str
    action: str
    skipped: bool
    started_at: datetime
    ended_at: datetime
    params_resolved: dict[str, Any]
    output: dict[str, Any] | None = None
    error: str | None = None


class WorkflowRunResult(BaseModel):
    """Final result of a workflow run."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    output: dict[str, Any] = Field(default_factory=dict)
    trace: list[StepTrace] = Field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Reference resolution
# ---------------------------------------------------------------------------


def _walk_path(context: dict[str, Any], dotted: str) -> Any:
    """Resolve `a.b.c` against context. Returns None if any segment is missing."""
    cur: Any = context
    for segment in dotted.split("."):
        if isinstance(cur, dict) and segment in cur:
            cur = cur[segment]
        elif isinstance(cur, list):
            try:
                cur = cur[int(segment)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


#: `{{ steps.foo.bar }}` Jinja-ish interpolation inside string values.
#: The LLM gravitates toward this syntax for prompt-template-style refs,
#: so the interpreter resolves both this form and `{"$ref": "path"}`.
#: Dict-form `$ref` preserves the resolved value's type; `{{...}}` always
#: stringifies (json-encodes dicts/lists so they're readable in prompts).
_TEMPLATE_REF = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return _json.dumps(value, ensure_ascii=False)
        except TypeError:
            return str(value)
    return str(value)


def _resolve(value: Any, context: dict[str, Any]) -> Any:
    """Recursively resolve $ref markers and `{{path}}` strings against context."""
    if isinstance(value, dict):
        if set(value.keys()) == {"$ref"} and isinstance(value["$ref"], str):
            return _walk_path(context, value["$ref"])
        return {k: _resolve(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, context) for v in value]
    if isinstance(value, str) and _TEMPLATE_REF.search(value):
        return _TEMPLATE_REF.sub(
            lambda m: _stringify(_walk_path(context, m.group(1))),
            value,
        )
    return value


def _evaluate_condition(
    cond: EqualityCondition, context: dict[str, Any]
) -> bool:
    left = _resolve(cond.left, context)
    right = _resolve(cond.right, context)
    if cond.op == "eq":
        return left == right
    if cond.op == "neq":
        return left != right
    return False


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


async def run_workflow(
    definition: WorkflowDefinition,
    payload: dict[str, Any],
    creds: Credentials,
) -> WorkflowRunResult:
    """Execute `definition` against `payload`, returning a structured result."""
    context: dict[str, Any] = {"request": payload, "steps": {}}
    trace: list[StepTrace] = []
    final_output: dict[str, Any] | None = None

    for step in definition.steps:
        started = datetime.now(UTC)
        # Condition check
        if step.condition is not None and not _evaluate_condition(
            step.condition, context
        ):
            trace.append(
                StepTrace(
                    id=step.id,
                    tool=step.tool,
                    action=step.action,
                    skipped=True,
                    started_at=started,
                    ended_at=datetime.now(UTC),
                    params_resolved={},
                )
            )
            continue

        resolved = _resolve(step.params, context)
        if not isinstance(resolved, dict):
            resolved = {"value": resolved}

        adapter = get_adapter(step.tool)
        if adapter is None:
            err = f"no adapter registered for tool {step.tool!r}"
            trace.append(
                StepTrace(
                    id=step.id,
                    tool=step.tool,
                    action=step.action,
                    skipped=False,
                    started_at=started,
                    ended_at=datetime.now(UTC),
                    params_resolved=resolved,
                    error=err,
                )
            )
            return WorkflowRunResult(ok=False, trace=trace, error=err)

        try:
            output = await adapter(step.action, resolved, creds)
        except Exception as exc:  # noqa: BLE001
            logger.exception("adapter failed: tool=%s action=%s", step.tool, step.action)
            err = f"{type(exc).__name__}: {exc}"
            trace.append(
                StepTrace(
                    id=step.id,
                    tool=step.tool,
                    action=step.action,
                    skipped=False,
                    started_at=started,
                    ended_at=datetime.now(UTC),
                    params_resolved=resolved,
                    error=err,
                )
            )
            return WorkflowRunResult(ok=False, trace=trace, error=err)

        slot = step.output_key or step.id
        context["steps"][slot] = output

        trace.append(
            StepTrace(
                id=step.id,
                tool=step.tool,
                action=step.action,
                skipped=False,
                started_at=started,
                ended_at=datetime.now(UTC),
                params_resolved=resolved,
                output=output,
            )
        )

        if step.tool == "return":
            final_output = output

    if final_output is None:
        # No explicit return — surface a summary of every recorded step.
        final_output = {"steps": context["steps"]}

    return WorkflowRunResult(ok=True, output=final_output, trace=trace)
