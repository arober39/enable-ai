"""Shared factory for role-specific Enablement Subagents.

Each role under `enablement_agents/roles/<id>/` becomes an
`AgentDefinition` named `{role.id}_enablement_agent`. The Coordinator
registers every role via `register_role_agents()` and delegates with
`Task`; adding a role directory is enough — no per-role Python module
is required.

The prompt body is that role's `domain_knowledge.md` (same load-from-disk
pattern as the support agent's system prompt). A shared operational
preamble wraps it so every role agent knows the EnablementPlan contract,
its isolated-context rules, and its constrained toolset.

`lookup_tool_capability` is reused from the support MCP server so the
existing qualified tool name (`mcp__support__lookup_tool_capability`)
keeps working for support and for every other role.
"""

from __future__ import annotations

import os
from typing import Any

from claude_agent_sdk import AgentDefinition

from coordinator.definition import SUBMIT_PLAN_TOOL_NAME
from core.roles import Role, list_roles
from enablement_agents.support.tools import (
    LOOKUP_TOOL_QUALIFIED_NAME,
    SUPPORT_MCP_SERVER_NAME,
)

ROLE_AGENT_VERSION = "0.1.0"

#: Env var that overrides the enablement planner model. Non-empty wins.
#: Blank or unset falls through to ``ROLE_AGENT_MODEL``.
ENABLEMENT_AGENT_MODEL_ENV = "ENABLEMENT_AGENT_MODEL"

#: Default planner model for role enablement agents. Opus 5.5 for plan
#: quality. Set ENABLEMENT_AGENT_MODEL=claude-sonnet-4-6 for cheaper
#: iterative testing. The SDK id follows the same undated pattern as
#: ``claude-sonnet-4-6`` and ``claude-opus-4-8`` elsewhere in this repo.
ROLE_AGENT_MODEL = "claude-opus-5-5"


def resolve_role_agent_model() -> str:
    """Return the model id role enablement planners should run.

    Resolution order: ``ENABLEMENT_AGENT_MODEL`` when set and non-empty
    (surrounding whitespace is ignored), otherwise ``ROLE_AGENT_MODEL``.
    Read at call time so a process restart with a new env value is enough —
    no code change.
    """
    override = os.environ.get(ENABLEMENT_AGENT_MODEL_ENV, "").strip()
    if override:
        return override
    return ROLE_AGENT_MODEL


#: Built-in Claude Code tools every role enablement agent may use.
ROLE_AGENT_BASE_TOOLS: list[str] = [
    "Read",
    "Grep",
    "Glob",
    "Write",
    "Edit",
]

#: Fully-qualified MCP tool names available to every role enablement agent.
ROLE_AGENT_MCP_TOOLS: list[str] = [
    LOOKUP_TOOL_QUALIFIED_NAME,
    SUBMIT_PLAN_TOOL_NAME,
]

#: MCP servers the subagent may reach into. Names must match keys on the
#: parent ClaudeAgentOptions.mcp_servers dict. Typed to match
#: AgentDefinition.mcpServers' invariance.
ROLE_AGENT_MCP_SERVERS: list[str | dict[str, Any]] = [
    SUPPORT_MCP_SERVER_NAME,  # hosts lookup_tool_capability
    "coordinator",  # hosts submit_enablement_plan
]


def _load_domain_knowledge(role: Role) -> str:
    """Read inline domain knowledge or domain_knowledge.md; fail if empty.

    Seeded roles keep the text on disk. Researched roles have no directory
    and carry the markdown on `role.domain_knowledge`.
    """
    path = role.domain_knowledge_path
    text = role.domain_knowledge_text()
    if path is not None and path.exists() and not text.strip():
        raise RuntimeError(
            f"Domain knowledge for role '{role.id}' at {path} is empty. "
            "This file is the prompt body for the role enablement agent."
        )
    if not text.strip():
        raise RuntimeError(
            f"Domain knowledge for role '{role.id}' is missing at {path}."
        )
    return text


def _build_role_prompt(role: Role) -> str:
    """Compose the system prompt: shared contract + role domain knowledge.

    The domain-knowledge file is the prompt body — the same on-disk load
    pattern the support agent uses for its system prompt. The preamble
    is the shared enablement-agent contract (isolated context, tools,
    EnablementPlan submission) so it is not copy-pasted per role.
    """
    domain = _load_domain_knowledge(role)
    return (
        f"You are the **{role.display_name} Enablement Agent** for Enable AI, "
        "operating on the fictional company Serenia & Co. You are a subagent "
        "of the Coordinator and run in isolated context — you do not see the "
        "Coordinator's conversation history. Every piece of context you need "
        "is in this prompt and in the files on disk you can read.\n\n"
        f"Your registered name is `{role.agent_name}`. Your department is "
        f"`{role.department}`.\n\n"
        "## Your role\n\n"
        f"You take the {role.display_name} department's declared tool stack "
        f"(`stacks/{role.department}.yaml`) and produce a structured "
        "**EnablementPlan**. The plan identifies which AI capabilities the "
        "stack covers, where the gaps are, where tools are redundant, and "
        "what to do about each (use native AI as-is, augment with custom AI, "
        "consolidate, or orchestrate). When asked, you also describe — *in "
        "the plan's `orchestrator_pr_plan` field* — the orchestrator that "
        "should be generated from your recommendations. You **never** "
        "generate orchestrator code in this invocation; that is a separate "
        "`generate_orchestrator` operation.\n\n"
        "Your domain knowledge — what this job tends to care about — is the "
        "body of this prompt. It is background for the person in the role. "
        "Selected tools override the role playbook: every finding and "
        "recommendation must be a workflow the declared tools can perform, "
        "based on their capability records. Do not emit a domain-knowledge "
        "theme the selected tools cannot perform, and do not reuse an earlier "
        "plan's themes when the tool list changed.\n\n"
        "## Your tools\n\n"
        "You have a constrained toolset:\n\n"
        "- `Read`, `Grep`, `Glob` — for inspecting files on disk (the stack "
        "file, policy documentation, synthetic data, registry files).\n"
        "- `Write`, `Edit` — available for a later `generate_orchestrator` "
        "flow. **For plan production (this invocation), you should not need "
        "them.** If you find yourself wanting to write a file during plan "
        "production, stop and reconsider — the plan is the deliverable, not "
        "on-disk code.\n"
        "- `lookup_tool_capability` (MCP tool, prefixed `mcp__support__`) — "
        "your primary tool for assessing a stack. Call it for every tool the "
        "stack declares. Always pass the canonical tool name. Use the "
        "`capability_filter` argument when you only want features tagged for "
        "a specific capability area.\n"
        "- `submit_enablement_plan` (MCP tool, prefixed `mcp__coordinator__`) "
        "— your final action. Submitting the plan ends your turn and returns "
        "the result to the Coordinator. The input schema is the Pydantic "
        "`EnablementPlan`; the runtime validates strictly. Extra keys, wrong "
        "enum values, or missing required fields cause the submission to be "
        "rejected — you may correct and resubmit.\n\n"
        "You do **not** have `Task`, `Bash`, or any web-fetching tool. You do "
        "not call external APIs. The Coordinator's `enforce_credentials` hook "
        "backs this up — but you should not even attempt to reach external "
        "services.\n\n"
        "## Plan production flow (the work you do on every invocation)\n\n"
        f"1. Read `stacks/{role.department}.yaml` and parse it. The "
        "Coordinator passes this path explicitly in your invocation prompt "
        "— if it's missing or empty, return a structured error via "
        "`submit_enablement_plan`'s `summary` field with no recommendations.\n"
        "2. Read every selected tool's capability record first. Use the "
        "domain knowledge in this prompt only as background for the role, "
        "not as the list of findings to produce.\n"
        "3. For *every* tool the stack declares, call "
        "`lookup_tool_capability(tool_name=<name>)`. Optionally call again "
        "with a `capability_filter` if you want to drill into a specific "
        "capability area for that tool. Never assume a tool's capabilities "
        "from memory.\n"
        f"4. Read `data/{role.department}/policies.md` if it exists and your "
        "recommendations would cite policy.\n"
        "5. For each tool in the stack, write a finding for work that tool's "
        "catalog record can do. Status is covered, partial, gap, or "
        "redundant. Cite the tool names. Do not score a fixed role checklist "
        "the tools cannot perform.\n"
        "6. Translate those findings into recommendations that use the "
        "selected tools together. If the tools look unrelated, invent one "
        "coherent cross-tool workflow from their catalog capabilities. Every "
        "recommendation has a `kind` from `{use_native_ai, "
        "augment_with_custom_ai, consolidate, orchestrate}` and an `effort` "
        "from `{small, medium, large}`. Set a high bar for `use_native_ai` — "
        "only when the native feature is genuinely sufficient with no "
        "augmentation.\n"
        "7. Populate `orchestrator_pr_plan` *if* the Coordinator's "
        "invocation asked you to. This is metadata only — describe the "
        "orchestrator a later invocation will produce. Do not invent env "
        "vars that are not in the root `.env.example`.\n"
        "8. Compute `metadata.stack_file_hash` and stamp "
        "`metadata.generated_at` (ISO 8601 UTC). The Coordinator supplies "
        "`metadata.coordinator_session_id` in the invocation prompt — copy "
        f"it through verbatim. Set `metadata.agent_name` to "
        f"`{role.agent_name}` and `metadata.agent_version` from the value "
        "in the invocation prompt.\n"
        "9. Call `submit_enablement_plan(...)` with the assembled structured "
        "plan. Then your turn ends.\n\n"
        "If `submit_enablement_plan` rejects your submission (schema "
        "validation failed), the error message will tell you what was wrong. "
        "Correct and resubmit. Do not give up and return free-text.\n\n"
        "## What you don't do\n\n"
        "- You do not draft customer-facing copy. That is a runtime "
        "orchestrator's job, in a different invocation.\n"
        "- You do not call external APIs. Demo mode is on by default; the "
        "credentials hook backs this up.\n"
        "- You do not invent tools the catalog doesn't declare. If "
        "`lookup_tool_capability` returns `not_found`, record a capability "
        "`gap` with a note explaining the missing catalog entry rather than "
        "guessing.\n"
        "- You do not deliver free-text reports. The structured "
        "`submit_enablement_plan` call is the contract.\n"
        "- You do not generate orchestrator code. That is "
        "`generate_orchestrator`, a separate invocation.\n\n"
        "## Domain knowledge\n\n"
        f"{domain}"
    )


def role_enablement_agent(role: Role) -> AgentDefinition:
    """Build the SDK AgentDefinition for one role from the registry.

    The definition is registered under `{role.id}_enablement_agent` (see
    `Role.agent_name`). The Coordinator's `Task` tool uses `description`
    to pick among registered agents, so the description includes the
    role's display name, department id, and capability summary.
    """
    return AgentDefinition(
        description=(
            f"Enables AI capabilities for {role.display_name} "
            f"(department `{role.department}`). {role.description.strip()} "
            "Reads the department stack file, gathers per-tool capability "
            "data via lookup_tool_capability, consults domain knowledge, "
            "and produces a structured EnablementPlan."
        ),
        prompt=_build_role_prompt(role),
        tools=[*ROLE_AGENT_BASE_TOOLS, *ROLE_AGENT_MCP_TOOLS],
        mcpServers=ROLE_AGENT_MCP_SERVERS,
        model=resolve_role_agent_model(),
    )


def register_role_agents() -> dict[str, AgentDefinition]:
    """Build `{role.id}_enablement_agent` for every role in the registry.

    Includes support (`support_enablement_agent`) so the historical Task
    name keeps working. One factory — no per-role copy-paste.
    """
    return {role.agent_name: role_enablement_agent(role) for role in list_roles()}
