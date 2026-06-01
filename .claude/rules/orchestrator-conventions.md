---
paths: ["coordinator/**/*.py", "enablement_agents/**/*.py"]
---

# Architectural principles (non-optional)

These principles govern every decision in `coordinator/` and `enablement_agents/`. They are quoted from the build plan and are not optional.

## Hub-and-spoke orchestration

One **Coordinator** agent receives all inbound requests and routes to specialized **Enablement Subagents** (Support is the only one in v1). The Coordinator owns:

- Intent classification and request decomposition
- Subagent selection and delegation via the `Task` tool
- Error handling and structured propagation
- Result aggregation and final response synthesis

Subagents have isolated context. They do not inherit the Coordinator's conversation history. All context the subagent needs must be **explicitly passed** in the `Task` prompt. All communication between subagents flows through the Coordinator — never directly.

## Deterministic enforcement via hooks

Anywhere a rule must be **guaranteed** — financial limits, write boundaries, destructive operation gates, credential scope — the rule is implemented as a `PreToolUse` or `PostToolUse` hook, **not** as a prompt instruction. Prompt instructions give probabilistic compliance; hooks give deterministic guarantees.

Use hooks for:
- Blocking writes to anything other than the agent's working directory
- Refusing tool calls that would touch real production LaunchDarkly resources without explicit confirmation
- Normalizing tool outputs into consistent schemas

## Structured outputs with JSON Schema

Every agent that produces a plan, recommendation, or report uses `tool_use` with a strict JSON Schema. No free-text outputs for structured data. Required vs. nullable fields are deliberate. Enum fields include `"unclear"` or `"other"` plus a `detail` string for extensibility.

## Tool design with least privilege

Each subagent receives only the tools it needs. The Support Enablement Agent does not have legal-document tools. The Coordinator has `Task` plus a small set of cross-role utilities. Tool descriptions are explicit about input formats, expected outputs, edge cases, and when to use the tool vs. similar alternatives.

## MCP-first integration

Where an external tool has an official or community MCP server, **use it**. Build a minimal custom MCP server only when no usable existing one exists. Document the choice in the enablement plan output (`mcp_servers_used` vs. `mcp_servers_to_generate`).

## Credentials via environment variables

No credentials hardcoded anywhere. All external tool credentials are read from environment variables defined in the root `.env.example`. The orchestrator detects missing credentials and degrades to realistic stubs. **`.env.example` is the single source of truth for credential conventions** — do not invent new variables in later phases.

## Context management

Long-running subagent investigations use scratchpad files (`agent-state/<agent-name>-scratchpad.md`) to preserve findings across context boundaries. Subagent context budgets are constrained — pass minimal context, demand structured output, restrict toolsets.
