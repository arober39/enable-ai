"""FastAPI backend for the Enable AI UI.

Three endpoints:
  - GET  /api/tools                  — catalog summary of the 4 UI tools
  - POST /api/enablement             — run Support agent → EnablementPlan
  - POST /api/generate-orchestrator  — write the orchestrator tree from a plan

Demo mode (ENABLE_AI_DEMO_MODE=true or ANTHROPIC_API_KEY unset) returns a
synthetic catalog-driven plan. Live mode invokes the real
`SupportEnablementAgent.produce_plan` against a temporary stack file built
from the user's selection.

Run:
    .venv/bin/uvicorn ui.api.server:app --reload --port 8000

Set ENABLE_AI_UI_DEBUG=true to enable verbose SDK logging while diagnosing
live-mode failures. This prints every message the SDK receives from the
underlying claude CLI subprocess.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

# Verbose claude-agent-sdk logging when debugging the live path. Off by
# default — flip on with ENABLE_AI_UI_DEBUG=true in .env.
if os.environ.get("ENABLE_AI_UI_DEBUG", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}:
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("claude_agent_sdk").setLevel(logging.DEBUG)

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from coordinator.schemas import EnablementPlan, OrchestratorRunResult
from enablement_agents.support._orchestrator_generator import (
    generate_orchestrator_files,
)
from ui.api.live_runner import run_live_plan
from ui.api.synthetic import build_synthetic_plan

logger = logging.getLogger("ui.api.server")

REPO_ROOT: Path = Path(__file__).resolve().parents[2]

#: Tools the UI offers. Restricted to the v1 catalog. Adding a tool here
#: requires also adding tools/<name>.yaml and mcp_registry/<name>.yaml.
_CATALOG_TOOLS: list[str] = ["intercom", "zendesk", "slack", "hubspot"]


# ---------------------------------------------------------------------------
# FastAPI app + CORS
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Enable AI — UI API",
    description="Backend for the Next.js test UI. Hosts the Support agent.",
    version="0.1.0",
)

# The Next.js dev server runs on 3000; CORS is permissive for local dev only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ToolSummary(BaseModel):
    """One catalog entry as the UI displays it."""

    name: str
    vendor: str
    primary_use: str
    categories: list[str]
    has_native_ai: bool
    has_mcp_server: bool
    mcp_origin: str | None
    notes: str | None


class EnablementRequest(BaseModel):
    """Payload for POST /api/enablement."""

    tools: list[str] = Field(
        description="Canonical tool names selected by the user. Must be a "
        "non-empty subset of the catalog returned by GET /api/tools.",
    )


class EnablementResponse(BaseModel):
    """Wrapper exposing the agent's plan plus run metadata."""

    mode: str  # "demo" or "live"
    plan: EnablementPlan


class GenerateOrchestratorRequest(BaseModel):
    """Payload for POST /api/generate-orchestrator.

    The frontend forwards the full plan it just received from /api/enablement.
    The plan's `orchestrator_pr_plan` field drives what gets generated; the
    rest is preserved for the README and PlanMetadata stamping.
    """

    plan: EnablementPlan


class EnvVarHint(BaseModel):
    """One env var the user should set before running the orchestrator."""

    name: str
    required: bool
    explanation: str


class GenerateOrchestratorResponse(BaseModel):
    """Result of a generate-orchestrator run.

    Wraps OrchestratorRunResult with two UX-only fields:
      - `output_path` — repo-relative path so the UI can show it
      - `env_var_hints` — friendly per-variable explanations for the
        env-var checklist
    """

    result: OrchestratorRunResult
    output_path: str
    env_var_hints: list[EnvVarHint]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _demo_mode() -> bool:
    if os.environ.get("ENABLE_AI_DEMO_MODE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    return not os.environ.get("ANTHROPIC_API_KEY")


def _load_tool(name: str) -> dict[str, Any]:
    path = REPO_ROOT / "tools" / f"{name}.yaml"
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def _load_mcp(name: str) -> dict[str, Any]:
    path = REPO_ROOT / "mcp_registry" / f"{name}.yaml"
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "demo_mode": _demo_mode(),
        "has_anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


@app.get("/api/tools", response_model=list[ToolSummary])
async def list_tools() -> list[ToolSummary]:
    """Return the 4 catalog tools the UI offers."""
    out: list[ToolSummary] = []
    for name in _CATALOG_TOOLS:
        tool_data = _load_tool(name)
        mcp_data = _load_mcp(name)
        mcp_block = mcp_data.get("mcp_server", {}) or {}
        out.append(
            ToolSummary(
                name=name,
                vendor=tool_data.get("vendor", name),
                primary_use=_primary_use_lookup(name),
                categories=tool_data.get("categories", []) or [],
                has_native_ai=bool(tool_data.get("native_ai_features")),
                has_mcp_server=bool(mcp_block.get("available")),
                mcp_origin=mcp_block.get("origin"),
                notes=tool_data.get("notes"),
            )
        )
    return out


@app.post("/api/enablement", response_model=EnablementResponse)
async def run_enablement(req: EnablementRequest) -> EnablementResponse:
    """Run the Support agent against the user-selected tools."""
    if not req.tools:
        raise HTTPException(400, "Select at least one tool.")

    unknown = [t for t in req.tools if t not in _CATALOG_TOOLS]
    if unknown:
        raise HTTPException(
            400,
            f"Unknown tool(s): {unknown}. Catalog tools: {_CATALOG_TOOLS}.",
        )

    if _demo_mode():
        logger.info("running enablement in DEMO mode for tools=%s", req.tools)
        plan = build_synthetic_plan(req.tools)
        return EnablementResponse(mode="demo", plan=plan)

    logger.info("running enablement in LIVE mode for tools=%s", req.tools)
    try:
        plan = await run_live_plan(req.tools)
    except Exception as exc:  # noqa: BLE001 — turn any agent error into a 502 with the real message
        logger.exception("live runner failed for tools=%s", req.tools)
        raise HTTPException(
            status_code=502,
            detail=(
                f"Live-mode run failed: {type(exc).__name__}: {exc}. "
                "Check the backend terminal for the full traceback."
            ),
        ) from exc
    return EnablementResponse(mode="live", plan=plan)


# ---------------------------------------------------------------------------
# Env var explanations — surfaced in the UI after orchestrator generation
# so the user knows what each variable does and which are required vs.
# optional. Keys here match variable names in the root `.env.example`.
# ---------------------------------------------------------------------------

_ENV_VAR_EXPLANATIONS: dict[str, tuple[bool, str]] = {
    "ANTHROPIC_API_KEY": (
        True,
        "Required to call Claude for intent classification and response "
        "drafting. Without this the orchestrator falls back to stub "
        "classifier (demo mode).",
    ),
    "LAUNCHDARKLY_SDK_KEY": (
        False,
        "Optional. Lets the orchestrator fetch its system prompt at "
        "runtime from a LaunchDarkly AI Config and emit "
        "support.escalation / support.error events. Without it the "
        "orchestrator uses the on-disk v1_baseline.md prompt and skips "
        "event tracking.",
    ),
    "INTERCOM_API_KEY": (
        False,
        "Optional. Only needed if you want the orchestrator to send "
        "real Intercom replies. Stubbed responses are used when missing.",
    ),
    "ZENDESK_API_TOKEN": (
        False,
        "Optional. Only needed for real Zendesk knowledge base lookups. "
        "Stubbed otherwise.",
    ),
    "SLACK_BOT_TOKEN": (
        False,
        "Optional. Only needed if escalation handoffs should land in a "
        "real Slack channel. Stubbed otherwise.",
    ),
    "HUBSPOT_API_KEY": (
        False,
        "Optional. Only needed for real HubSpot CRM lookups. The "
        "generated HubSpot MCP stub returns synthetic data without it.",
    ),
    "ENABLE_AI_DEMO_MODE": (
        False,
        "Set to false to run the orchestrator against real LLM and SaaS "
        "APIs. Defaults to true (safe) — stubs are used and no external "
        "calls are made.",
    ),
    "OTEL_EXPORTER_ENDPOINT": (
        False,
        "Optional. If set, the orchestrator exports OpenTelemetry spans "
        "to this OTLP HTTP endpoint. Otherwise spans go to stderr.",
    ),
    "OTEL_SERVICE_NAME": (
        False,
        "Optional. Identifies the orchestrator in traces. Defaults to "
        "'support-orchestrator'.",
    ),
}


def _build_env_var_hints(env_vars: list[str]) -> list[EnvVarHint]:
    """Map plan's env_vars_required → user-facing checklist items."""
    out: list[EnvVarHint] = []
    for name in env_vars:
        required, explanation = _ENV_VAR_EXPLANATIONS.get(
            name,
            (False, "No explanation registered — check root .env.example."),
        )
        out.append(
            EnvVarHint(name=name, required=required, explanation=explanation)
        )
    return out


@app.post(
    "/api/generate-orchestrator",
    response_model=GenerateOrchestratorResponse,
)
async def generate_orchestrator(
    req: GenerateOrchestratorRequest,
) -> GenerateOrchestratorResponse:
    """Materialize the orchestrator tree on disk from the supplied plan.

    Writes to `orchestrators/<department>/` (canonical location). Any
    previous orchestrator tree there is wiped and recreated — the
    generator owns that directory. The OrchestratorRunResult enumerates
    every file written.
    """
    plan = req.plan
    if plan.orchestrator_pr_plan is None:
        raise HTTPException(
            400,
            "Plan has no orchestrator_pr_plan — nothing to generate. "
            "Re-run /api/enablement with a request that asks for the "
            "orchestrator artifact.",
        )

    output_root = REPO_ROOT / "orchestrators" / plan.department
    try:
        result = generate_orchestrator_files(plan, output_root)
    except Exception as exc:  # noqa: BLE001
        logger.exception("generate_orchestrator_files failed")
        raise HTTPException(
            status_code=502,
            detail=(
                f"Orchestrator generation failed: {type(exc).__name__}: "
                f"{exc}. Check the backend terminal for the full traceback."
            ),
        ) from exc

    # Re-create __init__.py markers wiped by the generator — required so
    # Python sees orchestrators/<department>/ as an importable package.
    for sub in [
        REPO_ROOT / "orchestrators",
        output_root,
        output_root / "mcp_servers",
    ]:
        init = sub / "__init__.py"
        if sub.exists() and not init.exists():
            init.touch()

    rel_output = str(output_root.relative_to(REPO_ROOT))
    hints = _build_env_var_hints(result.env_vars_required)
    logger.info(
        "generate_orchestrator wrote %d files to %s; env_vars=%s",
        len(result.files_created),
        rel_output,
        result.env_vars_required,
    )
    return GenerateOrchestratorResponse(
        result=result,
        output_path=rel_output,
        env_var_hints=hints,
    )


# ---------------------------------------------------------------------------
# Live-mode runner
# ---------------------------------------------------------------------------

# The UI's live path calls the Anthropic API directly (see
# ui/api/live_runner.py). This is an architectural deviation from the v1
# build plan — the rest of the system uses claude-agent-sdk. The UI made
# the swap to work around an SDK 0.1.81 bundled-CLI integration issue.
# `run_live_plan` is imported at the top of this module and called below
# from the `/api/enablement` handler.
def _primary_use_lookup(name: str) -> str:
    """Pull the primary_use from the support stack file. Used by /api/tools."""
    stack = yaml.safe_load(
        (REPO_ROOT / "stacks" / "support.yaml").read_text(encoding="utf-8")
    )
    for entry in stack.get("tools", []) or []:
        if entry.get("name") == name:
            primary = entry.get("primary_use", "")
            return str(primary) if primary is not None else ""
    return "unknown"
