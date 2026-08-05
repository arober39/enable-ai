# Enable AI: Vision

*This document supersedes `BUILD_PLAN.md` (now historical) as the read-first source of truth for where this project is going. Last revised: 2026-08-05.*

## What Enable AI is

Enable AI is a **diagnosis-first AI enablement platform**. It audits a team's actual tool stack, tells them where AI genuinely fits, executes the rollout on a runtime they can trust, and proves whether it worked.

The spine of the product is a loop:

**Diagnose → Recommend → Execute → Measure**

1. **Diagnose** — a user picks their role (support, marketing, devrel, customer success, …) and adds the everyday tools they use. LLM-driven research turns free-form tool names into structured capability cards: native AI features, API surface, MCP availability.
2. **Recommend** — an enablement agent compares the stack against role-specific domain knowledge and produces recommendations of four kinds: use a native AI feature you already pay for, augment with custom AI, consolidate redundant tools, or orchestrate a cross-tool workflow. The user picks one; the rest are saved for later.
3. **Execute** — the platform builds the chosen recommendation. Orchestration recommendations become **plan-as-data workflows**: validated `WorkflowDefinition` JSON executed by a fixed, reviewed interpreter — LLM output never executes as code. Native-AI recommendations become step-by-step setup artifacts; consolidations become migration plans.
4. **Measure** — the loop nobody else closes: did the recommendation pay off? Adoption, run success, escalation and error rates per recommendation, with the ability to roll back what isn't working.

**Who it's for:** the person who owns "AI rollout" in a company — the ops/IT/AI-enablement lead — not "anyone in a company." The one-chat-that-executes-tasks surface is the last mile of one artifact type, not the product.

## Architectural commitments

These carry over from the phase-1 pivot and remain non-negotiable:

- **Plan as data, not code.** Per-user artifacts are validated JSON interpreted by a platform-owned runtime (`enablement_agents/workflow_interpreter.py`). Generation pipelines are schema-forced and reject hallucinated tool references.
- **The four multi-tenancy abstractions** (`core/`): a `Credentials` provider (no direct `os.environ` reads), `UserContext` threaded through every endpoint, per-user state directory layout, and UI-managed credential storage that never writes to `.env`.
- **Adapters degrade honestly.** Every tool adapter returns identical shapes in real and stub mode and tags which one ran.
- **Roles and tools are data.** Adding a role is dropping a directory; tools resolve through one catalog whether seeded or LLM-researched.

## LaunchDarkly as the control plane

Every LLM surface becomes an AI Config: per-role plan-production prompts, each generator pipeline's emit prompt, tool research, and workflow `llm` steps. Judges score emitted artifacts. Custom metrics track build quality (validation-rejection rate, cost per build) and — the flagship — recommendation outcomes. Prompt and pipeline changes ship behind guarded rollouts.

## The software factory that builds this

Enable AI is developed through a **software factory**: the same input → governed pipeline → validated artifact → measurement loop, one altitude up.

- **Work orders** — structured units of work (scope, acceptance criteria, definition of done) as the standardized input. Three kinds: `feature`, `fix`, and `experiment` (try a new tool/technology, evaluate against gates, keep or revert).
- **Assembly line** — coding agents pick up work orders in isolated worktrees and produce PRs.
- **Gates** — every PR, human- or agent-authored, passes identical checks: tests, lint, typecheck, plus spec-conformance and standards review agents.
- **Provenance** — every merged change traceable to its work order, prompts, model versions, and gate results.
- **Same control plane** — factory agents' prompts and models are AI Configs; factory metrics (cycle time, gate-failure rate, cost per change) are LD metrics. The factory dogfoods what the product sells.

### Milestones

| # | Deliverable | Status |
|---|---|---|
| 0 | Baseline: coherent commits, public repo, this document | in progress |
| 1 | Gates: CI + review agents as required checks | — |
| 2 | First agent-executed work order through the full loop | — |
| 3 | LD control plane on factory agents and product pipelines | — |
| 4+ | Product repositioning via work orders: diagnose-first UX, outcome-measurement loop, provenance on emitted workflows | — |

## Built in public

This is a long-term build-in-public project. The factory's exhaust — work orders, gate results, provenance, what broke — is the content. Every shipped work order gets at least a short write-up; milestones get the full treatment (live build, short-form recaps, tutorial); guides and conference talks are compiled from shipped episodes, not written speculatively. `experiment` work orders are the standing invitation: any new developer tool can be slotted into the factory, measured against the gates, and written about honestly.

## Historical context

- `BUILD_PLAN.md` — the original v1 spec (Coordinator + Support Enablement Agent + tutorial-aligned orchestrator). Complete on disk; kept as history.
- `SERENIA.md` — the fictional company. Still the demo dataset: it lets everything be shown publicly with zero real-customer risk.
