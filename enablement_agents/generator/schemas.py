"""Pydantic shapes for the 4-stage generator pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from coordinator.schemas import Recommendation
from core.tool_catalog import ToolCapability

StageName = Literal["research", "plan", "generate", "verify"]


class ToolResearch(BaseModel):
    """Stage 1 output for a single tool — what the orchestrator needs from it."""

    model_config = ConfigDict(extra="forbid")

    canonical_name: str
    api_endpoints_needed: list[str] = Field(
        default_factory=list,
        description="REST endpoints or SDK methods the orchestrator will call",
    )
    mcp_tools_used: list[str] = Field(
        default_factory=list,
        description="MCP server tools the orchestrator will invoke",
    )
    env_vars_consumed: list[str] = Field(
        default_factory=list,
        description="Credential names from the user's vault this tool needs",
    )
    notes: str | None = None


class GeneratorContext(BaseModel):
    """All inputs the pipeline needs to produce an orchestrator."""

    model_config = ConfigDict(extra="forbid")

    role_id: str
    role_display_name: str
    recommendation: Recommendation
    tool_capabilities: list[ToolCapability]
    available_credentials: list[str] = Field(
        description="Credential keys the user has stored. The generator should "
        "only reference these names in the generated code."
    )


class CodeFilePlan(BaseModel):
    """One planned source file — name + purpose + key exports."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        description="Relative path under orchestrator dir, e.g. 'orchestrator.py'",
    )
    purpose: str
    key_exports: list[str] = Field(
        description="Function or class names this file exports",
    )


class CodePlan(BaseModel):
    """Stage 2 output — the structure of the orchestrator code."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(
        description="One-paragraph plan summary the user will see in the UI",
    )
    files: list[CodeFilePlan]
    env_vars_required: list[str] = Field(
        description="Credential names the generated code will read",
    )
    request_input_schema: dict = Field(
        description="JSON-schema-ish object describing what handle_request expects",
    )
    response_output_schema: dict = Field(
        description="JSON-schema-ish object describing what handle_request returns",
    )


class GeneratedCode(BaseModel):
    """Stage 3 output — the actual source for orchestrator.py."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(
        description="Complete Python source for orchestrator.py. Must define "
        "an async function `handle_request(payload: dict) -> dict`.",
    )
    explanation: str = Field(
        description="Short paragraph the UI shows next to the build result",
    )


class StageResult(BaseModel):
    """Per-stage trace for the UI's progress display."""

    model_config = ConfigDict(extra="forbid")

    name: StageName
    ok: bool
    started_at: datetime
    ended_at: datetime
    detail: str | None = None
    output_preview: str | None = None


class GeneratorRunResult(BaseModel):
    """What the pipeline returns to the API layer."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    output_path: str
    stages: list[StageResult]
    plan: CodePlan | None = None
    explanation: str | None = None
    env_vars_required: list[str] = Field(default_factory=list)
