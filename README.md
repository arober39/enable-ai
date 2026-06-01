# Enable AI

Enable AI is an agent system that takes a department's tool stack as input and produces an AI enablement plan for that department — then implements it. Each department's plan recommends which existing tools have AI worth using, which gaps to fill with custom AI, which tools to consolidate, and how to orchestrate the resulting stack behind a single Operations Agent that the team can interact with as a unified surface.

This repo is the reference implementation. It operates on **Serenia & Co.**, a fictional events and venues business, and walks through how an AI enablement system would actually work department by department.

It also serves as the demo asset for LaunchDarkly's [tutorials series](https://launchdarkly.com/docs/tutorials) on operating AI agents in production. Each tutorial lives on its own branch, demonstrating a specific operational concern — multi-signal guardrails, threshold calibration, fail-safe rollout design — against a subagent that Enable AI has already generated.

## Why this exists

Every team building production AI agents eventually needs the same set of capabilities: rollout safety, observability, evaluation, guardrails, fallback behavior, cost controls. Most teams build these incrementally, function by function, and the architecture drifts as they go.

Enable AI demonstrates the alternative: a coordinator-orchestrated system that knows what AI-enabled looks like in each department and generates the runtime infrastructure to support it, with LaunchDarkly as the control layer for everything that happens after the system ships.

## What's in v1

The first release contains:

- The **Coordinator** — routes inbound enablement requests to specialized subagents
- The **Support Enablement Agent** — Enable AI's first department specialist; reads Serenia's support stack, produces an enablement plan, generates the support orchestrator
- The **Support Orchestrator** — the deployed AI agent that handles customer inquiries at Serenia, integrating Intercom, Zendesk, Slack, and HubSpot
- The shared infrastructure: hooks, schemas, tool and MCP registries, observability scaffolding, the `.claude/` configuration

Future releases extend Enable AI to additional departments — Marketing, Engineering, Legal, Finance, HR, Sales — each through the same coordinator-and-subagent pattern.

## Getting started

```bash
git clone https://github.com/[org]/enable-ai
cd enable-ai
make install
```

Set the one required env var:

```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY (or OPENAI_API_KEY)
```

Run the coordinator against Serenia's support stack:

```bash
python -m coordinator "Enable AI for customer support"
```

The Coordinator delegates to the Support Enablement Agent, which produces a structured enablement plan and generates a runnable support orchestrator under `orchestrators/support/`.

## Demo mode and credentials

Enable AI runs against realistic stubs by default. The generated orchestrators integrate with real SaaS tools (Intercom, Zendesk, Slack, HubSpot, and so on for future departments), but if the corresponding API credentials aren't set, the integrations fall back to stub implementations that return synthetic responses with the same shape as the real APIs.

This means you can clone the repo, run everything end-to-end, and see realistic behavior without needing accounts for the tools Enable AI integrates with. When you want real interaction, set the relevant env vars and the same code paths use the real APIs.

All credentials are environment variables. The repo never reads from anywhere else. See `.env.example` for the full list.

## The tutorial series

Each LaunchDarkly tutorial that uses Enable AI lives on its own branch:

| Branch | Tutorial |
|---|---|
| `tutorial-01-multi-signal-guardrails` | Building multi-signal guardrails for self-healing AI systems |
| `tutorial-02-threshold-calibration` *(planned)* | Calibrating guarded rollout thresholds against historical traffic |
| `tutorial-03-fail-safely` *(planned)* | Designing AI Config rollouts that fail safely |

Each branch represents the repo's state at the *start* of the tutorial — the orchestrator built, the AI Config provisioned, the metrics ready to attach. Cloning the branch puts you exactly where the tutorial begins. The tutorial's specific code lives in `tutorials/<tutorial-name>/`.

The `main` branch always holds the most recent state, which incorporates all completed tutorials.

## Architecture

Enable AI follows a hub-and-spoke pattern. One Coordinator agent receives all inbound requests and routes them to specialized Enablement Subagents (Support is the only one in v1). Subagents have isolated context — they don't inherit the Coordinator's conversation history, and they only communicate back through structured outputs the Coordinator aggregates.

A few patterns hold throughout:

- **Hooks for deterministic enforcement.** Critical rules — credential scope, write boundaries, demo-mode safety — are implemented as `PreToolUse` and `PostToolUse` hooks. Prompts give probabilistic compliance; hooks give guarantees.
- **Structured outputs everywhere.** Every plan, recommendation, and orchestrator artifact is a Pydantic model with a JSON Schema attached to the agent's `tool_use`. No free-text outputs for structured data.
- **MCP-first integration.** Generated orchestrators use existing MCP servers when they exist (official or community), build minimal custom MCP servers only when no usable one is available, and fall back to direct API integration only when MCP isn't viable.
- **Scoped tools.** Each subagent receives only the tools it needs for its function. The Support Enablement Agent doesn't have legal-document tools, and vice versa.
- **Scratchpad files for long-running state.** Subagent investigations that span multiple steps persist findings to `agent-state/<agent>-scratchpad.md` so context isn't lost between turns.

The `.claude/` directory documents these conventions in detail. Path-scoped rules in `.claude/rules/` apply only when Claude is editing the relevant code paths.

## Repository layout

```
enable-ai/
├── coordinator/              # The Coordinator agent and its hooks
├── enablement_agents/        # Department specialists (Support in v1)
├── orchestrators/            # Generated orchestrators (one per enabled department)
├── stacks/                   # Each department's declared tool stack
├── tools/                    # Knowledge base of SaaS tools and their AI capabilities
├── mcp_registry/             # Catalog of known MCP servers per tool
├── data/                     # Synthetic data per department (customers, tickets, etc.)
├── scripts/                  # Setup, replay, and operational scripts
├── tutorials/                # Tutorial-specific code (populated by tutorial branches)
├── tests/
├── .claude/                  # Claude Code configuration, rules, and skills
└── SERENIA.md                # The fictional company's world bible
```

## Serenia & Co.

Serenia & Co. is a mid-sized events and venues company. They host weddings, corporate offsites, conferences, and private parties at three venues. They have departments you'd expect at a business that size: sales, customer support, vendor operations, HR, finance, legal, marketing, and a small engineering team that runs their booking platform.

For the full fictional-company context — org chart, named personas, brand voice — see [`SERENIA.md`](./SERENIA.md).

## Contributing

Enable AI is the demo asset for LaunchDarkly's tutorial series; structural changes happen through tutorial branches. If you're following a tutorial and find an issue with the code, please open an issue against the relevant branch.
