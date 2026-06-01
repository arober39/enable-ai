# Enable AI — Test UI

A minimal two-tier app for hands-on testing of the Support Enablement Agent:

- **Backend** (`ui/api/`): FastAPI hosting the agent. Returns the catalog and runs `produce_plan`.
- **Frontend** (`ui/web/`): Next.js 15 + TypeScript + Tailwind. Picks tools, renders the plan.

This is **scope expansion beyond `BUILD_PLAN.md`** — the v1 plan put the Next.js frontend out-of-scope. Treat the UI as a development convenience, not part of the v1 deliverable. The tests in `tests/` cover the v1 contract; this UI is for human-in-the-loop testing.

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
| **Live** | `ENABLE_AI_DEMO_MODE=false` AND `ANTHROPIC_API_KEY` set | The backend calls Anthropic's API directly via `anthropic.AsyncAnthropic()`, using Pydantic-generated JSON Schema as a `tool_use` input schema. Each run costs a few cents in LLM tokens. |

### Architectural deviation — UI live mode does NOT use `claude-agent-sdk`

The rest of the system uses `claude-agent-sdk==0.1.81` for agent execution. The UI's live mode does **not** — it calls the Anthropic Python SDK directly (see `ui/api/live_runner.py`). Reason:

> The SDK ships a bundled `claude` CLI binary that, on some setups, returns a contradictory `result` message (`is_error: true` with `subtype: "success"`). The SDK surfaces this as `"Claude Code returned an error result: success"` — actionable for nobody. We hit it reliably from FastAPI on macOS. Since the UI's value is "let me see a plan come back," we don't need Task delegation / hooks / MCP for this path. The direct API call with Pydantic-derived `tool_use` schema gives us the same structured output with no bundled-binary dependency.

What still uses claude-agent-sdk:
- The CLI: `python -m coordinator "..."`
- Phase 7 live tests (`@pytest.mark.live`)
- The Coordinator's `run_coordinator` and the Support agent's `produce_plan`

If you debug the SDK bundled-CLI issue, the UI's live path can be swapped back to the routed Coordinator/Support flow with a one-import change in `ui/api/server.py`. The deviation is scoped — it only affects the UI demo path.

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
│ ├ ToolSelector          │ ──────→ │ ├ GET  /api/tools             │
│ └ PlanDisplay           │         │ ├ POST /api/enablement        │
└─────────────────────────┘         │ └ Calls SupportEnablementAgent│
                                    └─────────────┬─────────────────┘
                                                  │
                                                  ▼
                                    ┌─────────────────────────────┐
                                    │ Support Enablement Agent    │
                                    │ (real LLM or synthetic stub)│
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
│   └── synthetic.py                   # demo-mode plan builder
└── web/
    ├── package.json
    ├── tsconfig.json
    ├── next.config.js                 # /api rewrite to FastAPI
    ├── tailwind.config.ts
    ├── postcss.config.js
    ├── playwright.config.ts           # e2e config (boots both servers)
    ├── e2e/
    │   └── smoke.spec.ts              # Playwright smoke tests
    └── app/
        ├── layout.tsx
        ├── page.tsx                   # main UI page
        ├── globals.css
        ├── components/
        │   ├── ToolSelector.tsx
        │   └── PlanDisplay.tsx
        └── lib/
            ├── api.ts
            └── types.ts
```
