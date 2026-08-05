"""Build artifacts — what the generator produces for each recommendation kind.

The build pipeline dispatches on `Recommendation.kind` and produces one of
three artifact types:

  - use_native_ai            → `NativeAISetupArtifact`   (configuration steps, no runtime)
  - consolidate              → `ConsolidationPlanArtifact` (migration checklist, no runtime)
  - augment_with_custom_ai   → `WorkflowDefinition`      (runtime workflow)
  - orchestrate              → `WorkflowDefinition`      (runtime workflow)

`BuildResult` is the envelope returned by the build endpoint. The
`artifact_kind` discriminator tells the UI which artifact field to read
and render. The Send-an-Inquiry surface only activates when
`artifact_kind == "workflow"` — the other kinds are deliverables you
act on, not things you call at runtime.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.workflow import WorkflowDefinition

from .schemas import StageResult


# ---------------------------------------------------------------------------
# `use_native_ai` artifact: configuration steps for enabling a vendor's AI
# ---------------------------------------------------------------------------


class SetupStep(BaseModel):
    """One step in a vendor-feature setup guide."""

    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1)
    title: str = Field(min_length=1)
    detail: str = Field(
        min_length=1,
        description="What to click / where to find it / what to enter",
    )
    optional: bool = False


class NativeAISetupArtifact(BaseModel):
    """A `use_native_ai` recommendation's deliverable.

    The recommendation says "turn on the vendor's AI feature — don't
    build anything custom." This artifact is the step-by-step guide for
    doing that, plus what to connect and how to verify it's working.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["native_ai_setup"] = "native_ai_setup"
    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    primary_tool: str = Field(
        description="canonical tool name whose native feature is being enabled",
    )
    feature_name: str = Field(
        description="The vendor's name for the feature (e.g., 'Fin', 'Intelligent triage')",
    )
    setup_steps: list[SetupStep] = Field(min_length=1)
    connected_sources: list[str] = Field(
        default_factory=list,
        description="Other tools/sources to connect (e.g., 'Zendesk Help Center')",
    )
    success_criteria: list[str] = Field(
        min_length=1,
        description="Observable signals that the feature is working as intended",
    )
    notes: str | None = None


# ---------------------------------------------------------------------------
# `consolidate` artifact: migration plan for unifying duplicated capability
# ---------------------------------------------------------------------------


class MigrationItem(BaseModel):
    """One thing being moved from one tool to another."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="What's being migrated (e.g., 'FAQ articles')")
    source: str = Field(min_length=1, description="Current location")
    target: str = Field(min_length=1, description="Destination")
    method: str = Field(
        min_length=1,
        description="How to move it (e.g., 'export CSV from X, import to Y')",
    )
    notes: str | None = None


class ConsolidationPlanArtifact(BaseModel):
    """A `consolidate` recommendation's deliverable.

    The recommendation says "two tools redundantly cover the same
    capability — unify on one of them." This artifact is the
    structured migration plan: what to move, how, what to check before
    and after, and what could go wrong.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["consolidation_plan"] = "consolidation_plan"
    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_tool: str = Field(description="canonical tool name being consolidated away from")
    target_tool: str = Field(description="canonical tool name being consolidated onto")
    items_to_migrate: list[MigrationItem] = Field(min_length=1)
    pre_migration_checklist: list[str] = Field(default_factory=list)
    post_migration_checklist: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    notes: str | None = None


# ---------------------------------------------------------------------------
# Build envelope
# ---------------------------------------------------------------------------


ArtifactKind = Literal[
    "workflow",
    "native_ai_setup",
    "consolidation_plan",
    "none",  # used on pipeline failure before any artifact is produced
]


class BuildResult(BaseModel):
    """What the build endpoint returns to the UI.

    Exactly one of `workflow`, `native_ai_setup`, `consolidation_plan` is
    populated on success — the `artifact_kind` field is the discriminator
    telling the UI which to render. On failure all three are None and
    `artifact_kind` is `"none"`.
    """

    model_config = ConfigDict(extra="forbid")

    ok: bool
    stages: list[StageResult] = Field(default_factory=list)
    artifact_kind: ArtifactKind
    workflow: WorkflowDefinition | None = None
    native_ai_setup: NativeAISetupArtifact | None = None
    consolidation_plan: ConsolidationPlanArtifact | None = None
    explanation: str | None = None
    env_vars_required: list[str] = Field(default_factory=list)
