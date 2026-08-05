# Enable AI

Enable AI is a diagnosis-first AI enablement platform: it audits a team's tool stack, recommends where AI genuinely fits, executes the rollout (plan-as-data workflows on a fixed interpreter, native-AI setup guides, consolidation plans), and measures whether the recommendation paid off. It is developed through a software factory and built in public. Demo data comes from a fictional company (Serenia & Co.).

## Architectural principles

The architectural principles that govern every decision are defined in `@./.claude/rules/orchestrator-conventions.md`. They are not optional.

## Fictional company context

Serenia & Co. is the fictional company this system operates on. See `@./SERENIA.md` for the org chart, customer personas, recurring scenarios, and brand voice.

## Direction and build state

The product vision, factory milestones, and build-in-public program live in `@./VISION.md`. Future Claude Code sessions resuming this work should read it first. `BUILD_PLAN.md` is the historical v1 spec — do not resume its phases.

## Build and run

- `make install` — create `.venv` and install pinned deps
- `make setup` — provision LaunchDarkly AI Configs (no-op in demo mode)
- `make test` — run deterministic tests (no LLM calls)
- `make test-live` — include `@pytest.mark.live` tests (requires `ANTHROPIC_API_KEY`)
- `make replay-traffic VARIATION=<name>` — drive synthetic traffic through the support orchestrator
- `make lint` / `make typecheck` — code health
