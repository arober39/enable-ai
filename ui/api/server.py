"""FastAPI backend for the Enable AI UI.

Endpoints:
  - GET    /api/tools                          — seed catalog + user's researched tools
  - POST   /api/tools/research                 — LLM-research a free-form tool name and cache
  - DELETE /api/tools/cache/{name}             — remove a researched tool from the cache
  - GET    /api/roles                          — seeded roles plus this user's researched roles
  - POST   /api/roles/research                 — LLM-research a free-form job role and cache
  - DELETE /api/roles/cache/{role_id}          — remove a researched role from the cache
  - GET    /api/preferences                    — current user's stored preferences
  - PUT    /api/preferences/role               — set the user's selected role
  - POST   /api/enablement                     — run Enablement agent → EnablementPlan
  - POST   /api/build-workflow                 — Phase 2.1: 2-stage pipeline → WorkflowDefinition
  - GET    /api/workflows                      — list this user's persisted workflows
  - DELETE /api/workflows/{role_id}            — remove one workflow
  - POST   /api/run-workflow                   — execute a request through the interpreter
  - GET    /api/stacks/{role_id}               — declared tool names for a role
  - GET    /api/outcomes                       — recent measured workflow runs for this user
  - GET    /api/outcomes/summary               — success and real-call rates per recommendation
  - POST   /api/rollback                       — uninstall the workflow for one recommendation
  - POST   /api/grokbot/handoff               — copy-paste Grok Bot text; optional webhook POST
  - POST   /api/generate-orchestrator          — (LEGACY 1.4) 4-stage codegen pipeline
  - POST   /api/run-orchestrator               — (LEGACY 1.4) run codegen-produced orchestrator
  - GET    /api/saved-recommendations          — list user's saved-for-later recs
  - POST   /api/saved-recommendations          — save a recommendation for later
  - DELETE /api/saved-recommendations/{id}     — remove a saved recommendation
  - GET    /api/credentials                    — list stored credentials (values masked)
  - PUT    /api/credentials/{key}              — create or update a credential
  - DELETE /api/credentials/{key}              — delete a credential
  - GET    /api/credentials/{key}/reveal       — return the unmasked value

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
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

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

import importlib.util
import inspect

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from coordinator.schemas import EnablementPlan, Recommendation
from core.credentials import (
    LocalFileCredentialStore,
    credentials_in_env,
)
from core.grokbot import GrokbotHandoff, HandoffCredentials, build_handoff
from core.grokbot_roster import clear_remembered_rosters
from core.grokbot_webhook import deliver_handoff_webhook
from core.identity import UserContext, local_user
from core.jev import label_escalation
from core.outcomes import (
    OutcomeRecord,
    OutcomeStatus,
    RecommendationMetrics,
    RollbackError,
    StepSummary,
    list_outcomes,
    recommendation_metrics,
    record_outcome,
    rollback_recommendation,
    step_summaries_from_trace,
)
from core.preferences import Preferences, get_preferences, set_selected_role
from core.role_catalog import (
    delete_cached_role,
    list_available_roles,
    load_role_for_user,
    normalize_role_id,
)
from core.roles import Role
from core.saved_recommendations import (
    SavedRecommendation,
    list_saved,
    remove_saved,
    save_recommendation,
)
from core.stacks import StackNotFoundError, declared_tool_names
from core.state import orchestrator_path
from core.telemetry import track_workflow_run
from core.tool_catalog import (
    ToolCapability,
    delete_cached_tool,
    is_known,
    list_researched_tools,
    load_tool,
    normalize_name,
)
from core.tool_credentials import keys_for_tools, keys_for_workflow, missing_keys
from core.workflow import WorkflowDefinition
from core.workflow_storage import (
    delete_workflow,
    list_workflows,
    load_workflow,
    save_workflow,
)
from enablement_agents.generator.artifacts import BuildResult
from enablement_agents.generator.consolidation_pipeline import (
    build_consolidation_plan,
)
from enablement_agents.generator.demo_install import (
    install_demo_consolidation,
    install_demo_native_setup,
    install_demo_workflow,
)
from enablement_agents.generator.native_ai_pipeline import build_native_ai_setup
from enablement_agents.generator.pipeline import run_pipeline
from enablement_agents.generator.schemas import (
    GeneratorContext,
    GeneratorRunResult,
)
from enablement_agents.generator.workflow_pipeline import build_workflow
from enablement_agents.role_research import research_role
from enablement_agents.tool_research import research_tool
from enablement_agents.workflow_interpreter import (
    WorkflowRunResult,
    run_workflow,
)
from ui.api.jobs import Job, cancel_job, get_job, spawn, start_job
from ui.api.live_runner import run_live_plan
from ui.api.synthetic import build_synthetic_plan

logger = logging.getLogger("ui.api.server")

REPO_ROOT: Path = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# FastAPI app + CORS
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Settings keys and copy-paste Grok Bot memory belong to this process.
    # A restart starts with an empty vault and no remembered bots.
    # Tests import this app; they must not wipe the developer's state.
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        LocalFileCredentialStore(local_user()).clear()
        clear_remembered_rosters()
    yield


app = FastAPI(
    title="Enable AI — UI API",
    description="Backend for the Next.js test UI. Hosts the Support agent.",
    version="0.1.0",
    lifespan=_lifespan,
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
    """One catalog entry as the UI picker displays it."""

    name: str
    vendor: str
    categories: list[str]
    has_native_ai: bool
    has_mcp_server: bool
    mcp_origin: str | None
    notes: str | None
    source: str  # "seed" | "researched"


class ResearchToolRequest(BaseModel):
    """Body for POST /api/tools/research. Free-form tool name from typeahead."""

    name: str = Field(min_length=1, max_length=120)


class EnablementRequest(BaseModel):
    """Payload for POST /api/enablement."""

    tools: list[str] = Field(
        description="Canonical tool names selected by the user. Must be a "
        "non-empty subset of the catalog returned by GET /api/tools.",
    )
    role: str | None = Field(
        default=None,
        description="Role id from /api/roles. If omitted, the user's "
        "stored preference is used; if no preference is set, defaults to "
        "the registry's default role.",
    )


class EnablementResponse(BaseModel):
    """Wrapper exposing the agent's plan plus run metadata."""

    mode: str  # "demo" or "live"
    plan: EnablementPlan


class GenerateOrchestratorRequest(BaseModel):
    """Payload for POST /api/generate-orchestrator (Phase 1.4 pipeline).

    The UI sends the full plan + the id of the one recommendation the
    user wants to build. The generator's 4-stage pipeline uses the
    user's currently-stored credentials, the selected tools' catalog
    data, and the selected role to produce a per-user, per-role
    `orchestrator.py`.
    """

    plan: EnablementPlan
    selected_recommendation_id: str = Field(min_length=1)
    role: str | None = Field(
        default=None,
        description="Optional role id override; falls back to user preference.",
    )


class SaveRecommendationRequest(BaseModel):
    """Body for POST /api/saved-recommendations."""

    role_id: str = Field(min_length=1)
    tools: list[str]
    plan_summary: str
    recommendation: Recommendation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_user() -> UserContext:
    """Resolve the caller's user identity.

    Phase 1 single-user-local: always returns `local_user()`. Phase 2
    populates this from auth (FastAPI Depends pattern). Locked phase 1
    commitment (#2): every endpoint goes through this helper, even when
    the value is constant — so the multi-user transition is a swap of
    one function, not a refactor of every route.
    """
    return local_user()


def _demo_mode() -> bool:
    if os.environ.get("ENABLE_AI_DEMO_MODE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    return not os.environ.get("ANTHROPIC_API_KEY")


def _mask(value: str) -> str:
    """Convex-style preview: bullets + last 4 chars (or all bullets if short)."""
    if len(value) <= 4:
        return "•" * len(value)
    return "•" * 8 + value[-4:]


def _resolve_role(user: UserContext, role_id: str) -> Role:
    """Seeded role, or this user's researched card when one replaces it."""
    try:
        return load_role_for_user(user, role_id)
    except KeyError:
        raise HTTPException(400, f"Unknown role: {role_id}") from None


def _to_tool_summary(cap: ToolCapability) -> ToolSummary:
    return ToolSummary(
        name=cap.canonical_name,
        vendor=cap.vendor,
        categories=list(cap.categories),
        has_native_ai=bool(cap.native_ai_features),
        has_mcp_server=cap.mcp_server.available,
        mcp_origin=cap.mcp_server.origin,
        notes=cap.notes,
        source=cap.source,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


_BOOT_ID = uuid.uuid4().hex


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "demo_mode": _demo_mode(),
        "has_anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "boot_id": _BOOT_ID,
    }


@app.get("/api/tools", response_model=list[ToolSummary])
async def get_tools() -> list[ToolSummary]:
    """Return this user's researched tools. Seed files stay off the picker."""
    user = _current_user()
    return [_to_tool_summary(c) for c in list_researched_tools(user)]


@app.post("/api/tools/research", response_model=ToolSummary)
async def research_new_tool(req: ResearchToolRequest) -> ToolSummary:
    """LLM-research a free-form tool name and cache the result.

    Researched tools live in `agent-state/<user_id>/tool_cache/<name>.json`.
    A repeat call for the same name overwrites the cached record (the UI
    treats this as a refresh).
    """
    user = _current_user()
    try:
        normalize_name(req.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        capability = await research_tool(req.name, user)
    except RuntimeError as exc:
        # ANTHROPIC_API_KEY missing or model failure — surface as 502 so
        # the UI can show a useful error rather than a generic 500.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _to_tool_summary(capability)


@app.delete("/api/tools/cache/{name}")
async def delete_researched_tool(name: str) -> dict[str, bool]:
    """Remove a researched tool from the user's cache. Seed tools cannot be removed."""
    user = _current_user()
    removed = delete_cached_tool(user, name)
    return {"removed": removed}


@app.post("/api/enablement", response_model=EnablementResponse)
async def run_enablement(req: EnablementRequest) -> EnablementResponse:
    """Run the Enablement agent for the chosen role against selected tools."""
    if not req.tools:
        raise HTTPException(400, "Select at least one tool.")

    user = _current_user()
    unknown = [t for t in req.tools if not is_known(user, t)]
    if unknown:
        raise HTTPException(
            400,
            f"Unknown tool(s): {unknown}. Research them via "
            "POST /api/tools/research first.",
        )

    role_id = req.role or get_preferences(user).selected_role
    role = _resolve_role(user, role_id)

    if _demo_mode():
        logger.info(
            "running enablement in DEMO mode role=%s tools=%s",
            role.id,
            req.tools,
        )
        plan = build_synthetic_plan(req.tools, role, user)
        return EnablementResponse(mode="demo", plan=plan)

    logger.info(
        "running enablement in LIVE mode role=%s tools=%s",
        role.id,
        req.tools,
    )
    try:
        plan = await run_live_plan(req.tools, role, user)
    except Exception as exc:  # noqa: BLE001 — turn any agent error into a 502 with the real message
        logger.exception(
            "live runner failed role=%s tools=%s",
            role.id,
            req.tools,
        )
        raise HTTPException(
            status_code=502,
            detail=(
                f"Live-mode run failed: {type(exc).__name__}: {exc}. "
                "Check the backend terminal for the full traceback."
            ),
        ) from exc
    return EnablementResponse(mode="live", plan=plan)


# ---------------------------------------------------------------------------
# Role registry + per-user preferences
# ---------------------------------------------------------------------------


class RoleSummary(BaseModel):
    """One role as the UI displays it in the picker."""

    id: str
    display_name: str
    department: str
    description: str
    capabilities: list[str]
    source: Literal["seed", "researched"] = "seed"


class ResearchRoleRequest(BaseModel):
    """Body for POST /api/roles/research. Free-form job title."""

    name: str = Field(min_length=1, max_length=120)
    role_id: str | None = None


class SetRoleRequest(BaseModel):
    """Body for PUT /api/preferences/role."""

    role: str = Field(min_length=1)


def _role_to_summary(role: Role) -> RoleSummary:
    return RoleSummary(
        id=role.id,
        display_name=role.display_name,
        department=role.department,
        description=role.description,
        capabilities=list(role.capabilities),
        source=role.source,
    )


@app.get("/api/roles", response_model=list[RoleSummary])
async def get_roles() -> list[RoleSummary]:
    """Return seeded roles plus this user's researched roles.

    A researched card replaces the seed for that user. The seed file stays.
    """
    return [_role_to_summary(r) for r in list_available_roles(_current_user())]


@app.post("/api/roles/research", response_model=RoleSummary)
async def research_new_role(req: ResearchRoleRequest) -> RoleSummary:
    """LLM-research a free-form job role and cache the capability card.

    Researched roles live in `agent-state/<user_id>/role_cache/<id>.json`.
    A repeat call for the same name overwrites the cached card.
    """
    user = _current_user()
    try:
        normalize_role_id(req.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        role = await research_role(req.name, user, role_id=req.role_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _role_to_summary(role)


@app.delete("/api/roles/cache/{role_id}")
async def delete_researched_role(role_id: str) -> dict[str, bool]:
    """Remove a researched role from the user's cache. Seed roles stay on disk."""
    removed = delete_cached_role(_current_user(), role_id)
    return {"removed": removed}


@app.get("/api/preferences", response_model=Preferences)
async def get_user_preferences() -> Preferences:
    """Return the current user's preferences (selected role, etc.)."""
    return get_preferences(_current_user())


@app.put("/api/preferences/role", response_model=Preferences)
async def set_user_role(req: SetRoleRequest) -> Preferences:
    """Persist the user's selected role. Seeded and researched roles are valid."""
    user = _current_user()
    _resolve_role(user, req.role)
    return set_selected_role(user, req.role)


# ---------------------------------------------------------------------------
# Env var explanations — legacy hints retained for human-friendly UI text.
# The Phase 1.4 generator produces its own env var list per recommendation;
# these explanations are used when an env var name is recognized.
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
    "INTERCOM_API_TOKEN": (
        False,
        "Intercom access token (Developer Hub → Settings → Workspace "
        "apps → Authentication). Required for any real Intercom call. "
        "Read actions (search_conversations, get_conversation) work "
        "with just this; write actions also need INTERCOM_ADMIN_ID.",
    ),
    "INTERCOM_ADMIN_ID": (
        False,
        "Numeric admin id this app posts as. Required only for write "
        "actions (send_reply, assign_to_agent). Find it at Settings → "
        "Workspace → Teammates → click your service admin → URL "
        "contains `.../admins/<id>`.",
    ),
    "INTERCOM_API_KEY": (
        False,
        "Legacy name — use INTERCOM_API_TOKEN instead. Kept here for "
        "back-compat with workflows generated under earlier phases.",
    ),
    "ZENDESK_SUBDOMAIN": (
        False,
        "Zendesk subdomain — the leading word from your Zendesk URL, "
        "e.g. `mycompany` from `mycompany.zendesk.com`. Real Zendesk "
        "calls need this plus ZENDESK_EMAIL and ZENDESK_API_TOKEN.",
    ),
    "ZENDESK_EMAIL": (
        False,
        "Email of the Zendesk user the API token belongs to. Used for "
        "HTTP Basic auth (`{email}/token`). Pair with ZENDESK_SUBDOMAIN "
        "and ZENDESK_API_TOKEN.",
    ),
    "ZENDESK_API_TOKEN": (
        False,
        "Zendesk API token (Admin → Apps → API → token). When set with "
        "ZENDESK_SUBDOMAIN + ZENDESK_EMAIL, the Zendesk adapter makes "
        "real REST calls; otherwise it returns synthetic stub data.",
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


@app.post(
    "/api/generate-orchestrator",
    response_model=GeneratorRunResult,
)
async def generate_orchestrator(
    req: GenerateOrchestratorRequest,
) -> GeneratorRunResult:
    """Run the 4-stage LLM generator and write `orchestrator.py` to disk.

    Output: `orchestrators/<user_id>/<role_id>/orchestrator.py`. Any
    prior orchestrator at that path is wiped. The structured result
    includes per-stage timings + the code plan + an explanation.
    """
    user = _current_user()
    role_id = req.role or get_preferences(user).selected_role
    role = _resolve_role(user, role_id)

    # Resolve the selected recommendation
    rec: Recommendation | None = None
    for candidate in req.plan.recommendations:
        if candidate.id == req.selected_recommendation_id:
            rec = candidate
            break
    if rec is None:
        raise HTTPException(
            400,
            f"Recommendation {req.selected_recommendation_id!r} not "
            "found in plan.recommendations.",
        )

    # Resolve tool capabilities
    capabilities: list[ToolCapability] = []
    missing: list[str] = []
    for tool_name in rec.tools_affected or []:
        cap = load_tool(user, tool_name)
        if cap is None:
            missing.append(tool_name)
            continue
        capabilities.append(cap)
    if missing:
        raise HTTPException(
            400,
            f"Tool(s) not in catalog or user cache: {missing}. "
            "Research them via /api/tools/research first.",
        )

    store = LocalFileCredentialStore(user)
    ctx = GeneratorContext(
        role_id=role.id,
        role_display_name=role.display_name,
        recommendation=rec,
        tool_capabilities=capabilities,
        available_credentials=store.list_keys(),
    )

    # The generator runs Claude calls; it needs ANTHROPIC_API_KEY in env.
    # Inject from the credential store for the duration of the call.
    with credentials_in_env(store):
        try:
            result = await run_pipeline(user, ctx)
        except Exception as exc:  # noqa: BLE001
            logger.exception("generator pipeline failed")
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Generator pipeline failed: {type(exc).__name__}: "
                    f"{exc}. Check the backend terminal for the full traceback."
                ),
            ) from exc
    logger.info(
        "generator pipeline role=%s rec=%s ok=%s output=%s",
        role.id,
        rec.id,
        result.ok,
        result.output_path,
    )
    return result


# ---------------------------------------------------------------------------
# Saved-for-later recommendations
# ---------------------------------------------------------------------------


@app.get(
    "/api/saved-recommendations",
    response_model=list[SavedRecommendation],
)
async def get_saved_recommendations() -> list[SavedRecommendation]:
    """Return every recommendation the user has parked for later."""
    return list_saved(_current_user())


@app.post(
    "/api/saved-recommendations",
    response_model=SavedRecommendation,
)
async def save_recommendation_endpoint(
    req: SaveRecommendationRequest,
) -> SavedRecommendation:
    """Save a recommendation for later (full context preserved)."""
    return save_recommendation(
        _current_user(),
        role_id=req.role_id,
        tools=req.tools,
        plan_summary=req.plan_summary,
        recommendation=req.recommendation,
    )


@app.delete("/api/saved-recommendations/{saved_id}")
async def delete_saved_recommendation(saved_id: str) -> dict[str, bool]:
    """Remove a saved recommendation by id."""
    return {"removed": remove_saved(_current_user(), saved_id)}


# ---------------------------------------------------------------------------
# Phase 2.1 workflow pipeline — plan-as-data replacement for 1.4 codegen
# ---------------------------------------------------------------------------


class BuildWorkflowRequest(BaseModel):
    """Body for POST /api/build-workflow."""

    plan: EnablementPlan
    selected_recommendation_id: str = Field(min_length=1)
    tools: list[str] = Field(
        description="The full stack the user picked when running the "
        "Enablement Agent. The workflow may legitimately reference any of "
        "these tools, not just the recommendation's `tools_affected`."
    )
    role: str | None = Field(
        default=None,
        description="Optional role override; falls back to user preference.",
    )


@app.post("/api/build-workflow", response_model=BuildResult)
async def build_workflow_endpoint(
    req: BuildWorkflowRequest,
) -> BuildResult:
    """Run the kind-appropriate build pipeline for the chosen recommendation.

    Dispatches on `Recommendation.kind`:
      - `orchestrate` / `augment_with_custom_ai` → 2-stage workflow pipeline.
        Persists the `WorkflowDefinition` so the interpreter can run it.
      - `use_native_ai` → 2-stage native-AI-setup pipeline. Returns
        configuration steps; no persistence (rebuild to re-display).
      - `consolidate` → 2-stage consolidation-plan pipeline. Returns
        migration plan; no persistence.

    The endpoint name retains `build-workflow` for back-compat but
    actually returns one of three artifact types in `BuildResult`. The
    UI reads `artifact_kind` to know what to render.
    """
    user = _current_user()
    role_id = req.role or get_preferences(user).selected_role
    role = _resolve_role(user, role_id)

    rec: Recommendation | None = None
    for candidate in req.plan.recommendations:
        if candidate.id == req.selected_recommendation_id:
            rec = candidate
            break
    if rec is None:
        raise HTTPException(
            400,
            f"Recommendation {req.selected_recommendation_id!r} not "
            "found in plan.recommendations.",
        )

    # Use the user's full selected stack (not just rec.tools_affected) so
    # the workflow can legitimately coordinate across all tools they picked.
    # Union with rec.tools_affected to handle older callers that still send
    # just the recommendation's tools.
    requested_tools = sorted(set(req.tools) | set(rec.tools_affected or []))
    if not requested_tools:
        raise HTTPException(
            400,
            "BuildWorkflowRequest.tools is empty — pass the stack the user "
            "selected when running the Enablement Agent.",
        )
    capabilities: list[ToolCapability] = []
    missing: list[str] = []
    for tool_name in requested_tools:
        cap = load_tool(user, tool_name)
        if cap is None:
            missing.append(tool_name)
            continue
        capabilities.append(cap)
    if missing:
        raise HTTPException(
            400,
            f"Tool(s) not in catalog or user cache: {missing}. "
            "Research them via /api/tools/research first.",
        )

    store = LocalFileCredentialStore(user)
    ctx = GeneratorContext(
        role_id=role.id,
        role_display_name=role.display_name,
        recommendation=rec,
        tool_capabilities=capabilities,
        available_credentials=store.list_keys(),
    )

    # Dispatch on kind. Only orchestrate / augment_with_custom_ai produce
    # runtime workflows; use_native_ai and consolidate produce
    # configuration / migration artifacts the user acts on themselves.
    with credentials_in_env(store):
        try:
            if _demo_mode():
                if rec.kind in ("orchestrate", "augment_with_custom_ai"):
                    result = install_demo_workflow(ctx)
                elif rec.kind == "use_native_ai":
                    result = install_demo_native_setup(ctx)
                elif rec.kind == "consolidate":
                    result = install_demo_consolidation(ctx)
                else:
                    raise HTTPException(
                        400,
                        f"Unknown recommendation kind: {rec.kind!r}",
                    )
            elif rec.kind in ("orchestrate", "augment_with_custom_ai"):
                result = await build_workflow(user, ctx)
            elif rec.kind == "use_native_ai":
                result = await build_native_ai_setup(ctx)
            elif rec.kind == "consolidate":
                result = await build_consolidation_plan(ctx)
            else:
                raise HTTPException(
                    400,
                    f"Unknown recommendation kind: {rec.kind!r}",
                )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("build pipeline failed (kind=%s)", rec.kind)
            raise HTTPException(
                status_code=502,
                detail=f"Build pipeline failed: {type(exc).__name__}: {exc}",
            ) from exc

    # Persist only when the artifact is a runtime workflow.
    if result.ok and result.workflow is not None:
        save_workflow(user, result.workflow)
    logger.info(
        "build pipeline role=%s rec=%s kind=%s ok=%s artifact=%s",
        role.id,
        rec.id,
        rec.kind,
        result.ok,
        result.artifact_kind,
    )
    return result


class JobResponse(BaseModel):
    """Poll body for a run that continues after the browser tab goes away."""

    id: str
    kind: Literal["enablement", "build"]
    status: Literal["running", "done", "error", "cancelled"]
    started_at: str
    result: dict[str, Any] | None = None
    error: str | None = None


def _job_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        kind=job.kind,
        status=job.status,
        started_at=job.started_at,
        result=job.result,
        error=job.error,
    )


@app.post("/api/jobs/enablement", response_model=JobResponse)
async def start_enablement_job(req: EnablementRequest) -> JobResponse:
    """Start an enablement run and return before it finishes."""
    job = start_job("enablement")

    async def _work() -> dict[str, Any]:
        plan = await run_enablement(req)
        return plan.model_dump(mode="json")

    spawn(job.id, _work())
    return _job_response(job)


@app.post("/api/jobs/build", response_model=JobResponse)
async def start_build_job(req: BuildWorkflowRequest) -> JobResponse:
    """Start a workflow build and return before it finishes."""
    job = start_job("build")

    async def _work() -> dict[str, Any]:
        built = await build_workflow_endpoint(req)
        return built.model_dump(mode="json")

    spawn(job.id, _work())
    return _job_response(job)


@app.post("/api/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_running_job(job_id: str) -> JobResponse:
    """Stop an enablement run or a workflow build that is still in progress."""
    job = cancel_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found. It ended when the server restarted.")
    return _job_response(job)


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def read_job(job_id: str) -> JobResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found. It ended when the server restarted.")
    return _job_response(job)


@app.get("/api/workflows", response_model=list[WorkflowDefinition])
async def get_workflows() -> list[WorkflowDefinition]:
    """List all WorkflowDefinitions persisted for the current user."""
    return list_workflows(_current_user())


@app.delete("/api/workflows/{role_id}")
async def delete_workflow_endpoint(role_id: str) -> dict[str, bool]:
    """Remove the workflow for a role."""
    return {"removed": delete_workflow(_current_user(), role_id)}


class GrokbotHandoffRequest(BaseModel):
    """Fields for a copy-paste Grok Bot assignment.

    ``recommendation_id`` does not have to belong to the current plan.
    A recommendation the user wrote on step 5 is sent as ``R-CUSTOM``.

    When both webhook settings are in the environment or ``.env``, the
    server also POSTs this assignment. Copy-paste still works when they
    are missing or the POST fails.
    """

    recommendation_id: str = Field(
        min_length=1,
        description="Plan id such as R-001, or R-CUSTOM for a recommendation the user wrote.",
    )
    kind: str = Field(min_length=1)
    description: str = Field(min_length=1)
    notes: str | None = None
    role_name: str = Field(min_length=1)
    role_id: str | None = None
    tools: list[str] = Field(default_factory=list)


@app.post("/api/grokbot/handoff", response_model=GrokbotHandoff)
def grokbot_handoff(req: GrokbotHandoffRequest) -> GrokbotHandoff:
    """Draft paste text, including where Jev says the bot belongs.

    Does not call createAgent or updateAgent. listAgents runs only when
    gateway credentials are set. Bots remembered from earlier handoffs
    in this process are included either way. A restart clears that roster.

    After the handoff is built, POST it to the Grok Bot webhook when both
    webhook settings are configured. A missing or failed webhook still
    returns the paste text.
    """
    user = _current_user()
    creds = HandoffCredentials(LocalFileCredentialStore(user))
    handoff = build_handoff(
        recommendation_id=req.recommendation_id,
        kind=req.kind,
        description=req.description,
        notes=req.notes,
        role_name=req.role_name,
        role_id=req.role_id,
        tools=req.tools,
        creds=creds,
        user=user,
    )
    delivery = deliver_handoff_webhook(
        creds,
        name=handoff.name,
        title=handoff.title,
        description=handoff.description,
        placement=handoff.placement,
        action=handoff.action,
        recommendation_id=req.recommendation_id,
        role_name=req.role_name,
        role_id=req.role_id,
        tools=req.tools,
        existing_bot_name=handoff.existing_bot_name,
    )
    if delivery.status == "sent":
        return handoff.model_copy(
            update={"webhook_status": "sent", "webhook_message": delivery.message}
        )
    if delivery.status == "failed":
        return handoff.model_copy(
            update={"webhook_status": "failed", "webhook_message": delivery.message}
        )
    return handoff


class RunWorkflowRequest(BaseModel):
    """Body for POST /api/run-workflow."""

    payload: dict[str, Any] = Field(
        description="Free-form JSON forwarded to the workflow interpreter "
        "as the inbound request."
    )
    role: str | None = Field(
        default=None,
        description="Optional role override; falls back to user preference.",
    )


@app.post("/api/run-workflow", response_model=WorkflowRunResult)
async def run_workflow_endpoint(req: RunWorkflowRequest) -> WorkflowRunResult:
    """Execute the user's stored workflow for the chosen role."""
    user = _current_user()
    role_id = req.role or get_preferences(user).selected_role
    definition = load_workflow(user, role_id)
    if definition is None:
        raise HTTPException(
            404,
            f"No workflow built yet for role {role_id!r}. Pick a "
            "recommendation and click 'Build workflow' first.",
        )
    store = LocalFileCredentialStore(user)
    started_at = datetime.now(UTC)
    rec_id = getattr(definition, "recommendation_id", None)
    with credentials_in_env(store):
        try:
            result = await run_workflow(definition, req.payload, store)
        except Exception as exc:  # noqa: BLE001
            logger.exception("run_workflow failed")
            _persist_outcome(
                user,
                role_id=role_id,
                recommendation_id=rec_id,
                status="failed",
                started_at=started_at,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise HTTPException(
                status_code=502,
                detail=f"Workflow run failed: {type(exc).__name__}: {exc}",
            ) from exc
    _persist_outcome(
        user,
        role_id=role_id,
        recommendation_id=rec_id,
        status="ok" if result.ok else "failed",
        started_at=started_at,
        step_summaries=step_summaries_from_trace(result.trace),
        error=result.error,
        payload=req.payload,
        output=result.output,
    )
    return result


def _persist_outcome(
    user: UserContext,
    *,
    role_id: str,
    recommendation_id: str | None,
    status: OutcomeStatus,
    started_at: datetime,
    error: str | None = None,
    step_summaries: list[StepSummary] | None = None,
    payload: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
) -> None:
    """Best-effort Measure write. Must never change the HTTP status of the run."""
    try:
        scored = label_escalation(payload, output, LocalFileCredentialStore(user))
        record_outcome(
            user,
            role_id=role_id,
            recommendation_id=recommendation_id,
            status=status,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            step_summaries=step_summaries,
            error=error,
            escalated=bool(scored["escalate"]) if payload or output else None,
            escalation_mode=scored["mode"] if payload or output else None,
            escalation_source=scored["source"] if payload or output else None,
        )
        track_workflow_run(
            role_id=role_id,
            recommendation_id=recommendation_id,
            status=status,
            sdk_key=LocalFileCredentialStore(user).get("LAUNCHDARKLY_SDK_KEY"),
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to persist workflow outcome")


class DeclaredStackResponse(BaseModel):
    """Tool names from `stacks/<department>.yaml` for one role."""

    role_id: str
    tools: list[str]


@app.get("/api/stacks/{role_id}", response_model=DeclaredStackResponse)
async def get_declared_stack(role_id: str) -> DeclaredStackResponse:
    """Return the role's declared stack so the UI can select those tools."""
    try:
        tools = declared_tool_names(role_id)
    except KeyError:
        raise HTTPException(404, f"Unknown role: {role_id}") from None
    except StackNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc
    return DeclaredStackResponse(role_id=role_id, tools=tools)


@app.get("/api/outcomes", response_model=list[OutcomeRecord])
async def get_outcomes() -> list[OutcomeRecord]:
    """Return recent measured workflow runs for the current user, newest first."""
    return list_outcomes(_current_user())


@app.get("/api/outcomes/summary", response_model=list[RecommendationMetrics])
async def get_outcome_summary() -> list[RecommendationMetrics]:
    """Success, error, and real-vs-stub rates per installed recommendation."""
    return recommendation_metrics(_current_user())


class RollbackRequest(BaseModel):
    """Body for POST /api/rollback."""

    recommendation_id: str = Field(min_length=1)
    role: str | None = Field(
        default=None,
        description="Optional role override; falls back to user preference.",
    )


@app.post("/api/rollback", response_model=OutcomeRecord)
async def rollback_endpoint(req: RollbackRequest) -> OutcomeRecord:
    """Uninstall the workflow that was built from this recommendation."""
    user = _current_user()
    role_id = req.role or get_preferences(user).selected_role
    try:
        return rollback_recommendation(user, role_id, req.recommendation_id)
    except RollbackError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


# ---------------------------------------------------------------------------
# Live-mode runner
# ---------------------------------------------------------------------------

# The UI's live path calls the Anthropic API directly (see
# ui/api/live_runner.py). This is an architectural deviation from the v1
# build plan — the rest of the system uses claude-agent-sdk. The UI made
# the swap to work around an SDK 0.1.81 bundled-CLI integration issue.
# `run_live_plan` is imported at the top of this module and called below
# from the `/api/enablement` handler.
# ---------------------------------------------------------------------------
# Credential management — Convex-style UI vault.
#
# Storage: per-user JSON file at agent-state/<user_id>/credentials.json,
# backed by core.credentials.LocalFileCredentialStore. The UI never writes
# to .env directly (locked phase 1 commitment #4). Run-orchestrator
# endpoint injects creds into the env at call time via
# credentials_in_env() — phase 2 swaps that for subprocess spawning.
# ---------------------------------------------------------------------------


class CredentialSummary(BaseModel):
    """One credential entry as the UI displays it. Value is masked."""

    key: str
    masked_value: str


class CredentialUpsertRequest(BaseModel):
    """Body for PUT /api/credentials/{key}."""

    value: str = Field(min_length=1)


class CredentialRevealResponse(BaseModel):
    """Returned by /api/credentials/{key}/reveal — the unmasked value."""

    key: str
    value: str


class RequiredCredentialsResponse(BaseModel):
    """Keys the selected tools need, and which of them are not in the vault yet."""

    required: list[dict[str, str]]
    missing: list[str]


@app.get("/api/credentials/for-workflow", response_model=RequiredCredentialsResponse)
async def workflow_credentials(role: str | None = None) -> RequiredCredentialsResponse:
    """Keys the built workflow will read, and which are still missing."""
    user = _current_user()
    role_id = role or get_preferences(user).selected_role
    definition = load_workflow(user, role_id)
    if definition is None:
        return RequiredCredentialsResponse(required=[], missing=[])
    pairs = keys_for_workflow(
        [step.tool for step in definition.steps],
        list(definition.env_vars_required),
    )
    present = set(LocalFileCredentialStore(user).list_keys())
    return RequiredCredentialsResponse(
        required=[{"tool": source, "key": key} for source, key in pairs],
        missing=[key for _source, key in pairs if key not in present],
    )


@app.get("/api/credentials/required", response_model=RequiredCredentialsResponse)
async def required_credentials(tools: str = "") -> RequiredCredentialsResponse:
    """Keys for a comma-separated tool list, checked against the vault."""
    names = [part.strip() for part in tools.split(",") if part.strip()]
    user = _current_user()
    present = set(LocalFileCredentialStore(user).list_keys())
    return RequiredCredentialsResponse(
        required=[{"tool": tool, "key": key} for tool, key in keys_for_tools(names)],
        missing=missing_keys(names, present),
    )


@app.get("/api/credentials", response_model=list[CredentialSummary])
async def list_credentials() -> list[CredentialSummary]:
    """Return every stored credential, value masked."""
    user = _current_user()
    store = LocalFileCredentialStore(user)
    out: list[CredentialSummary] = []
    for key in store.list_keys():
        value = store.get(key) or ""
        out.append(CredentialSummary(key=key, masked_value=_mask(value)))
    return out


@app.put("/api/credentials/{key}", response_model=CredentialSummary)
async def upsert_credential(
    key: str, req: CredentialUpsertRequest
) -> CredentialSummary:
    """Create or update a credential."""
    if not key or not key.replace("_", "").isalnum():
        raise HTTPException(
            400,
            "Credential key must be alphanumeric/underscore "
            "(e.g. ANTHROPIC_API_KEY).",
        )
    user = _current_user()
    store = LocalFileCredentialStore(user)
    store.set(key, req.value)
    return CredentialSummary(key=key, masked_value=_mask(req.value))


@app.delete("/api/credentials/{key}")
async def delete_credential(key: str) -> dict[str, bool]:
    """Delete a credential. No-op if it doesn't exist."""
    user = _current_user()
    store = LocalFileCredentialStore(user)
    store.delete(key)
    return {"deleted": True}


@app.get(
    "/api/credentials/{key}/reveal",
    response_model=CredentialRevealResponse,
)
async def reveal_credential(key: str) -> CredentialRevealResponse:
    """Return the unmasked credential value (for the UI's copy button)."""
    user = _current_user()
    store = LocalFileCredentialStore(user)
    value = store.get(key)
    if value is None:
        raise HTTPException(404, f"Credential not found: {key}")
    return CredentialRevealResponse(key=key, value=value)


# ---------------------------------------------------------------------------
# Run the orchestrator with credentials injected from the store.
#
# Phase 1 in-process implementation. Phase 2 swaps to subprocess.Popen with
# env=store.export_env(...) and reads structured stdout. Orchestrator code
# does not change between phases — only this call site does.
# ---------------------------------------------------------------------------


class RunOrchestratorRequest(BaseModel):
    """Body for POST /api/run-orchestrator (Phase 1.4 free-form payload)."""

    payload: dict[str, Any] = Field(
        description="Free-form JSON forwarded to the generated "
        "orchestrator's handle_request function."
    )
    role: str | None = Field(
        default=None,
        description="Optional role override; falls back to user preference.",
    )


def _load_generated_orchestrator(user: UserContext, role_id: str):
    """Import the per-user, per-role generated `orchestrator.py` dynamically.

    Returns the module's `handle_request` callable, or raises HTTPException
    if no orchestrator has been generated yet.
    """
    target = orchestrator_path(user, role_id, "orchestrator.py")
    if not target.exists():
        raise HTTPException(
            404,
            f"No orchestrator generated yet for role {role_id!r}. "
            "Pick a recommendation and click 'Build orchestrator' first.",
        )
    spec = importlib.util.spec_from_file_location(
        f"_runtime_orch_{user.user_id}_{role_id}", target
    )
    if spec is None or spec.loader is None:
        raise HTTPException(500, "could not load generated orchestrator")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            502,
            f"Generated orchestrator failed to import: {type(exc).__name__}: {exc}",
        ) from exc
    handler = getattr(module, "handle_request", None)
    if handler is None or not inspect.iscoroutinefunction(handler):
        raise HTTPException(
            500,
            "Generated orchestrator does not expose async `handle_request`.",
        )
    return handler


@app.post("/api/run-orchestrator")
async def run_orchestrator(req: RunOrchestratorRequest) -> dict[str, Any]:
    """Execute one request through the user's generated orchestrator.

    Credentials from the user's vault are injected into the process
    environment for the duration of the call. The generated code reads
    them via `core.credentials.runtime_credentials()`.
    """
    user = _current_user()
    role_id = req.role or get_preferences(user).selected_role
    store = LocalFileCredentialStore(user)
    handler = _load_generated_orchestrator(user, role_id)

    with credentials_in_env(store):
        try:
            response = await handler(req.payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("run_orchestrator failed")
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Orchestrator run failed: {type(exc).__name__}: {exc}. "
                    "Check the backend terminal for the full traceback."
                ),
            ) from exc
    if not isinstance(response, dict):
        raise HTTPException(
            500,
            f"handle_request returned {type(response).__name__}, expected dict.",
        )
    return response
