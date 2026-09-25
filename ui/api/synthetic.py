"""Synthetic EnablementPlan builder for demo-mode UI requests.

When the UI is running without `ANTHROPIC_API_KEY` (or with
`ENABLE_AI_DEMO_MODE=true`), we don't want to charge the user for live LLM
calls just to render the UI. This module builds a plausible plan
deterministically from the catalog data alone — same Pydantic shape as
what a live run would produce, but without invoking Claude.

It is NOT a substitute for the real agent. Findings and recommendations
are built from the selected tools' catalog capabilities (categories,
notes, native features), with the role as who the workflow is for. The
synthetic plan is labeled in its summary so users can tell.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from coordinator.schemas import (
    EnablementPlan,
    OrchestratorPRPlan,
    PlanMetadata,
)
from core.credentials import Credentials
from core.identity import UserContext
from core.plan_grounding import (
    grounded_findings,
    grounded_recommendations,
    grounded_summary,
)
from core.roles import Role
from core.tool_catalog import ToolCapability, load_tool


def build_synthetic_plan(
    tools: list[str],
    role: Role,
    user: UserContext,
    creds: Credentials | None = None,
) -> EnablementPlan:
    """Build a deterministic synthetic EnablementPlan from the catalog.

    Reads each tool through `core.tool_catalog.load_tool` so researched
    tools and seed tools are treated identically. The synthetic plan
    stamps `role.department` / `role.agent_name`. Findings and
    recommendations follow the selected tools' catalog domains.
    """
    loaded: list[ToolCapability] = []
    missing: list[str] = []
    for tool_name in tools:
        cap = load_tool(user, tool_name)
        if cap is None:
            missing.append(tool_name)
            continue
        loaded.append(cap)

    findings = grounded_findings(loaded, missing=missing, creds=creds)
    recs = grounded_recommendations(loaded, role)
    summary = grounded_summary(loaded, role, synthetic=True)
    if missing:
        summary = (
            f"{summary} Missing catalog entries: {', '.join(missing)}."
        )
    mcp_used = [cap.canonical_name for cap in loaded if cap.mcp_server.available]
    mcp_to_generate = [
        cap.canonical_name for cap in loaded if not cap.mcp_server.available
    ]

    return EnablementPlan(
        department=role.department,
        summary=summary,
        capability_coverage=findings,
        recommendations=recs,
        orchestrator_pr_plan=OrchestratorPRPlan(
            branch=f"enable-ai/{role.id}",
            files_to_create=[
                "orchestrator.py",
                "agent_definition.py",
                "prompts/v1_baseline.md",
                "prompts/v2_detailed_responses.md",
                "judges/factual_accuracy.md",
                ".mcp.json",
                "observability.py",
                ".env.example",
                "Makefile",
                "README.md",
                "ai_configs.manifest.yaml",
            ],
            mcp_servers_used=mcp_used,
            mcp_servers_to_generate=mcp_to_generate,
            ai_configs_to_create=[f"{role.id}-orchestrator-config"],
            env_vars_required=["ANTHROPIC_API_KEY", "LAUNCHDARKLY_SDK_KEY"],
        ),
        metadata=PlanMetadata(
            generated_at=datetime.now(UTC),
            agent_name=f"{role.agent_name}_synthetic",
            agent_version="0.1.0",
            stack_file_hash=hashlib.sha256(
                ",".join(sorted(tools)).encode("utf-8")
            ).hexdigest(),
            coordinator_session_id="ui-synthetic",
        ),
    )
