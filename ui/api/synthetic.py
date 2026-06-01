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
from pathlib import Path
from typing import Any, Literal

import yaml

from coordinator.schemas import (
    CapabilityFinding,
    EnablementPlan,
    OrchestratorPRPlan,
    PlanMetadata,
    Recommendation,
)

_Status = Literal["covered", "partial", "gap", "redundant"]

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]


def _load_tool(name: str) -> dict[str, Any] | None:
    path = _REPO_ROOT / "tools" / f"{name}.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def _load_mcp(name: str) -> dict[str, Any] | None:
    path = _REPO_ROOT / "mcp_registry" / f"{name}.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def _classify_tool(tool_data: dict[str, Any]) -> tuple[str, _Status]:
    """Pick a capability area + status heuristic for a single tool.

    Returns (capability_name, status). Drives the synthetic
    CapabilityFinding list. Loosely mirrors the assessment a real
    Support Enablement Agent would produce.
    """
    cats = tool_data.get("categories", []) or []
    cats_text = " ".join(cats).lower()
    if "ticketing" in cats_text:
        return ("first_response_drafting", "covered")
    if "knowledge_base" in cats_text:
        return ("faq_retrieval", "covered")
    if "internal_messaging" in cats_text or "team_collaboration" in cats_text:
        return ("escalation_routing", "partial")
    if "crm" in cats_text:
        return ("knowledge_base_search", "partial")
    return ("intent_classification", "partial")


def build_synthetic_plan(tools: list[str]) -> EnablementPlan:
    """Build a deterministic synthetic EnablementPlan from the catalog."""
    findings: list[CapabilityFinding] = []
    recs: list[Recommendation] = []
    mcp_used: list[str] = []
    mcp_to_generate: list[str] = []

    for tool_name in tools:
        tool_data = _load_tool(tool_name)
        mcp_data = _load_mcp(tool_name)
        if tool_data is None:
            findings.append(
                CapabilityFinding(
                    capability="catalog_lookup",
                    status="gap",
                    tools_involved=[tool_name],
                    notes=f"No catalog entry for '{tool_name}' — record as gap.",
                )
            )
            continue
        cap, status = _classify_tool(tool_data)
        findings.append(
            CapabilityFinding(
                capability=cap,
                status=status,
                tools_involved=[tool_name],
                notes=(tool_data.get("notes") or None),
            )
        )
        if mcp_data and mcp_data.get("mcp_server", {}).get("available"):
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
                    f"Compose {', '.join(mcp_used)} into a unified support "
                    f"surface via their existing MCP servers."
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
                    "read the customer data it needs."
                ),
                tools_affected=list(mcp_to_generate),
                effort="medium",
                notes="No vendor-maintained MCP server at build time.",
            )
        )
        rec_id += 1
    # One use_native_ai recommendation if any tool has native AI features.
    for tool_name in tools:
        tool_data = _load_tool(tool_name)
        if tool_data and tool_data.get("native_ai_features"):
            features = tool_data["native_ai_features"]
            if features:
                recs.append(
                    Recommendation(
                        id=f"R-{rec_id:03d}",
                        kind="use_native_ai",
                        description=(
                            f"Use {tool_data.get('vendor', tool_name)}'s "
                            f"{features[0].get('name')} as-is for the "
                            "capabilities it already covers well."
                        ),
                        tools_affected=[tool_name],
                        effort="small",
                        notes=None,
                    )
                )
                rec_id += 1
                break

    summary = (
        f"[DEMO/SYNTHETIC] Catalog-driven enablement plan over "
        f"{len(tools)} tools ({', '.join(tools)}). This plan is built "
        "deterministically from the tool catalog — set "
        "ANTHROPIC_API_KEY and ENABLE_AI_DEMO_MODE=false to invoke the "
        "real Support Enablement Agent for a reasoning-driven plan."
    )

    return EnablementPlan(
        department="support",
        summary=summary,
        capability_coverage=findings,
        recommendations=recs,
        orchestrator_pr_plan=OrchestratorPRPlan(
            branch="enable-ai/support",
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
            ai_configs_to_create=["support-orchestrator-config"],
            env_vars_required=["ANTHROPIC_API_KEY", "LAUNCHDARKLY_SDK_KEY"],
        ),
        metadata=PlanMetadata(
            generated_at=datetime.now(UTC),
            agent_name="support_enablement_agent_synthetic",
            agent_version="0.1.0",
            stack_file_hash=hashlib.sha256(
                ",".join(sorted(tools)).encode("utf-8")
            ).hexdigest(),
            coordinator_session_id="ui-synthetic",
        ),
    )
