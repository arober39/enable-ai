"""Deterministic install for demo mode.

Live build pipelines call a model. Demo mode does not. This module
installs the same artifact kinds from the catalog and the reviewed
adapter registry: a WorkflowDefinition the interpreter can run, a
native-AI setup guide, or a consolidation checklist. No model-authored
code is written.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.workflow import WorkflowDefinition, WorkflowStep
from enablement_agents.generator.artifacts import (
    BuildResult,
    ConsolidationPlanArtifact,
    MigrationItem,
    NativeAISetupArtifact,
    SetupStep,
)
from enablement_agents.generator.schemas import GeneratorContext, StageResult
from enablement_agents.generator.workflow_pipeline import unknown_adapter_actions
from enablement_agents.tool_adapters import builtin as _builtin  # noqa: F401
from enablement_agents.tool_adapters.registry import describe_actions

#: Credential name a real call would need. Demo runs stay stub without it.
_CREDENTIAL_FOR_TOOL: dict[str, str] = {
    "intercom": "INTERCOM_API_TOKEN",
    "zendesk": "ZENDESK_API_TOKEN",
    "slack": "SLACK_BOT_TOKEN",
    "hubspot": "HUBSPOT_API_KEY",
    "gainsight": "GAINSIGHT_API_KEY",
    "gong": "GONG_API_KEY",
    "vitally": "VITALLY_API_KEY",
    "github": "GITHUB_TOKEN",
    "klaviyo": "KLAVIYO_API_KEY",
    "marketo": "MARKETO_API_KEY",
    "discord": "DISCORD_BOT_TOKEN",
    "discourse": "DISCOURSE_API_KEY",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _stage(detail: str, preview: str) -> StageResult:
    now = _now()
    return StageResult(
        name="plan",
        ok=True,
        started_at=now,
        ended_at=now,
        detail=detail,
        output_preview=preview,
    )


def _demo_params() -> dict[str, object]:
    """Literals the reviewed adapters accept. Extra keys are ignored."""
    return {
        "query": "demo",
        "email": "demo@serenia.example",
        "account_id": "acct_demo",
        "id": "demo",
        "channel": "general",
        "text": "demo inquiry",
        "owner": "serenia",
        "repo": "enable-ai",
        "number": "1",
        "conversation_id": "demo",
        "body": "demo inquiry",
    }


def _installable_tools(ctx: GeneratorContext) -> list[tuple[str, str]]:
    """(tool, action) pairs drawn only from the reviewed action catalog."""
    catalog = describe_actions()
    requested = list(ctx.recommendation.tools_affected) or [
        cap.canonical_name for cap in ctx.tool_capabilities
    ]
    pairs: list[tuple[str, str]] = []
    for name in requested:
        actions = catalog.get(name)
        if not actions:
            continue
        action = sorted(actions)[0]
        pairs.append((name, action))
    return pairs


def install_demo_workflow(ctx: GeneratorContext) -> BuildResult:
    """Install a WorkflowDefinition that only calls reviewed adapters."""
    pairs = _installable_tools(ctx)
    if not pairs:
        now = _now()
        return BuildResult(
            ok=False,
            stages=[
                StageResult(
                    name="plan",
                    ok=False,
                    started_at=now,
                    ended_at=now,
                    detail="no reviewed adapter for the recommendation's tools",
                )
            ],
            artifact_kind="none",
            explanation=(
                "[DEMO] Nothing was installed. The recommendation names tools "
                "with no reviewed adapter."
            ),
        )

    steps: list[WorkflowStep] = []
    modes: dict[str, dict[str, str]] = {}
    for tool, action in pairs:
        step_id = f"step_{tool}"
        steps.append(
            WorkflowStep(
                id=step_id,
                tool=tool,
                action=action,
                params=_demo_params(),
                description=f"Reviewed {tool}.{action} call. Stub unless credentials are set.",
            )
        )
        modes[tool] = {"$ref": f"steps.{step_id}.mode"}
    steps.append(
        WorkflowStep(
            id="done",
            tool="return",
            action="value",
            params={"modes": modes, "recommendation_id": ctx.recommendation.id},
        )
    )
    definition = WorkflowDefinition(
        name=f"{ctx.role_id}-{ctx.recommendation.id}",
        description=(
            f"[DEMO] {ctx.recommendation.description} "
            "Installed from the reviewed adapter catalog, not from model-authored code."
        ),
        role_id=ctx.role_id,
        recommendation_id=ctx.recommendation.id,
        tools_used=[tool for tool, _action in pairs],
        env_vars_required=sorted(
            {_CREDENTIAL_FOR_TOOL[tool] for tool, _action in pairs if tool in _CREDENTIAL_FOR_TOOL}
        ),
        sample_request={"inquiry": f"Demo {ctx.role_display_name} request"},
        steps=steps,
    )
    unknown = unknown_adapter_actions(definition)
    if unknown:
        now = _now()
        return BuildResult(
            ok=False,
            stages=[
                StageResult(
                    name="plan",
                    ok=False,
                    started_at=now,
                    ended_at=now,
                    detail=f"refused unreviewed actions: {unknown}",
                )
            ],
            artifact_kind="none",
        )
    preview = ", ".join(f"{tool}.{action}" for tool, action in pairs)
    return BuildResult(
        ok=True,
        stages=[_stage("installed reviewed workflow", preview)],
        artifact_kind="workflow",
        workflow=definition,
        explanation=(
            "[DEMO] Installed a reviewed workflow. Each tool call stays a stub "
            "until that tool's credential is in the vault. No model-authored code ran."
        ),
        env_vars_required=list(definition.env_vars_required),
    )


def install_demo_native_setup(ctx: GeneratorContext) -> BuildResult:
    """A setup guide for the vendor feature already in the catalog. No runtime."""
    tool = (
        ctx.recommendation.tools_affected[0]
        if ctx.recommendation.tools_affected
        else ctx.tool_capabilities[0].canonical_name
    )
    feature = "native AI"
    for cap in ctx.tool_capabilities:
        if cap.canonical_name == tool and cap.native_ai_features:
            feature = cap.native_ai_features[0].name
            break
    artifact = NativeAISetupArtifact(
        name=f"Enable {feature}",
        summary=(
            f"[DEMO] Turn on {feature} inside {tool}. This guide does not "
            "change the vendor account."
        ),
        primary_tool=tool,
        feature_name=feature,
        setup_steps=[
            SetupStep(
                order=1,
                title=f"Open {tool}",
                detail=f"Sign in to {tool} with the account Serenia already pays for.",
            ),
            SetupStep(
                order=2,
                title=f"Enable {feature}",
                detail=(
                    f"Turn on {feature} in the product's AI settings. "
                    "Enable AI does not call the vendor from this step."
                ),
            ),
        ],
        success_criteria=[
            f"{feature} is visible to a person using {tool}.",
            "No custom workflow was installed for this recommendation.",
        ],
        notes="Demo guide assembled from the tool catalog, not from a model.",
    )
    return BuildResult(
        ok=True,
        stages=[_stage("wrote native-AI setup guide", feature)],
        artifact_kind="native_ai_setup",
        native_ai_setup=artifact,
        explanation=artifact.summary,
    )


def install_demo_consolidation(ctx: GeneratorContext) -> BuildResult:
    """A migration checklist. No runtime, and no claim that data was moved."""
    names = list(ctx.recommendation.tools_affected) or [
        cap.canonical_name for cap in ctx.tool_capabilities
    ]
    if len(names) < 2:
        now = _now()
        return BuildResult(
            ok=False,
            stages=[
                StageResult(
                    name="plan",
                    ok=False,
                    started_at=now,
                    ended_at=now,
                    detail="consolidate needs two tools",
                )
            ],
            artifact_kind="none",
            explanation="[DEMO] Consolidation needs a source tool and a target tool.",
        )
    source, target = names[0], names[1]
    artifact = ConsolidationPlanArtifact(
        name=f"Consolidate {source} onto {target}",
        summary=(
            f"[DEMO] Plan to keep {target} and retire the overlapping use of {source}. "
            "Nothing has been migrated."
        ),
        source_tool=source,
        target_tool=target,
        items_to_migrate=[
            MigrationItem(
                name="overlapping records",
                source=source,
                target=target,
                method=(
                    f"Export from {source} and import into {target} using each vendor's own tools."
                ),
                notes="Demo checklist. Enable AI did not move data.",
            )
        ],
        pre_migration_checklist=[
            f"Confirm {target} already covers the capability {source} duplicates."
        ],
        post_migration_checklist=[f"Stop creating new records in {source}."],
        risks=["Records can diverge if both tools stay in daily use during the move."],
    )
    return BuildResult(
        ok=True,
        stages=[_stage("wrote consolidation checklist", f"{source} -> {target}")],
        artifact_kind="consolidation_plan",
        consolidation_plan=artifact,
        explanation=artifact.summary,
    )
