"""Synthetic EnablementPlan builder for demo-mode UI requests.

When the UI is running without `ANTHROPIC_API_KEY` (or with
`ENABLE_AI_DEMO_MODE=true`), we don't want to charge the user for live LLM
calls just to render the UI. This module builds a plausible plan
deterministically from the catalog data alone — same Pydantic shape as
what a live run would produce, but without invoking Claude.

It is NOT a substitute for the real agent. The recommendations are
catalog-driven heuristics, not reasoning. The synthetic plan is labeled
in its summary so users can tell.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal

from coordinator.schemas import (
    CapabilityFinding,
    EnablementPlan,
    OrchestratorPRPlan,
    PlanMetadata,
    Recommendation,
)
from core.identity import UserContext
from core.roles import Role
from core.tool_catalog import ToolCapability, load_tool

_Status = Literal["covered", "partial", "gap", "redundant"]


def _classify_tool(cap: ToolCapability) -> tuple[str, _Status]:
    """Pick a capability area + status heuristic for a single tool.

    Returns (capability_name, status). Drives the synthetic
    CapabilityFinding list. Loosely mirrors the assessment a real
    Enablement Agent would produce — heuristic, not reasoning.
    """
    cats_text = " ".join(cap.categories).lower()
    if "ticketing" in cats_text:
        return ("first_response_drafting", "covered")
    if "knowledge_base" in cats_text:
        return ("faq_retrieval", "covered")
    if "internal_messaging" in cats_text or "team_collaboration" in cats_text:
        return ("escalation_routing", "partial")
    if "crm" in cats_text:
        return ("knowledge_base_search", "partial")
    return ("intent_classification", "partial")


def build_synthetic_plan(
    tools: list[str], role: Role, user: UserContext
) -> EnablementPlan:
    """Build a deterministic synthetic EnablementPlan from the catalog.

    Reads each tool through `core.tool_catalog.load_tool` so researched
    tools and seed tools are treated identically. The synthetic plan
    stamps `role.department` / `role.agent_name`; capability findings
    remain catalog-driven heuristics.
    """
    findings: list[CapabilityFinding] = []
    recs: list[Recommendation] = []
    mcp_used: list[str] = []
    mcp_to_generate: list[str] = []
    loaded: list[ToolCapability] = []

    for tool_name in tools:
        cap = load_tool(user, tool_name)
        if cap is None:
            findings.append(
                CapabilityFinding(
                    capability="catalog_lookup",
                    status="gap",
                    tools_involved=[tool_name],
                    notes=(
                        f"No catalog entry or cached research for "
                        f"'{tool_name}' — record as gap."
                    ),
                )
            )
            continue
        loaded.append(cap)
        capability, status = _classify_tool(cap)
        findings.append(
            CapabilityFinding(
                capability=capability,
                status=status,
                tools_involved=[tool_name],
                notes=cap.notes,
            )
        )
        if cap.mcp_server.available:
            mcp_used.append(tool_name)
        else:
            mcp_to_generate.append(tool_name)

    # Recommendations heuristics
    rec_id = 1
    if mcp_used:
        recs.append(
            Recommendation(
                id=f"R-{rec_id:03d}",
                kind="orchestrate",
                description=(
                    f"Compose {', '.join(mcp_used)} into a unified "
                    f"{role.display_name.lower()} surface via their existing "
                    "MCP servers."
                ),
                tools_affected=list(mcp_used),
                effort="medium",
                notes=None,
            )
        )
        rec_id += 1
    if mcp_to_generate:
        recs.append(
            Recommendation(
                id=f"R-{rec_id:03d}",
                kind="augment_with_custom_ai",
                description=(
                    f"Generate a minimal MCP server stub for "
                    f"{', '.join(mcp_to_generate)} so the orchestrator can "
                    "read the data it needs."
                ),
                tools_affected=list(mcp_to_generate),
                effort="medium",
                notes="No vendor-maintained MCP server at build time.",
            )
        )
        rec_id += 1
    # One use_native_ai recommendation if any tool has native AI features.
    for cap in loaded:
        if cap.native_ai_features:
            feature = cap.native_ai_features[0]
            recs.append(
                Recommendation(
                    id=f"R-{rec_id:03d}",
                    kind="use_native_ai",
                    description=(
                        f"Use {cap.vendor}'s {feature.name} as-is for the "
                        "capabilities it already covers well."
                    ),
                    tools_affected=[cap.canonical_name],
                    effort="small",
                    notes=None,
                )
            )
            rec_id += 1
            break

    summary = (
        f"[DEMO/SYNTHETIC] Catalog-driven {role.display_name.lower()} "
        f"enablement plan over {len(tools)} tools ({', '.join(tools)}). "
        "This plan is built deterministically from the tool catalog — set "
        "ANTHROPIC_API_KEY and ENABLE_AI_DEMO_MODE=false to invoke the "
        f"real {role.display_name} Enablement Agent for a reasoning-driven plan."
    )

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
