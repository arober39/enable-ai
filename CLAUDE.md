# Enable AI

Enable AI is an AI enablement orchestration system that operates on a fictional company (Serenia & Co.). A hub-and-spoke Coordinator agent routes inbound enablement requests to specialized Enablement Subagents, which produce structured plans and generate runnable per-department orchestrators. The v1 deliverable is the Coordinator plus the Support Enablement Agent end-to-end, plus the support orchestrator the agent generates.

## Architectural principles

The architectural principles that govern every decision are defined in `@./.claude/rules/orchestrator-conventions.md`. They are not optional.

## Fictional company context

Serenia & Co. is the fictional company this system operates on. See `@./SERENIA.md` for the org chart, customer personas, recurring scenarios, and brand voice.

## In-progress build state

The full build plan, phase-by-phase, lives in `@./BUILD_PLAN.md`. Future Claude Code sessions resuming this work should read it first.

## Build and run

- `make install` — create `.venv` and install pinned deps
- `make setup` — provision LaunchDarkly AI Configs (no-op in demo mode)
- `make test` — run deterministic tests (no LLM calls)
- `make test-live` — include `@pytest.mark.live` tests (requires `ANTHROPIC_API_KEY`)
- `make replay-traffic VARIATION=<name>` — drive synthetic traffic through the support orchestrator
- `make lint` / `make typecheck` — code health
