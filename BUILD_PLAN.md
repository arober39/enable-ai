# Enable AI: Architecture and Build Plan (v1.2)

> **Historical document.** This was the source of truth for the v1 build (Coordinator + Support Enablement Agent + tutorial-aligned orchestrator), which is complete on disk. The project direction changed on 2026-06-04 and again on 2026-08-05 — see `VISION.md` for the current direction. Do not resume the phases below.

This document is the build plan for Enable AI, an AI enablement orchestration system that operates on a fictional company (Serenia & Co.). The v1 goal is to ship the coordinator and the Support Enablement Agent end-to-end, plus the support orchestrator the agent generates — sufficient to support the first published tutorial (`tutorial-01-multi-signal-guardrails`).

## How to use this document

Work through the phases in order. After each phase, stop and report what was built, what remains, and any decisions you need from me. Do not skip phases. Do not start the next phase until I've acknowledged the current one. **Do not begin the next phase before acknowledgment, even if the current phase finishes early.** Use idle time to re-audit the current phase against its checklist, not to push into the next one.

For every step:
- Read existing code before adding new code. Audit, then act.
- Ask before doing anything destructive (overwriting existing files, deleting directories, force-pushing).
- Surface every environment variable in the final summary at the end of each phase.
- Do not run anything that triggers external API calls (no calls to LaunchDarkly, no calls to Anthropic, no GitHub actions) unless I explicitly approve.

When in doubt, ask. The cost of asking is always lower than the cost of rebuilding.

## Architectural principles

These principles govern every decision in the build. They are not optional.

### Hub-and-spoke orchestration

One Coordinator agent receives all inbound requests and routes to specialized Enablement Subagents (Support is the only one in v1). The Coordinator owns:
- Intent classification and request decomposition
- Subagent selection and delegation via the `Task` tool
- Error handling and structured propagation
- Result aggregation and final response synthesis

Subagents have isolated context. They do not inherit the Coordinator's conversation history. All context the subagent needs must be explicitly passed in the Task prompt. All communication between subagents flows through the Coordinator — never directly.

### Deterministic enforcement via hooks

Anywhere a rule must be guaranteed — financial limits, write boundaries, destructive operation gates, credential scope — the rule is implemented as a `PreToolUse` or `PostToolUse` hook, not as a prompt instruction. Prompt instructions give probabilistic compliance; hooks give deterministic guarantees. Use hooks for:
- Blocking writes to anything other than the agent's working directory
- Refusing tool calls that would touch real production LaunchDarkly resources without explicit confirmation
- Normalizing tool outputs into consistent schemas

### Structured outputs with JSON Schema

Every agent that produces a plan, recommendation, or report uses `tool_use` with a strict JSON Schema. No free-text outputs for structured data. Required vs. nullable fields are deliberate. Enum fields include `"unclear"` or `"other"` plus a detail string for extensibility.

### Tool design with least privilege

Each subagent receives only the tools it needs for its function. The Support Enablement Agent does not have legal-document tools. The Coordinator has the `Task` tool plus a small set of cross-role utilities. Tool descriptions are explicit about input formats, expected outputs, edge cases, and when to use the tool vs. similar alternatives.

### MCP-first integration

Where an external tool has an official or community MCP server, use it. Build a minimal custom MCP server only when no usable existing one exists. Document the choice in the enablement plan output.

### Credentials via environment variables

No credentials hardcoded anywhere. All external tool credentials are read from environment variables. The orchestrator detects missing credentials and degrades to realistic stubs. The repo ships with `.env.example` listing every variable with a placeholder. **`.env.example` is established in Phase 1 and is the single source of truth for credential conventions — every later phase reads from it.**

### Context management

Long-running subagent investigations use scratchpad files (`agent-state/<agent-name>-scratchpad.md`) to preserve findings across context boundaries. Subagent context budgets are constrained — pass minimal context, demand structured output, restrict toolsets.

### Branch-per-tutorial repo layout

- `main` is the active development line and advances forward as new work lands.
- Each published tutorial has its own branch (`tutorial-01-multi-signal-guardrails`, etc.) representing the repo state at that tutorial's start.
- **Tutorial branches are frozen snapshots once published.** They are not rebased onto main. If a tutorial needs a fix after publication, cut a new versioned branch (`tutorial-01-v2-...`) rather than mutating the original.
- Tutorial-specific code lives in `tutorials/<tutorial-name>/`.

## Phase 0: Audit

Before building anything, audit the repo's current state. Report on:

1. What directories and files exist
2. Whether any LaunchDarkly, Anthropic, or MCP-related code is already present
3. Whether there is any prior `.claude/` configuration
4. Whether `.env.example` or `Makefile` already exist
5. What language and framework conventions are in use, if any

If the repo is empty or near-empty, proceed to Phase 1. If there is significant existing code, stop and ask before proceeding — I need to decide whether to integrate with what's there or start fresh.

## Phase 1: Repo scaffolding

Establish the foundational structure. After this phase, the repo should have all top-level directories, all CLAUDE.md and `.claude/` configuration, the full credential contract (`.env.example`), and an empty but valid project skeleton.

### 1.1 Directory structure

Create the following directory tree:

```
enable-ai/
├── BUILD_PLAN.md                  # this document, committed to the repo
├── README.md
├── SERENIA.md
├── CLAUDE.md
├── .env.example
├── .gitignore
├── Makefile
├── pyproject.toml
├── .claude/
│   ├── CLAUDE.md
│   ├── rules/
│   │   ├── coding-style.md
│   │   ├── orchestrator-conventions.md
│   │   ├── mcp-server-conventions.md
│   │   ├── testing.md
│   │   └── observability.md
│   └── skills/
│       ├── enable-department/SKILL.md
│       ├── audit-orchestrator/SKILL.md
│       └── replay-traffic/SKILL.md
├── coordinator/
│   ├── __init__.py
│   ├── agent.py
│   ├── definition.py
│   ├── schemas.py
│   ├── hooks/
│   │   ├── __init__.py
│   │   ├── enforce_credentials.py
│   │   ├── enforce_writes.py
│   │   └── normalize_responses.py
│   └── prompts/
│       └── coordinator_system.md
├── enablement_agents/
│   ├── __init__.py
│   ├── base.py
│   └── support/
│       ├── __init__.py
│       ├── agent.py
│       ├── definition.py
│       ├── domain_knowledge.md
│       ├── tools.py
│       └── prompts/
│           └── support_system.md
├── orchestrators/
│   └── support/
│       └── (generated by the Support Enablement Agent — empty in v1 scaffold)
├── stacks/
│   └── support.yaml
├── tools/
│   ├── intercom.yaml
│   ├── zendesk.yaml
│   ├── slack.yaml
│   └── hubspot.yaml
├── mcp_registry/
│   ├── intercom.yaml
│   ├── zendesk.yaml
│   ├── slack.yaml
│   └── hubspot.yaml
├── data/
│   └── support/
│       ├── customers.json
│       ├── tickets.json
│       └── policies.md
├── scripts/
│   ├── setup_ai_configs.py
│   ├── drive_traffic.py
│   └── replay_traffic.py
├── tutorials/
│   └── (empty in v1 scaffold; populated by tutorial branches)
├── agent-state/
│   └── (created on first run; .gitignored)
└── tests/
    ├── coordinator/
    ├── enablement_agents/
    └── orchestrators/
```

Initialize `__init__.py` files where needed. Add `.gitignore` entries for `.env`, `agent-state/*`, `__pycache__/`, and `.pytest_cache/`.

The static-data files under `stacks/`, `tools/`, `mcp_registry/`, and `data/support/` are created here as empty placeholders and **filled in during Phase 2**. Do not generate their content yet.

### 1.2 CLAUDE.md hierarchy

Create the three-level CLAUDE.md hierarchy.

**Project root `CLAUDE.md`** — visible to all Claude Code sessions working on this repo. Contains:
- One-paragraph project description
- Reference to the architectural principles section above (via `@./.claude/rules/orchestrator-conventions.md`)
- Pointer to `SERENIA.md` for fictional-company context
- Pointer to `BUILD_PLAN.md` for in-progress build state
- Build-and-run conventions: `make install`, `make setup`, `make test`, `make replay-traffic`

**`.claude/CLAUDE.md`** — Claude-Code-specific guidance. Contains:
- Coding standards (via `@./rules/coding-style.md`)
- Testing requirements (via `@./rules/testing.md`)
- The architectural principles (via `@./rules/orchestrator-conventions.md`)
- A note pinning the Claude Agent SDK version installed at build time (read it from `pyproject.toml` and quote the exact version, not "the latest")

**Directory-level CLAUDE.md files** for each major subdirectory that has its own conventions:
- `coordinator/CLAUDE.md` — coordinator-specific patterns (Task tool usage, hook registration, structured outputs)
- `enablement_agents/CLAUDE.md` — base class conventions, subagent isolation, scratchpad usage
- `orchestrators/CLAUDE.md` — generated orchestrator conventions (read-only context for now since v1 generates this)

### 1.3 Path-scoped rules

Create `.claude/rules/` with YAML frontmatter `paths` directives so each rule loads only when relevant.

`.claude/rules/coding-style.md`:
- Header: `paths: ["**/*.py"]`
- Content: PEP 8, type hints required, async/await for I/O, no `print()` (use the logger), Pydantic for all data models

`.claude/rules/orchestrator-conventions.md`:
- Header: `paths: ["coordinator/**/*.py", "enablement_agents/**/*.py"]`
- Content: hub-and-spoke principles, hooks vs. prompts, structured output schemas, scratchpad file usage

`.claude/rules/mcp-server-conventions.md`:
- Header: `paths: ["orchestrators/**/mcp_servers/**/*.py", "mcp_registry/**/*.yaml"]`
- Content: tool description requirements, structured `isError` responses, JSON Schema requirements

`.claude/rules/testing.md`:
- Header: `paths: ["tests/**/*.py", "**/*.test.py"]`
- Content: pytest, async test support, fixtures over hardcoded data, no real API calls in deterministic tests, live-LLM tests gated on `ANTHROPIC_API_KEY` and marked with `@pytest.mark.live`

`.claude/rules/observability.md`:
- Header: `paths: ["**/*.py"]`
- Content: OpenTelemetry instrumentation requirements, span naming conventions, resource attributes (`service=<name>`), what to instrument (LLM calls, tool calls, decision points)

### 1.4 Skills

Create `.claude/skills/` for project-wide slash commands. Each skill explicitly declares its context isolation.

`.claude/skills/enable-department/SKILL.md`:
- Frontmatter: `argument-hint: "<department-name>"`, `context: main`, `allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Task"]`
- Content: instructions for invoking the Coordinator to run a department enablement (read the stack file, invoke the appropriate Enablement Agent, generate the orchestrator PR)
- Rationale for `context: main`: the skill is the user's entry point to the Coordinator, which itself manages context via Task delegation

`.claude/skills/audit-orchestrator/SKILL.md`:
- Frontmatter: `context: fork`, `allowed-tools: ["Read", "Grep", "Glob"]`
- Content: instructions for auditing a generated orchestrator's structure, configurations, and credentials handling
- Rationale for `context: fork`: audits are independent investigations and should not pollute the calling context

`.claude/skills/replay-traffic/SKILL.md`:
- Frontmatter: `argument-hint: "<variation-name>"`, `context: main`, `allowed-tools: ["Bash"]`
- Content: instructions for triggering the synthetic traffic replay against a specific AI Config variation
- Rationale for `context: main`: the skill is a thin shell wrapper; no investigative context to isolate

### 1.5 Environment variables and credentials contract

`.env.example` is established here and is the source of truth for the credential contract. Every later phase reads from this file rather than inventing new variables.

```
# Required for the Coordinator to actually run an LLM
ANTHROPIC_API_KEY=                  # Set this to run the Coordinator and Enablement Agents
# OPENAI_API_KEY=                   # Optional alternative

# LaunchDarkly access (only needed for real AI Config provisioning and observability)
LAUNCHDARKLY_API_KEY=               # For scripts/setup_ai_configs.py and scripts/setup_metrics.py (REST API)
LAUNCHDARKLY_PROJECT_KEY=enable-ai  # Set to your LaunchDarkly project key
LAUNCHDARKLY_SDK_KEY=               # Server-side SDK key — used by the support orchestrator runtime to fetch AI Config variations and emit ld_client.track events

# Demo mode: blocks all external API calls (default true)
ENABLE_AI_DEMO_MODE=true

# Override that lets the build agent write to CLAUDE.md files (default false)
ALLOW_CLAUDEMD_WRITES=false

# Support orchestrator credentials (all optional; stubs are used when missing)
INTERCOM_API_KEY=
ZENDESK_API_TOKEN=
SLACK_BOT_TOKEN=
HUBSPOT_API_KEY=

# Observability
OTEL_EXPORTER_ENDPOINT=             # Optional: where to send OTel traces
OTEL_SERVICE_NAME=enable-ai

# LaunchDarkly MCP server (used by scripts/setup_ai_configs.py if available)
# No credential needed — uses OAuth
```

Invariants to enforce from this point forward:
- Every credential read in code reads from one of these env vars
- The `enforce_credentials` hook (built in Phase 3) respects `ENABLE_AI_DEMO_MODE`
- Missing optional credentials trigger stub mode without crashing
- `enforce_writes` (built in Phase 3) respects `ALLOW_CLAUDEMD_WRITES`

### 1.6 Configuration files

Create:
- `pyproject.toml` with project metadata, Python 3.12+, and these dependencies (pin exact versions installed at build time, not ranges): `claude-agent-sdk`, `anthropic`, `pydantic`, `pyyaml`, `openinference-instrumentation`, `opentelemetry-sdk`, `httpx`, `launchdarkly-server-sdk-ai`, `pytest`, `pytest-asyncio`, `ruff`, `mypy`
- `Makefile` with targets: `install`, `setup`, `test`, `test-live`, `replay-traffic`, `lint`, `typecheck`, `clean`
- `.gitignore` covering common Python ignores plus `.env`, `agent-state/*`, `*.scratchpad.md`

### 1.7 Initial documentation

Write the initial versions of:
- `README.md` — project overview, install instructions, the high-level "what is Enable AI" pitch, pointer to `BUILD_PLAN.md`
- `SERENIA.md` — the fictional company's world bible: org chart with 8 departments, 3-5 named fake employees per department, 5 fake customer personas, 3 fake recurring scenarios, the fake brand voice
- `BUILD_PLAN.md` — copy of this document, committed verbatim so future sessions can resume
- The placeholder content of `CLAUDE.md` and `.claude/CLAUDE.md`

### 1.8 Phase 1 checkpoint

Before proceeding, confirm:
- [ ] Directory tree matches the spec
- [ ] All three CLAUDE.md levels are present and link to rules via `@path` syntax
- [ ] `.claude/CLAUDE.md` pins the exact Claude Agent SDK version
- [ ] All `.claude/rules/` files have correct `paths` frontmatter
- [ ] All three skills have correct frontmatter (including explicit `context:`) and instruction prose
- [ ] `.env.example` is complete and matches the contract above
- [ ] `pyproject.toml`, `Makefile`, `.gitignore` are valid and complete
- [ ] `README.md`, `SERENIA.md`, and `BUILD_PLAN.md` are written, not placeholder
- [ ] Empty placeholder files exist for the Phase 2 static data, but no content yet

Stop. Report what was built. Wait for my acknowledgment.

## Phase 2: Static knowledge (stacks, tools, MCP registry, synthetic data)

Populate the static knowledge that the Support Enablement Agent depends on. **This phase comes before the agent itself, so the agent has its data dependencies ready the moment it runs.**

### 2.1 Serenia's support stack

`stacks/support.yaml` — Serenia & Co.'s declared customer support tool stack:

```yaml
department: support
declared_at: 2026-01-15
tools:
  - name: intercom
    primary_use: ticketing
    description: Inbound customer messages, conversation threading, agent assignment
  - name: zendesk
    primary_use: knowledge_base
    description: Articles, FAQs, internal documentation searchable by agents
  - name: slack
    primary_use: internal_handoff
    description: Escalation channel for complex tickets; internal team coordination
  - name: hubspot
    primary_use: crm
    description: Customer profile, account history, subscription status
```

### 2.2 Tool registry

For each tool in the stack, create `tools/<name>.yaml`:

`tools/intercom.yaml`:
```yaml
canonical_name: intercom
vendor: Intercom
categories: [ticketing, customer_messaging, customer_support]
native_ai_features:
  - name: Fin
    description: AI agent for first-response drafting and resolution suggestions
    maturity: ga
    coverage: medium
api_surface:
  has_rest_api: true
  has_webhooks: true
  rate_limits: standard
integration_patterns:
  - augment_with_custom_ai
  - orchestrate_into_unified_surface
notes: "Strong native AI but limited to Intercom's own model and surface. Custom orchestration on top adds flexibility."
```

Repeat for `zendesk.yaml`, `slack.yaml`, `hubspot.yaml`. Each file should be realistic — accurate to the tool's actual AI capabilities at time of writing.

### 2.3 MCP registry

For each tool, create `mcp_registry/<name>.yaml`:

`mcp_registry/intercom.yaml`:
```yaml
tool: intercom
mcp_server:
  available: true
  origin: official
  maintained_by: Intercom
  url: "https://github.com/intercom/mcp-server-intercom"
  install: "npx @intercom/mcp-server"
  tools_exposed: ["search_conversations", "get_conversation", "send_reply", "assign_to_agent"]
fallback_if_unavailable: direct_api
```

For tools where no MCP server exists, set `available: false` and explain. The Support Enablement Agent's `lookup_tool_capability` tool (built in Phase 4) reads these files.

### 2.4 Synthetic data

Populate `data/support/`:
- `customers.json` — 20 fake customer records (id, name, email, plan, subscription_status, signup_date)
- `tickets.json` — 50 fake support tickets (id, customer_id, subject, body, status, created_at, conversation_history)
- `policies.md` — Serenia's policies that the orchestrator's support agent can reference (refund policy, escalation policy, response time SLAs, etc.). Roughly 500 words.

Data should be realistic. Names should not be obviously fake ("Test User 1"). Tickets should reflect real support scenarios that would happen at an events business: lost bookings, vendor issues, payment questions, refund requests.

This is the part of the build most likely to feel rushed. Take time on it — the agent's outputs are only credible if its inputs are.

### 2.5 Phase 2 checkpoint

Before proceeding, confirm:
- [ ] `stacks/support.yaml` is complete and realistic
- [ ] All four `tools/*.yaml` files are complete and accurate to current vendor AI features
- [ ] All four `mcp_registry/*.yaml` files are complete with real or `available: false` entries
- [ ] Synthetic data in `data/support/` is realistic and varied
- [ ] No file is a placeholder

Stop. Report what was built. Wait for my acknowledgment.

## Phase 3: Coordinator

Build the Coordinator agent, its schemas, and its hooks.

### 3.1 Coordinator agent definition

In `coordinator/definition.py`, define the Coordinator using the Claude Agent SDK's `AgentDefinition`. Specifications:

- `name`: `"coordinator"`
- `description`: routes inbound requests across enablement subagents; never produces orchestrator code directly
- `system_prompt`: loaded from `coordinator/prompts/coordinator_system.md`
- `allowed_tools`: `["Task", "Read", "Write", "Edit", "Glob", "Grep", "Bash"]` (Bash limited by hook in 3.3)

The system prompt should:
- Establish the Coordinator's role: classify inbound enablement requests, decompose into subtasks, delegate to the right Enablement Subagent, aggregate results
- Specify the contract for delegation: when invoking a subagent via `Task`, the prompt must include the department stack file path, the relevant tool registry entries, and any prior context
- Forbid the Coordinator from directly editing files in `orchestrators/`, except to commit generated output assembled by a subagent
- Specify the structured output schema for an enablement plan (defined in 3.2)
- Reference the architectural principles via `@../.claude/rules/orchestrator-conventions.md`

Note: subagent registration (how the Coordinator's `Task` tool actually knows the Support agent exists) is handled in Phase 4.6, after the Support agent itself is defined.

### 3.2 Structured output schemas

In `coordinator/schemas.py`, define Pydantic models. All are referenced by both the Coordinator and the Enablement Agents. Every subagent's final output conforms to one of these schemas via `tool_use` with the schema attached.

```python
class PlanMetadata(BaseModel):
    generated_at: datetime          # UTC timestamp the plan was finalized
    agent_name: str                 # which Enablement Agent produced this plan
    agent_version: str              # version string from the agent definition
    stack_file_hash: str            # sha256 of the stack file at time of generation
    coordinator_session_id: str     # session id of the Coordinator run

class CapabilityFinding(BaseModel):
    capability: str
    status: Literal["covered", "partial", "gap", "redundant"]
    tools_involved: list[str]
    notes: str | None = None

class Recommendation(BaseModel):
    id: str
    kind: Literal["use_native_ai", "augment_with_custom_ai", "consolidate", "orchestrate"]
    description: str
    tools_affected: list[str]
    effort: Literal["small", "medium", "large"]
    notes: str | None = None

class OrchestratorPRPlan(BaseModel):
    """Metadata describing the orchestrator that *will be* generated.
    The actual code lives on disk under orchestrators/<department>/ and is
    produced in Phase 5. This object describes the intended artifact."""
    branch: str
    files_to_create: list[str]
    mcp_servers_used: list[str]
    mcp_servers_to_generate: list[str]
    ai_configs_to_create: list[str]
    env_vars_required: list[str]

class EnablementPlan(BaseModel):
    department: str
    summary: str
    capability_coverage: list[CapabilityFinding]
    recommendations: list[Recommendation]
    orchestrator_pr_plan: OrchestratorPRPlan | None
    metadata: PlanMetadata
```

Note the rename: `OrchestratorPR` → `OrchestratorPRPlan` to disambiguate metadata-about-the-PR from the actual generated code. The on-disk code is the output of Phase 5; this schema only describes what that code will be.

### 3.3 Hooks

Implement the three hooks in `coordinator/hooks/`:

`enforce_credentials.py` — a `PreToolUse` hook. If a tool call references a real LaunchDarkly API endpoint or a real external SaaS API and `ENABLE_AI_DEMO_MODE=true` is set, block the call and return a structured refusal:

```python
{
  "isError": True,
  "content": {
    "errorCategory": "permission",
    "isRetryable": False,
    "message": "Demo mode is active. Real external API calls are blocked. Use stubs instead.",
    "blocked_endpoint": "<endpoint>",
    "suggestion": "Set ENABLE_AI_DEMO_MODE=false to enable real API calls."
  }
}
```

`enforce_writes.py` — a `PreToolUse` hook for `Write` and `Edit` tools. Blocks writes to:
- Anywhere outside the repo root
- `.env` (must be edited manually by humans)
- `CLAUDE.md` files (must be edited manually unless explicit `ALLOW_CLAUDEMD_WRITES=true`)
- `data/` directory at runtime (only the Phase 2 setup can write here)

`normalize_responses.py` — a `PostToolUse` hook on MCP tool calls. Ensures all MCP tool errors conform to the structured-error schema (errorCategory, isRetryable, message, optional partial_results). If an MCP tool returns a non-structured error, this hook wraps it.

Register all three hooks in `coordinator/agent.py` when the Coordinator is instantiated.

### 3.4 Coordinator entry point

`coordinator/agent.py` defines `run_coordinator(request: str) -> CoordinatorRunResult` — the function that starts a Coordinator session, executes the request, and returns the structured result. Specifications:
- Accept a free-text request string
- Create an `AgentDefinition` with the Coordinator's config
- Register the hooks
- Register subagents (added in Phase 4.6 — leave a registration hook in the code now)
- Start a session (fresh session, not resumed)
- Pass the request as the user message
- Loop until `stop_reason == "end_turn"`
- Parse the final `tool_use` (which conforms to `EnablementPlan` schema) and return it

`coordinator/__main__.py` exposes the function as a CLI so `python -m coordinator "Enable AI for customer support"` works. The CLI:
- Takes the request as the single positional argument (joined if multi-word).
- Calls `run_coordinator(request)`.
- Pretty-prints the returned `EnablementPlan` (and `OrchestratorRunResult` if present) as JSON to stdout.
- Exits 0 on success, non-zero on schema validation failure or run error.

### 3.5 Phase 3 checkpoint

Before proceeding, confirm:
- [ ] Coordinator AgentDefinition is complete and references all configured tools
- [ ] System prompt is written and references rules via `@path` syntax
- [ ] All Pydantic schemas (including `PlanMetadata` and the renamed `OrchestratorPRPlan`) are defined and validated
- [ ] All three hooks are implemented and tested manually with sample inputs
- [ ] `coordinator/agent.py` exports `run_coordinator()` with the right signature
- [ ] The subagent registration hook in `agent.py` is present but empty (no agents registered yet)

Stop. Report what was built. Wait for my acknowledgment.

## Phase 4: Support Enablement Agent (plan production)

Build the Support Enablement Agent and its capability to produce an `EnablementPlan`. **This phase does not generate orchestrator code** — that is Phase 5. Splitting these keeps each phase to a single coherent deliverable.

### 4.1 Base class

In `enablement_agents/base.py`, define `EnablementAgentBase` — the abstract base that all department agents inherit from. Specifications:
- Pydantic config object: `department`, `domain_knowledge_path`, `stack_path`, `tool_registry_path`
- Abstract methods:
  - `produce_plan(stack: StackFile) -> EnablementPlan` (implemented in Phase 4)
  - `generate_orchestrator(plan: EnablementPlan) -> OrchestratorRunResult` (implemented in Phase 5)
- Shared utilities: stack file parsing, tool registry lookup, MCP registry lookup, scratchpad I/O

### 4.2 Support Enablement Agent definition

In `enablement_agents/support/definition.py`, define the Support Enablement Agent using `AgentDefinition`:
- `name`: `"support_enablement_agent"`
- `description`: enables AI capabilities for customer support functions; reads stack file, produces enablement plan, generates support orchestrator
- `system_prompt`: from `enablement_agents/support/prompts/support_system.md`
- `allowed_tools`: limited set — `["Read", "Grep", "Glob", "Write", "Edit"]` plus a custom tool `lookup_tool_capability` (defined in 4.4)

The system prompt should:
- Establish the agent's role: take a customer support stack file as input, produce a structured `EnablementPlan` recommending capability coverage findings, consolidations, and augmentations
- Reference the agent's domain knowledge file (`@./domain_knowledge.md`) explicitly
- Specify that the final output must be a `tool_use` conforming to `EnablementPlan` schema
- Forbid the agent from making any external API calls (enforced by the credentials hook)
- Note that orchestrator code generation is a separate invocation (Phase 5), not part of plan production

### 4.3 Domain knowledge

In `enablement_agents/support/domain_knowledge.md`, write the Support Enablement Agent's knowledge base. Contents:
- Functional capabilities of an AI-enabled customer support function: intent classification, first-response drafting, escalation routing, FAQ retrieval, sentiment analysis, conversation summarization, knowledge base search
- For each capability, what AI features look like (with examples)
- Common patterns: how support agents typically integrate with CRMs, ticketing systems, knowledge bases
- Failure modes specific to support: hallucinated policy details, over-escalation, premature resolution, tone-deafness

This file is read by the Support Enablement Agent as part of its system prompt context. Length: roughly 1000-1500 words. Quality matters here — the agent's recommendations are only credible if its domain knowledge is.

### 4.4 Custom tool: `lookup_tool_capability`

In `enablement_agents/support/tools.py`, implement the `lookup_tool_capability` tool with JSON Schema:

```python
{
  "name": "lookup_tool_capability",
  "description": "Look up the AI capabilities and integration patterns of a specific tool. Returns structured information about native AI features, API surface, and known MCP server availability. Use this when assessing how a department's tool stack could be augmented with AI.",
  "input_schema": {
    "type": "object",
    "properties": {
      "tool_name": {"type": "string", "description": "Canonical tool name, e.g. 'hubspot', 'intercom'"},
      "capability_filter": {"type": "string", "description": "Optional: filter to a specific capability area (e.g. 'crm', 'ticketing')"}
    },
    "required": ["tool_name"]
  }
}
```

The tool's execution reads `tools/<tool_name>.yaml` and `mcp_registry/<tool_name>.yaml` (populated in Phase 2) and returns a structured response. If the tool isn't found, return a structured `isError` response per the conventions in Phase 3.

### 4.5 Plan production logic

The agent's `produce_plan()` flow when it receives a request like `"Enable AI for customer support"`:

1. Read `stacks/support.yaml` to get Serenia's declared support stack
2. For each tool in the stack, call `lookup_tool_capability` to gather AI feature and MCP server data
3. Read the domain knowledge file
4. Compare declared stack against the domain knowledge: identify capability coverage, gaps, redundancies, consolidation opportunities
5. Produce an `EnablementPlan` with the four recommendation types
6. Populate `orchestrator_pr_plan` (metadata only — the actual code is produced in Phase 5)
7. Compute `metadata.stack_file_hash` and stamp `metadata.generated_at`

### 4.6 Register the Support agent on the Coordinator

Wire the agent into the Coordinator's `Task` tool. In `coordinator/agent.py`, the subagent registration hook from Phase 3.4 now becomes a concrete registration:

```python
def _register_subagents(coordinator: AgentDefinition) -> None:
    from enablement_agents.support.definition import support_enablement_agent
    coordinator.subagents = [support_enablement_agent]
```

Test that `Task(agent="support_enablement_agent", prompt=...)` from inside the Coordinator successfully invokes the Support agent in an isolated context.

### 4.7 Phase 4 checkpoint

Before proceeding, confirm:
- [ ] `EnablementAgentBase` is defined with the right abstract surface
- [ ] Support Enablement Agent definition is complete
- [ ] `domain_knowledge.md` is written (not placeholder, ~1000-1500 words)
- [ ] `lookup_tool_capability` tool is implemented and tested against the Phase 2 data
- [ ] `produce_plan()` produces valid `EnablementPlan` output, including a populated `orchestrator_pr_plan` metadata field
- [ ] Support agent is registered on the Coordinator
- [ ] An end-to-end smoke test: `run_coordinator("Enable AI for customer support")` returns a valid `EnablementPlan` (no orchestrator code yet)

Stop. Report what was built. Wait for my acknowledgment.

## Phase 5: Support orchestrator generation

Implement the Support agent's `generate_orchestrator()` capability and produce the runnable orchestrator under `orchestrators/support/`. This phase is a second invocation of the Support agent, separate from the plan production in Phase 4.

### 5.1 Orchestrator generation flow

`generate_orchestrator(plan: EnablementPlan) -> OrchestratorRunResult` reads the `EnablementPlan` from Phase 4 and produces:

- `orchestrators/support/orchestrator.py` — runtime entry point for the support orchestrator (this is a *runtime* agent, separate from the build-time Coordinator)
- `orchestrators/support/agent_definition.py` — the Support Ops Agent definition
- `orchestrators/support/prompts/v1_baseline.md` — baseline support prompt; corresponds to the `v1-baseline` AI Config variation
- `orchestrators/support/prompts/v2_detailed_responses.md` — v2 prompt; differs from `v1_baseline.md` by a single added instruction designed to cause policy-volunteering hallucinations (the failure mode the multi-signal guardrails tutorial demonstrates); corresponds to the `v2-detailed-responses` AI Config variation
- `orchestrators/support/judges/factual_accuracy.md` — judge prompt that scores a response's factual accuracy against Serenia's policy documentation, returning a 0.0-1.0 decimal score. The LaunchDarkly judge feature auto-generates a `support.judge.factual_accuracy` metric when this judge is attached to the AI Config.
- `orchestrators/support/.mcp.json` — references each tool's MCP server (Intercom, Zendesk, Slack, HubSpot)
- `orchestrators/support/mcp_servers/intercom/` etc. for each tool (stubs in v1)
- `orchestrators/support/observability.py` — OTel instrumentation per `.claude/rules/observability.md`
- `orchestrators/support/.env.example` — credentials required (must be a subset of the root `.env.example` from Phase 1.5; no new variable names introduced)
- `orchestrators/support/Makefile` — `make run` target
- `orchestrators/support/README.md` — how to run, what it does
- `orchestrators/support/ai_configs.manifest.yaml` — manifest consumed by `scripts/setup_ai_configs.py` in Phase 6

### 5.2 Runtime behavioral spec

The generated orchestrator must demonstrate these behaviors when run against stubs:

- Accepts a synthetic ticket inquiry (subject + body + customer_id) as input
- Constructs an `LDContext` from the request (single-context, key=request_id, kind=request)
- Fetches its system prompt at runtime from `ld_ai.config("support-orchestrator-config", context)` — the active variation (`v1-baseline` or `v2-detailed-responses`) is governed by LaunchDarkly, not hardcoded
- Classifies the intent (refund, escalation, FAQ, status check, other)
- For FAQ-class intents: searches the knowledge base stub (returns a templated answer)
- For refund-class intents: reads `data/support/policies.md` and drafts a response citing the relevant policy
- For escalation-class intents: produces a structured handoff message
- Returns a structured response: `{intent, draft_reply, confidence, action_taken, citations, escalated, error}`
- On completion, emits two custom LaunchDarkly events via `ld_client.track`:
  - `support.escalation` — `metric_value=1` if the response escalated, else `0`
  - `support.error` — `metric_value=1`, only emitted on error paths
- Emits OTel spans for: AI Config fetch, intent classification, knowledge base search, response drafting, final output

This behavioral contract is what the Phase 7 tests verify. The two LD events plus the LaunchDarkly-side judge (`support.judge.factual_accuracy`, auto-generated from `judges/factual_accuracy.md`) are the three signals the multi-signal guardrails tutorial attaches to its guarded rollout.

### 5.3 OrchestratorRunResult schema

In `coordinator/schemas.py`, add:

```python
class OrchestratorRunResult(BaseModel):
    """Result of orchestrator generation — what actually got written to disk."""
    department: str
    files_created: list[str]
    mcp_servers_generated: list[str]
    ai_configs_manifest_path: str
    env_vars_required: list[str]
    plan_reference: PlanMetadata
```

Distinct from `OrchestratorPRPlan` (intent) in that this records what was actually produced.

### 5.4 Phase 5 checkpoint

Before proceeding, confirm:
- [ ] `generate_orchestrator()` is implemented on the Support agent
- [ ] The full `orchestrators/support/` tree is generated and matches 5.1
- [ ] Generated `.env.example` is a strict subset of root `.env.example` (no new variables)
- [ ] The generated orchestrator can `make run` against stubs and demonstrates the behaviors in 5.2
- [ ] `OrchestratorRunResult` schema is added and used
- [ ] End-to-end smoke test: `run_coordinator("Enable AI for customer support, including the runnable orchestrator")` produces both an `EnablementPlan` and a working `orchestrators/support/` directory

Stop. Report what was built. Wait for my acknowledgment.

## Phase 6: Scripts and operational tooling

### 6.1 `scripts/setup_ai_configs.py`

Provisions the AI Configs required for the support orchestrator via the LaunchDarkly REST API. Specifications:
- Reads the manifest at `orchestrators/support/ai_configs.manifest.yaml` (generated in Phase 5)
- Provisions one AI Config named `support-orchestrator-config` in **completion mode** with two variations:
  - `v1-baseline` — prompt loaded from `orchestrators/support/prompts/v1_baseline.md`, model `claude-sonnet-4-6`, set as the default variation
  - `v2-detailed-responses` — prompt loaded from `orchestrators/support/prompts/v2_detailed_responses.md`, model `claude-sonnet-4-6`
- Each variation has its system prompt, model, max_tokens, temperature
- Initial traffic: 100% v1-baseline, 0% v2-detailed-responses
- Exits 0 on success, non-zero on failure with a structured error report
- Idempotent: if the AI Config or variations already exist, the script updates them rather than failing
- Has a `--dry-run` flag that shows what would be provisioned without making API calls
- Reads `LAUNCHDARKLY_API_KEY` and `LAUNCHDARKLY_PROJECT_KEY` from the env vars defined in Phase 1.5

The same provisioning can be performed by hand via the **LaunchDarkly AI Configs MCP server** in an AI client (Claude Code, Cursor, etc.) — see the README for the natural-language prompt to use. This script remains the primary path because it's reproducible, scriptable, and resets state cleanly between test runs. The MCP route is documented for users who prefer a single-line natural-language setup.

### 6.2 `scripts/drive_traffic.py`

Sends synthetic support conversations through the support orchestrator. Specifications:
- Reads scenario templates from `data/support/replay_scenarios.json` — create this file in this phase (30 scenario templates)
- Each scenario has an `id`, `inquiry_text`, `expected_skill_invoked`, `tags`
- Roughly **8% of scenarios carry a `hallucination_probe` tag** — these are policy-edge-case inquiries (e.g., refund-adjacent questions where the v2-detailed-responses prompt is likely to volunteer unverifiable policy details). These scenarios are what make the multi-signal guardrails tutorial demonstrate a measurable judge-score regression on v2.
- Sends 30+ inquiries through the orchestrator at a configurable rate (default: 1/30s for replay realism)
- Logs each call: variation served, response, parse status, latency, whether judge would have flagged (when run in test mode)
- Idempotent — re-running uses different scenario seeds
- Has `--variation` flag to force a specific variation (useful for tutorial demos)

### 6.3 `scripts/replay_traffic.py`

A thinner wrapper around `drive_traffic.py` for the tutorial scenario:
- Hardcoded to send 200 conversations over 15 minutes
- Hardcoded to force traffic through the target variation
- Designed for tutorial reproduction

### 6.4 `scripts/setup_metrics.py`

Provisions the two LaunchDarkly custom metrics that the multi-signal guardrails tutorial attaches to its guarded rollout. Specifications:
- Creates `support.errors.count` — event name `support.error`, lower-is-better success criteria, randomization unit `request`
- Creates `support.escalation_rate` — event name `support.escalation`, lower-is-better success criteria, randomization unit `request`
- The third tutorial metric (`support.judge.factual_accuracy`) is **not** created by this script — it is auto-generated by LaunchDarkly when the `judges/factual_accuracy.md` judge is attached to the AI Config in the LaunchDarkly UI
- Reads `LAUNCHDARKLY_API_KEY` and `LAUNCHDARKLY_PROJECT_KEY`
- Idempotent: if metrics already exist, the script exits 0 without modification
- Has a `--dry-run` flag
- Exits 0 on success, non-zero on failure with structured error

### 6.5 Makefile targets

Connect the scripts:
- `make install` — installs Python deps
- `make setup-ai-configs` — runs `scripts/setup_ai_configs.py`
- `make setup-metrics` — runs `scripts/setup_metrics.py`
- `make setup` — runs both setup scripts in order
- `make replay-traffic VARIATION=<name>` — runs `scripts/replay_traffic.py --variation <name>`
- `make test` — runs `pytest` excluding `@pytest.mark.live`
- `make test-live` — runs `pytest` including live-LLM tests (requires `ANTHROPIC_API_KEY`)
- `make lint` — runs `ruff`
- `make typecheck` — runs `mypy`

### 6.6 Phase 6 checkpoint

Before proceeding, confirm:
- [ ] All four scripts run end-to-end against stubs (no real API calls in demo mode)
- [ ] `data/support/replay_scenarios.json` has 30 varied, realistic templates with ~8% tagged `hallucination_probe`
- [ ] Makefile targets work as documented (including the new `setup-metrics` target)
- [ ] No script introduces env vars not declared in root `.env.example`

Stop. Report what was built. Wait for my acknowledgment.

## Phase 7: Tests

Build the test suite. **Testing strategy:** deterministic tests are the default and never make external API or LLM calls. Live-LLM end-to-end tests are gated behind `@pytest.mark.live` and only run when `ANTHROPIC_API_KEY` is set. `make test` skips them; `make test-live` includes them.

### 7.1 Coordinator tests (deterministic)

- Test that `enforce_writes` correctly blocks writes outside the repo, to `.env`, and to CLAUDE.md files (and that `ALLOW_CLAUDEMD_WRITES=true` lifts the CLAUDE.md block)
- Test that `enforce_credentials` blocks real API calls when `ENABLE_AI_DEMO_MODE=true`
- Test that `normalize_responses` wraps non-structured MCP errors correctly
- Test that all Pydantic schemas reject invalid inputs and accept canonical examples

### 7.2 Support Enablement Agent tests (deterministic)

- Test that `lookup_tool_capability` returns expected data for known tools and a structured error for unknown tools
- Test that the generated orchestrator's file tree matches the spec in 5.1
- Test that the generated `.env.example` is a strict subset of the root `.env.example`

### 7.3 Orchestrator tests (deterministic)

- Test that the generated support orchestrator imports without error
- Test that its OTel instrumentation registers the expected span names
- Test the structured response shape against fixture inquiries (using a stubbed LLM)
- Test the behavioral contract from Phase 5.2 against the stub: each intent class produces the expected `action_taken`

### 7.4 Live-LLM integration tests (`@pytest.mark.live`)

These are skipped by default. When run:
- Test the full flow: `run_coordinator("Enable AI for customer support")` produces a complete `EnablementPlan` and an `orchestrators/support/` directory
- Test that `produce_plan()` output validates against the `EnablementPlan` schema
- Test that `generate_orchestrator()` output is runnable end-to-end

### 7.5 Phase 7 checkpoint

Before proceeding, confirm:
- [ ] `make test` passes with no `ANTHROPIC_API_KEY` set
- [ ] No deterministic test makes an external API or LLM call
- [ ] Live tests are properly gated on `@pytest.mark.live` and `ANTHROPIC_API_KEY`
- [ ] Coverage is reasonable for the v1 surface (hooks, schemas, tool implementations, orchestrator structure)
- [ ] `make test-live` is documented but not required to pass for the phase to close (it costs money to run)

Stop. Report what was built. Wait for my acknowledgment.

## Phase 8: Documentation and final review

### 8.1 Final READMEs

- Root `README.md` — explains what Enable AI is, how to clone it, how to run the first demo
- `orchestrators/support/README.md` — explains what the support orchestrator does, how to run it
- `SERENIA.md` — final pass on the fictional company
- `BUILD_PLAN.md` — verify the committed version matches the version in use; update if any decisions changed it

### 8.2 Final architecture check

Audit against the architectural principles at the top of this document:
- [ ] Hub-and-spoke is intact: subagents communicate only through the Coordinator
- [ ] All deterministic rules are enforced by hooks, not prompts
- [ ] All structured outputs use Pydantic models with JSON Schema
- [ ] Tool descriptions are explicit about inputs, outputs, and edge cases
- [ ] MCP-first integration is respected in `mcp_registry/`
- [ ] All credentials are env-var-based and trace back to root `.env.example`
- [ ] Scratchpad files and structured state are used in long-running flows
- [ ] CLAUDE.md hierarchy and path-scoped rules are in place
- [ ] Tutorial branches policy (frozen snapshots) is documented in README

### 8.3 Cert-curriculum coverage check (silent)

Verify quietly that the v1 build exercises each domain of the Claude Certified Architect — Foundations curriculum. This check informs whether the build is ready to support cert-practice tutorials; it does not appear in user-facing deliverables.

- Domain 1 (Agent architecture and orchestration): coordinator-subagent, AgentDefinition, hooks, Task tool, fork_session capability
- Domain 2 (Tool design and MCP integration): tool descriptions, structured `isError` responses, allowed_tools, MCP server registry
- Domain 3 (Claude Code configuration): CLAUDE.md hierarchy, `.claude/rules/` with paths, `.claude/skills/`, planning mode usage
- Domain 4 (Prompt engineering): few-shot patterns in agent prompts, JSON Schema validation, retry-with-feedback in error handling
- Domain 5 (Context management): scratchpad files, structured state persistence, position-aware input organization

### 8.4 Phase 8 checkpoint

- [ ] All documentation is final
- [ ] Architectural audit passes
- [ ] Curriculum coverage is verified
- [ ] The repo is ready for the multi-signal guardrails tutorial branch to be cut from `main`
- [ ] On `main`, `tutorials/` is empty. The tutorial branch (`tutorial-01-multi-signal-guardrails`, cut from this state) adds `tutorials/multi-signal-guardrails/` with `example_conversation.md` and any tutorial-specific code. Per Phase 5.1 the orchestrator's two variation prompts (`v1_baseline.md`, `v2_detailed_responses.md`) and the judge (`factual_accuracy.md`) ship on `main` so the tutorial branch only needs to add tutorial-narrative artifacts, not orchestrator artifacts.

Stop. Final report.

## Out-of-scope for v1

These are explicitly out of scope. Do not build them. Do not stub them in ways that suggest they exist.

- Other Enablement Agents (Sales, Marketing, HR, Legal, Finance, etc.) — the Coordinator's `Task` tool should reference subagents generically, but no other subagent definitions exist yet
- Real LaunchDarkly observability instrumentation in the support orchestrator (OTel scaffolding only; export endpoints are optional)
- Multi-environment support (staging, production) — single environment only
- The Next.js front end — CLI/API only for v1
- The "audit your auto-rollbacks" capability — that's a future tutorial
- Anything related to the multi-signal guardrails tutorial itself — that's a separate branch and a separate build

## How to ask for help

If you encounter a decision point I haven't anticipated, stop and ask. Examples:
- An architectural choice that conflicts with the principles
- A dependency that doesn't behave as expected
- A naming collision between files
- A test that fails for unclear reasons

Do not silently work around problems. Do not invent additional structure not specified here. Do not modify the architectural principles to fit implementation difficulty.

If you find that one of my specs is wrong (e.g., the wrong Pydantic field type, an outdated SDK convention), tell me before adjusting. I'd rather fix the spec than ship a workaround.

## Starting

Start with Phase 0 (audit). Report what you find. Wait for me before proceeding to Phase 1.

## Changelog

- **v1.2** — Folded the `tutorial-01-multi-signal-guardrails` requirements that emerged after v1.1 was written. Phase 1.5 adds `LAUNCHDARKLY_SDK_KEY` (server-side runtime SDK key, distinct from the REST `LAUNCHDARKLY_API_KEY`). Phase 1.6 adds `launchdarkly-server-sdk-ai` to the dependency list. Phase 3.4 adds `coordinator/__main__.py` so `python -m coordinator "..."` is the supported CLI entry. Phase 5.1 replaces the single `prompts/system.md` with two variation prompts (`prompts/v1_baseline.md`, `prompts/v2_detailed_responses.md`) and adds `judges/factual_accuracy.md`. Phase 5.2 adds the runtime behaviors that drive the tutorial: AI Config fetch via `ld_ai.config`, `ld_client.track` for `support.escalation` and `support.error` events. Phase 6.1 pins model `claude-sonnet-4-7` and completion mode, and documents the LD AI Configs MCP route as an alternative to the script. Phase 6.2 adds the ~8% `hallucination_probe` scenario requirement. New Phase 6.4 introduces `scripts/setup_metrics.py` for the two custom LD metrics (renumbering 6.4→6.5 Makefile, 6.5→6.6 checkpoint). Phase 8.4 clarifies that `tutorials/` stays empty on `main` and that the tutorial branch adds only narrative artifacts, not orchestrator code.
- **v1.1** — Reordered phases so static data (now Phase 2) precedes the agent that consumes it. Pulled env-var contract (was Phase 6) into Phase 1.5 as the source of truth. Split orchestrator generation (was inside Phase 3) into its own Phase 5 with an explicit runtime behavioral spec. Added explicit subagent registration step (Phase 4.6). Added `PlanMetadata` definition; renamed `OrchestratorPR` → `OrchestratorPRPlan` and added `OrchestratorRunResult` to disambiguate intent from artifact. Clarified testing strategy: deterministic by default, live-LLM tests gated on `@pytest.mark.live`. Specified tutorial branches as frozen snapshots. Made skill context isolation explicit for all three skills. Pinned SDK version in Phase 1.6 rather than "the latest." Added idle-time guidance to "How to use this document."
