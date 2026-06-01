# Coordinator conventions

The Coordinator is the hub. It receives all inbound requests, classifies intent, decomposes into subtasks, and delegates to Enablement Subagents via the `Task` tool. It never produces orchestrator code directly — that work happens inside the subagents in isolated context.

## Task tool usage

When invoking a subagent via `Task`, the prompt must include:
- The path to the relevant `stacks/<department>.yaml` file
- The relevant `tools/*.yaml` and `mcp_registry/*.yaml` entries the subagent will need
- Any prior context the subagent needs (the subagent does **not** inherit the Coordinator's conversation history)

Subagents return structured outputs only. The Coordinator parses the structured result and either aggregates with other subagent results, or returns it to the caller.

## Hook registration

All three hooks (`enforce_credentials`, `enforce_writes`, `normalize_responses`) are registered in `agent.py` at `AgentDefinition` instantiation time. Do not bypass them with prompt instructions — that defeats the determinism guarantee.

## Structured outputs

The Coordinator's final answer is always an `EnablementPlan` (see `schemas.py`). The Coordinator never returns free-text reports.

## Pointer

The architectural principles that govern this directory are in `@../.claude/rules/orchestrator-conventions.md`.
