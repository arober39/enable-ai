# Claude Code guidance for Enable AI

This file is auto-loaded for every Claude Code session in this repo.

## Coding standards

Standard Python conventions for this repo are defined in `@./rules/coding-style.md`. They apply to every `*.py` file.

## Testing requirements

Testing conventions are defined in `@./rules/testing.md`. The deterministic suite must not make external API or LLM calls; live-LLM tests are gated on `@pytest.mark.live` and `ANTHROPIC_API_KEY`.

## Architectural principles

The non-optional architectural principles for the Coordinator and Enablement Subagents are defined in `@./rules/orchestrator-conventions.md`.

## MCP server conventions

MCP server authoring conventions are defined in `@./rules/mcp-server-conventions.md`.

## Observability

OTel instrumentation conventions are defined in `@./rules/observability.md`.

## SDK version pin

This repo was built and pinned against **`claude-agent-sdk==0.1.81`** (see `pyproject.toml`). The Coordinator and all Enablement Agents are written against this exact version. If you upgrade the SDK, re-run the Phase 1.6 dependency install and re-pin, then audit `coordinator/agent.py` and `enablement_agents/base.py` for breaking changes. Do not assume "the latest" SDK behavior — use the pinned version.

## What to read first

1. `@../BUILD_PLAN.md` — the source of truth for what is built and what is next
2. `@../SERENIA.md` — fictional company context
3. The rule file matching the path you are about to edit
