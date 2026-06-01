---
name: audit-orchestrator
description: Audit a generated orchestrator under orchestrators/<department>/ — structure, configurations, credentials handling. Read-only.
argument-hint: "<department-name>"
context: fork
allowed-tools: ["Read", "Grep", "Glob"]
---

# /audit-orchestrator

Audit a previously generated orchestrator without polluting the calling conversation's context.

## Why `context: fork`

This is an independent investigation. The caller (the user, or a parent agent) does not need the raw file contents and search results in their own context buffer — they only need the audit conclusions. Forking the context ensures the investigation's intermediate state stays isolated.

## Read-only by design

`allowed-tools` is restricted to `Read`, `Grep`, `Glob` — no `Write`, `Edit`, or `Bash`. An audit that wants to fix something must surface the finding and let a separate action (a human, or `/enable-department`) make the change. Audits do not mutate.

## What to check

1. **Structure** — does `orchestrators/<department>/` match the layout in Phase 5.1 of `BUILD_PLAN.md`? (orchestrator.py, agent_definition.py, prompts/system.md, .mcp.json, mcp_servers/, observability.py, .env.example, Makefile, README.md, ai_configs.manifest.yaml)
2. **Credentials** — does `orchestrators/<department>/.env.example` introduce any env var name **not** present in the root `.env.example`? If yes, that is a violation.
3. **Configuration** — does `.mcp.json` reference every tool in the department's stack file? Does `ai_configs.manifest.yaml` look well-formed?
4. **MCP server choices** — for each tool, does the orchestrator use the official MCP server (per `mcp_registry/<tool>.yaml`) or a generated stub? Flag any generated stub where an official server is available.
5. **Observability** — does `observability.py` register the spans named in `.claude/rules/observability.md`?

## Output

Return a structured audit report:

- `passed`: list of checks that passed
- `findings`: list of `{severity: "info"|"warning"|"error", check: str, detail: str, file: str | null}`
- `recommendations`: one-line action items the caller can take

Do not return the raw file contents — only the conclusions.
