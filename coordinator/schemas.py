"""Pydantic schemas shared by the Coordinator and Enablement Agents.

Every structured agent output crossing a process boundary is one of these models.
The Coordinator's final result is an EnablementPlan; the Support Enablement
Agent (Phase 4-5) returns the same; Phase 5 adds OrchestratorRunResult to
record the on-disk artifact a generate_orchestrator call produced.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PlanMetadata(BaseModel):
    """Provenance for an EnablementPlan."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(description="UTC timestamp when the plan was finalized.")
    agent_name: str = Field(description="Name of the Enablement Agent that produced the plan.")
    agent_version: str = Field(description="Agent version string from the agent definition.")
    stack_file_hash: str = Field(description="sha256 of the stack file at generation time.")
    coordinator_session_id: str = Field(description="Session id of the Coordinator run.")


class CapabilityFinding(BaseModel):
    """One assessment of how a functional capability is (or isn't) covered."""

    model_config = ConfigDict(extra="forbid")

    capability: str = Field(description="Name of the functional capability.")
    status: Literal["covered", "partial", "gap", "redundant"]
    tools_involved: list[str] = Field(
        description=(
            "Canonical tool names involved in covering (or failing to cover) "
            "the capability."
        ),
    )
    notes: str | None = None


class Recommendation(BaseModel):
    """One concrete action the Enablement Agent recommends."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable id within the plan (e.g. R-001).")
    kind: Literal["use_native_ai", "augment_with_custom_ai", "consolidate", "orchestrate"]
    description: str
    tools_affected: list[str]
    effort: Literal["small", "medium", "large"]
    notes: str | None = None


class OrchestratorPRPlan(BaseModel):
    """Metadata about the orchestrator that *will be* generated in Phase 5.

    This object is part of the EnablementPlan. The on-disk artifact produced
    by Phase 5 is described by OrchestratorRunResult (added in Phase 5.3).
    """

    model_config = ConfigDict(extra="forbid")

    branch: str = Field(description="Target branch name for the generated PR.")
    files_to_create: list[str]
    mcp_servers_used: list[str] = Field(
        description="Tool names whose existing MCP servers the orchestrator will reference.",
    )
    mcp_servers_to_generate: list[str] = Field(
        description="Tool names for which the orchestrator must generate a stub MCP server.",
    )
    ai_configs_to_create: list[str]
    env_vars_required: list[str]


class EnablementPlan(BaseModel):
    """The structured deliverable of a single Coordinator run."""

    model_config = ConfigDict(extra="forbid")

    department: str
    summary: str = Field(
        description="One-paragraph executive summary suitable for a PR description."
    )
    capability_coverage: list[CapabilityFinding]
    recommendations: list[Recommendation]
    orchestrator_pr_plan: OrchestratorPRPlan | None = None
    metadata: PlanMetadata


class OrchestratorRunResult(BaseModel):
    """Result of an orchestrator generation — what actually got written to disk.

    Produced by Phase 5's generate_orchestrator(plan) call. Distinct from
    OrchestratorPRPlan (which is the *intent*, embedded inside an
    EnablementPlan). This model records the artifact that was produced.
    """

    model_config = ConfigDict(extra="forbid")

    department: str
    files_created: list[str]
    mcp_servers_generated: list[str]
    ai_configs_manifest_path: str
    env_vars_required: list[str]
    plan_reference: PlanMetadata


class CoordinatorRunResult(BaseModel):
    """Top-level return value of run_coordinator()."""

    model_config = ConfigDict(extra="forbid")

    plan: EnablementPlan
    coordinator_session_id: str
