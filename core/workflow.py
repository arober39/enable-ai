"""Workflow DAG schema — the "plan as data, not code" replacement for 1.4.

A `WorkflowDefinition` is the per-user, per-role artifact produced by
the new build pipeline. It is JSON-serializable, peer-reviewable in
shape (Pydantic validates), and executed by a fixed interpreter
(`enablement_agents.workflow_interpreter`) that nobody but the platform
team owns. No LLM-authored Python ever runs in this path.

Design decisions for v1 (intentionally minimal):

- Linear execution. Steps run in order. No branches, no loops.
- A step may carry a `condition` — a tiny equality check against the
  context — that lets the runtime skip it. Anything more complex than
  "if X == Y" must wait for v2.
- Step params support `{"$ref": "<dotted.path>"}` markers. Everything
  else is a literal. The interpreter resolves refs before dispatch.
- Tool dispatch is by `(tool_name, action)` against a small adapter
  registry. Adapters are reviewed Python, not LLM-authored.
- Three "tools" are special:
    - `llm` — Claude call (uses ANTHROPIC_API_KEY from creds)
    - `return` — emits its `params` as the workflow's final output
    - `set` — copies values around the context, no I/O

This shape is intentionally smaller than what Zapier-class products
support — that's by design. We grow it deliberately, not by accretion.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

#: Special tool names that don't map to a SaaS catalog entry.
LLM_TOOL = "llm"
RETURN_TOOL = "return"
SET_TOOL = "set"
SPECIAL_TOOLS = {LLM_TOOL, RETURN_TOOL, SET_TOOL}


class EqualityCondition(BaseModel):
    """Tiny equality check: `{"eq": [<ref or literal>, <ref or literal>]}`."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["eq", "neq"]
    left: Any
    right: Any


class WorkflowStep(BaseModel):
    """One step in a workflow."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    tool: str = Field(min_length=1, description="canonical tool name or special: llm/return/set")
    action: str = Field(min_length=1, description="adapter-specific operation name")
    params: dict[str, Any] = Field(default_factory=dict)
    condition: EqualityCondition | None = None
    output_key: str | None = Field(
        default=None,
        description="Name to store output under in workflow context "
        "(default: step id).",
    )
    description: str | None = None


class WorkflowDefinition(BaseModel):
    """The persisted workflow — generated once, run many times."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    role_id: str = Field(min_length=1)
    recommendation_id: str = Field(min_length=1)
    tools_used: list[str] = Field(
        default_factory=list,
        description="canonical tool names referenced in steps; excludes special tools",
    )
    env_vars_required: list[str] = Field(
        default_factory=list,
        description="Credential keys the workflow's steps will need",
    )
    request_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="Shape of the request payload (informational; not strictly enforced in v1)",
    )
    response_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="Shape of the workflow's final output",
    )
    sample_request: dict[str, Any] = Field(
        default_factory=dict,
        description="A concrete example request the UI uses to pre-fill the "
        "'Send a request' textarea. Should match `request_schema`. Empty "
        "on legacy workflows generated before this field was added.",
    )
    steps: list[WorkflowStep] = Field(min_length=1)


def referenced_tools(definition: WorkflowDefinition) -> list[str]:
    """Return non-special tool names referenced by any step (deduped, sorted)."""
    found: set[str] = set()
    for step in definition.steps:
        if step.tool not in SPECIAL_TOOLS:
            found.add(step.tool)
    return sorted(found)
