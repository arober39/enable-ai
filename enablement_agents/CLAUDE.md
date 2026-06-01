# Enablement Subagent conventions

Every department-specific Enablement Agent inherits from `EnablementAgentBase` in `base.py`. The base class enforces the shared lifecycle: read stack file, gather tool capabilities, consult domain knowledge, produce an `EnablementPlan`, optionally generate the runnable orchestrator.

## Context isolation

Subagents run in isolated context. They do not inherit the Coordinator's conversation history. **Every piece of context a subagent needs must be passed in its `Task` invocation prompt.** Do not assume the subagent can see what the Coordinator already knows.

## Scratchpad usage

For long-running investigations that span multiple tool calls and risk context overflow, write to `agent-state/<agent-name>-scratchpad.md`. Read it back at the start of each significant step. The scratchpad is the durable memory between context-window boundaries; the conversation buffer is not.

## Tool least-privilege

Each subagent declares its `allowed_tools` explicitly. The Support agent does not have legal-document tools. Adding a tool to an agent's `allowed_tools` is a deliberate decision, not a default.

## Domain knowledge

Each agent has a `domain_knowledge.md` file in its directory. This is the agent's reference for what AI capabilities look like in its domain. It is loaded as part of the agent's system prompt context. Keep it tight, accurate, and free of marketing language.

## Pointer

The architectural principles for this directory are in `@../.claude/rules/orchestrator-conventions.md`.
