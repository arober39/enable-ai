# Agent Architect

The demo UI for deciding what agent to build. It starts from the work someone actually does, classifies what they should supervise, and writes a blueprint that feeds OpenAI Agents SDK, Claude, LangGraph, n8n, Copilot Studio, Zapier, or custom MCP.

The app is two tiers:

- **Backend** (`ui/api/`): FastAPI hosting the agent. Returns the catalog and runs `produce_plan`.
- **Frontend** (`ui/web/`): Next.js 15 + TypeScript + Tailwind. Picks tools, renders the plan.

In live mode the backend can run behind a LaunchDarkly AgentControl config, record generation metrics, and score each blueprint with attached judges. The setup for that is below.

## Prerequisites

- Python 3.12+ with the project's `.venv` populated (`make install`)
- Node.js 18+ and npm

## Setup (once)

```bash
# One-shot: installs Python (fastapi + uvicorn), Node.js deps, and Playwright's chromium browser
make ui-install
```

Or step-by-step:

```bash
# 1. Python backend deps
.venv/bin/pip install -e ".[ui]"

# 2. Node.js frontend deps
cd ui/web
npm install

# 3. Playwright chromium (~150MB) for smoke tests — skip if you only want the dev server
npx playwright install chromium
cd ../..
```

## Run

The UI needs **two terminals** — the FastAPI backend and the Next.js dev server.

### Terminal 1 — backend (port 8000)

```bash
make ui-backend
# or directly:
# .venv/bin/uvicorn ui.api.server:app --reload --port 8000
```

### Terminal 2 — frontend (port 3000)

```bash
make ui-frontend
# or directly:
# cd ui/web && npm run dev
```

Then open <http://localhost:3000>.

## Modes

The backend honors the same `ENABLE_AI_DEMO_MODE` env var as the rest of the system.

| Mode | When | What happens |
|---|---|---|
| **Demo** (default) | `ENABLE_AI_DEMO_MODE=true` *or* `ANTHROPIC_API_KEY` unset | The backend returns a synthetic catalog-driven plan. No LLM cost. The UI labels the plan `demo mode`. Useful for testing the surface itself. |
| **Live** | `ENABLE_AI_DEMO_MODE=false` AND `ANTHROPIC_API_KEY` set | The backend calls Anthropic's API directly via `anthropic.AsyncAnthropic()`, using Pydantic-generated JSON Schema as a `tool_use` input schema. When `LAUNCHDARKLY_SDK_KEY` is also set, it fetches completion-mode AI Config `agent-architect-config` (or `AGENT_ARCHITECT_AI_CONFIG_KEY`) and records generation metrics through the LaunchDarkly AI SDK tracker so attached online judges can score outputs. |

### LaunchDarkly online eval setup

Use this when you want Monitoring rows from real Architect runs:

0. Install judge-provider packages in the same Python env as the backend:
   - `launchdarkly-server-sdk-ai-langchain==0.8.0`
   - `langchain-anthropic==1.5.1`
   - Keep project pin `anthropic==0.101.0` (do not upgrade to 0.120+).
1. Set env vars before starting the backend:
   - `ENABLE_AI_DEMO_MODE=false`
   - `ANTHROPIC_API_KEY=...`
   - `LAUNCHDARKLY_SDK_KEY=...`
2. In LaunchDarkly, create/use completion-mode AgentControl config key:
   - `agent-architect-config` (or set `AGENT_ARCHITECT_AI_CONFIG_KEY` to your override)
3. Create a custom judge in LaunchDarkly and attach it to the config variation. Any judge works; `blueprint-fixes-friction-constraints` is the one used so far. Set sampling to **100%** for demos.
4. Run the UI flow (role + tools + friction → Run). A few live runs should appear in Monitoring within a couple of minutes. Judge scores lag the call by a minute or two.
   - The friction field accepts up to 8000 characters for longer real-world context.
5. To add a challenger model, create a second variation on the same config with a different model, attach the same judge, and change the default rule under a guarded rollout with the judge metric as a regression metric. The backend takes the model from whichever variation is served; nothing in the repo changes.

If `LAUNCHDARKLY_SDK_KEY` is missing, live mode still returns a blueprint and logs that eval tracking was skipped.
If judge provider packages are missing, the run still returns a blueprint and logs a warning that judge evaluation was skipped.

### Architectural deviation — UI live mode does NOT use `claude-agent-sdk`

The rest of the system uses `claude-agent-sdk==0.1.81` for agent execution. The UI's live mode does **not** — it calls the Anthropic Python SDK directly (see `ui/api/live_runner.py`). Reason:

> The SDK ships a bundled `claude` CLI binary that, on some setups, returns a contradictory `result` message (`is_error: true` with `subtype: "success"`). The SDK surfaces this as `"Claude Code returned an error result: success"` — actionable for nobody. We hit it reliably from FastAPI on macOS. Since the UI's value is "let me see a plan come back," we don't need Task delegation / hooks / MCP for this path. The direct API call with Pydantic-derived `tool_use` schema gives us the same structured output with no bundled-binary dependency.

What still uses claude-agent-sdk:
- The CLI: `python -m coordinator "..."`
- Live tests (`@pytest.mark.live`)
- The Coordinator's `run_coordinator` and the role agents' `produce_plan`

If you debug the SDK bundled-CLI issue, the UI's live path can be swapped back to the routed Coordinator flow with a one-import change in `ui/api/server.py`. The deviation is scoped — it only affects the UI path.

Set vars before launching the backend:

```bash
ENABLE_AI_DEMO_MODE=false ANTHROPIC_API_KEY=sk-... make ui-backend
```

## Smoke tests

A Playwright e2e suite under `ui/web/e2e/` covers the happy path in demo mode:

```bash
make ui-test-smoke
# or directly:
# cd ui/web && npx playwright test
```

The Playwright config boots **both** the FastAPI backend (on :8000) and the Next.js dev server (on :3000) before running — **do not** start them manually first or you'll get port conflicts. Demo mode is forced via env var so the suite never hits a live LLM.

What it covers:

- Home page loads with header, catalog (4 tools), and demo-mode health indicator.
- Default pre-selection (Intercom + Zendesk) renders.
- Run button completes the round-trip and renders all four plan sections (summary, capability findings, recommendations, orchestrator PR plan).
- Run button is disabled with zero tools selected.
- Selecting HubSpot only yields the expected `augment_with_custom_ai` recommendation (validates the MCP-stub heuristic).

What it does **not** cover:

- Live-mode runs (gated behind a real LLM; not part of smoke).
- The synthetic plan builder's full output shape (covered by Python unit tests in `tests/`).
- Production builds (`npm run build`).

## What you can test (manually)

- **Catalog rendering**: the four tools render with native-AI / MCP origin badges.
- **Plan shape**: capability findings, recommendations, orchestrator-PR plan all rendered with status/kind/effort tags.
- **Empty submission**: button is disabled with zero tools selected.
- **Error path**: kill the backend mid-run — the UI surfaces the error in a banner.
- **HubSpot MCP-stub case**: select HubSpot, see `MCP stub` badge and an `augment_with_custom_ai` recommendation about generating the stub.
- **Live LLM behavior** (when configured): the live plan's `summary` text reads differently from the synthetic one — the synthetic one starts with `[DEMO/SYNTHETIC]`.

## What's NOT covered

- No tests for the Next.js side. The Python backend's logic shares all the same unit tests as the rest of the system (the synthetic builder and live runner reuse code that's covered in `tests/`).
- No production build / deployment. `npm run build` works but the FastAPI backend assumes localhost. Real deploy is future work.
- No auth, rate limit, or input validation beyond the catalog whitelist. Local dev only.

## Architecture

```
┌─────────────────────────┐         ┌───────────────────────────────┐
│ Next.js dev (port 3000) │  HTTP   │ FastAPI backend (port 8000)   │
│ ├ RolePicker            │ ──────→ │ ├ GET  /api/tools, /api/roles │
│ ├ ToolPicker            │         │ ├ POST /api/enablement        │
│ ├ WorkIntelligence      │         │ └ ui/api/live_runner.py       │
│ ├ AgentBlueprintView    │         └─────────────┬─────────────────┘
│ └ GrokbotHandoff        │                       │
└─────────────────────────┘                       ▼
                                    ┌─────────────────────────────┐
                                    │ Agent Architect             │
                                    │ (blueprint, demo or live)   │
                                    │ live: AgentControl config,  │
                                    │ AI SDK tracker, judges      │
                                    └─────────────────────────────┘
```

The Next.js dev server rewrites `/api/*` to `http://127.0.0.1:8000/api/*` (see `next.config.js`) so the frontend uses same-origin requests.

## Files

```
ui/
├── README.md                          # this file
├── api/
│   ├── __init__.py
│   ├── server.py                      # FastAPI app + routes
│   ├── live_runner.py                 # live mode: Anthropic call, AgentControl config, tracker, judges
│   ├── synthetic.py                   # demo-mode plan builder
│   ├── jobs.py
│   └── speech.py
└── web/
    ├── package.json
    ├── tsconfig.json
    ├── next.config.js                 # /api rewrite to FastAPI
    ├── tailwind.config.ts
    ├── postcss.config.js
    ├── playwright.config.ts           # e2e config (boots both servers)
    ├── e2e/                           # Playwright smoke, selection-step, handoff-submit specs
    └── app/
        ├── layout.tsx
        ├── page.tsx                   # the seven-step flow
        ├── settings/page.tsx
        ├── globals.css
        ├── components/                # RolePicker, ToolPicker, WorkIntelligence, PlanDisplay,
        │                              # AgentBlueprintView, BuildOrchestrator, GrokbotHandoff, ...
        └── lib/                       # api.ts, types.ts, homeSession.ts, ...
```
