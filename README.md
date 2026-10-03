# Enable AI

Enable AI is a diagnosis-first AI enablement platform. It audits a team's actual tool stack, tells them where AI fits, builds the chosen recommendation on a runtime they can trust, and measures whether it paid off. The loop is Diagnose, Recommend, Execute, Measure.

The repo operates on **Serenia & Co.**, a fictional events and venues business, so every demo runs on synthetic data with zero real-customer risk. See [`SERENIA.md`](./SERENIA.md) for the world bible.

## What the app does

The main surface is **Agent Architect**, a UI for deciding what agent to build and how a person would supervise it. One run walks seven steps:

1. **Work intelligence.** Pick a role. Seeded roles ship in the repo, and any other role can be researched at runtime from its title. The app lists the tasks that role usually does and lets the person confirm the ones they actually do or add their own.
2. **Tools and friction.** Pick the tools the person uses, from the seeded catalog or researched by name, and describe the friction in their week in plain text.
3. **Run Agent Architect.** The agent reads the role, tools, tasks, and friction and compiles a plan grounded in what the selected tools can do together.
4. **Agent Blueprint.** Each task is classified as automate, assist, agentic, or human, with the signals behind the call, the human-in-the-loop shape, and the supervision shift. The blueprint names what the agent would own, what the person keeps, and which build targets fit. The targets are OpenAI Agents SDK, Claude, LangGraph, n8n, Copilot Studio, Zapier, and a custom MCP server, and the blueprint marks which ones it recommends for this role and stack, with a reason for each.
5. **Pick one recommendation.** The plan's recommendations come in four kinds, use a native AI feature already paid for, augment with custom AI, consolidate overlapping tools, or orchestrate a cross-tool workflow. The person picks one or writes their own. The rest are saved for later.
6. **Ask Jev to place it.** Jev, TypeSafe's typed decision model, decides whether the blueprint belongs on a new bot or an existing one. Without a key, a local heuristic answers and is labeled as such.
7. **Build from the Agent Blueprint.** The app writes a copyable workflow prompt from the blueprint and the chosen recommendation. You paste it wherever you want to create the agent, whether that is Grok Bot, one of the build targets from step 4, or any other agent builder. The app never creates or edits agents itself. An optional webhook can also receive the same text.

Orchestration recommendations can also be built and run inside the app. They become validated workflow JSON executed by a fixed interpreter, and each run is recorded as an outcome with its status, duration, and per-step trace. LLM output never executes as code.

The original CLI path is still available. A Coordinator agent routes a request such as "Enable AI for customer support" to a role-specific enablement agent that produces a plan and, on request, generates a runnable orchestrator under `orchestrators/`.

## Modes

Enable AI runs in demo mode by default. Demo mode makes no external calls, returns catalog-driven synthetic plans, and swaps every tool adapter for a stub that returns the same shape as the real API and tags itself as a stub. You can clone the repo and run everything end to end without accounts for any integrated tool.

Live mode calls Anthropic directly. Set `ENABLE_AI_DEMO_MODE=false` and `ANTHROPIC_API_KEY`. The planner defaults to Claude Opus 5.5 and can be overridden with `ENABLEMENT_AGENT_MODEL`.

## LaunchDarkly integration

When `LAUNCHDARKLY_SDK_KEY` is set in live mode, Agent Architect fetches its model and any system prompt from a completion-mode AgentControl config named `agent-architect-config`, or the key set in `AGENT_ARCHITECT_AI_CONFIG_KEY`. Each run is wrapped in the AI SDK tracker, so duration, token counts, and success land in LaunchDarkly as metrics. Any judges attached to the served variation are run against the plan the agent produced, and their scores are recorded. Judge evaluation requires the provider packages:

```bash
.venv/bin/pip install launchdarkly-server-sdk-ai-langchain==0.8.0 langchain-anthropic==1.5.1
```

Keep the project's `anthropic==0.101.0` pin. If the SDK key or the provider packages are missing, the app still returns a plan and logs that tracking or judging was skipped.

Workflow runs also emit `enablement.workflow_run` and `enablement.workflow_error` events when the SDK key is present.

## Run it

Install Python dependencies, then the UI:

```bash
git clone https://github.com/[org]/enable-ai
cd enable-ai
make install
make ui-install
```

Copy the env file and set what you need. Everything is optional in demo mode.

```bash
cp .env.example .env
```

Start the two halves of the UI in separate terminals and open `http://localhost:3000`:

```bash
make ui-backend     # FastAPI on :8000
make ui-frontend    # Next.js on :3000
```

Run the CLI path:

```bash
python -m coordinator "Enable AI for customer support"
```

Other targets:

```bash
make test           # deterministic suite, no LLM calls
make test-live      # adds tests that call Anthropic (needs ANTHROPIC_API_KEY)
make ui-test-smoke  # Playwright smoke tests in demo mode
make lint
make typecheck
```

UI setup details, including the LaunchDarkly steps, are in [`ui/README.md`](./ui/README.md).

## Credentials

All credentials are environment variables, and `.env.example` is the single source of truth for their names. The repo never reads credentials from anywhere else. Tool credentials for generated orchestrators, Jev, the Grok Bot gateway, and the handoff webhook are each optional, and the corresponding feature degrades to a stub or a labeled fallback when they are unset.

## Repository layout

```
enable-ai/
├── core/                     # Agent Architect, roles, tool catalog, credentials, outcomes, Jev, Grok Bot handoff
├── ui/                       # FastAPI backend (api/) and Next.js frontend (web/)
├── coordinator/              # The Coordinator agent and its hooks (CLI path)
├── enablement_agents/        # Role agents, domain knowledge, generator pipelines, workflow interpreter
├── orchestrators/            # Generated orchestrators
├── stacks/                   # Declared tool stacks per role
├── tools/                    # Knowledge base of SaaS tools and their AI capabilities
├── mcp_registry/             # Catalog of known MCP servers per tool
├── data/                     # Synthetic Serenia data
├── tests/
├── .claude/                  # Claude Code configuration, rules, and skills
└── SERENIA.md                # The fictional company's world bible
```

## Serenia & Co.

Serenia & Co. is a mid-sized events and venues company. They host weddings, corporate offsites, conferences, and private parties at three venues and have the departments you'd expect at that size, including sales, customer support, vendor operations, HR, finance, legal, marketing, and a small engineering team that runs their booking platform. The org chart, named personas, recurring scenarios, and brand voice are in [`SERENIA.md`](./SERENIA.md).
