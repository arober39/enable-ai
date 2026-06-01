---
name: enable-department
description: Invoke the Coordinator to run an enablement pass on a department — produces an EnablementPlan and (optionally) a runnable orchestrator under orchestrators/<department>/.
argument-hint: "<department-name>"
context: main
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Task"]
---

# /enable-department

Run an enablement pass on the named department. This is the primary user entry point to the Coordinator.

## Why `context: main`

This skill is a thin shell wrapper around the Coordinator. The Coordinator itself manages context isolation by spawning Enablement Subagents via the `Task` tool — each subagent runs in its own forked context. Forking again at the skill layer would just add an unnecessary boundary.

## Steps

1. Read `stacks/<department>.yaml` to confirm the department's stack file exists. If it does not, stop and tell the user to create it first.
2. Read `BUILD_PLAN.md`'s Phase 4 section to ground yourself on the current Enablement Agent contract.
3. Invoke `coordinator.run_coordinator(request)` with a request of the form:
   - `"Enable AI for <department>"` to produce a plan only
   - `"Enable AI for <department>, including the runnable orchestrator"` to also generate the orchestrator
4. Parse the returned `EnablementPlan` (and `OrchestratorRunResult`, if generated) and surface to the user:
   - A summary of capability coverage findings
   - Each recommendation with its `kind`, `effort`, and affected tools
   - If an orchestrator was generated, the list of files created and env vars required

## What this skill does NOT do

- It does not hand-edit anything under `orchestrators/<department>/` — that is the Enablement Subagent's job.
- It does not bypass the Coordinator and call an Enablement Agent directly. All inbound enablement requests flow through the Coordinator.
- It does not modify `stacks/`, `tools/`, `mcp_registry/`, or `data/` — those are curated by humans in Phase 2 of the build.
