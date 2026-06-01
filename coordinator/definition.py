"""Coordinator AgentDefinition.

The Coordinator is the top-level agent of Enable AI. This module defines its
identity — name, version, description, system prompt, allowed tools — as a
single `AgentDefinition`. The actual runtime is assembled in `agent.py` by
combining this definition with `ClaudeAgentOptions` (which carries hooks,
subagent registrations, mcp_servers, etc.).

Separating the *definition* (what the agent is) from the *runtime* (how it is
executed in a given session) lets us test the Coordinator's identity without
spinning up an SDK session.
"""

from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import AgentDefinition

COORDINATOR_NAME = "coordinator"
COORDINATOR_VERSION = "0.1.0"

# Default toolset for the Coordinator. The Coordinator delegates to subagents
# via `Task`; reads/writes structured artifacts via Read/Write/Edit/Glob/Grep;
# may shell out via Bash for narrow lifecycle tasks. The enforce_credentials
# and enforce_writes hooks (registered in `agent.py`) bound what Bash and
# Write/Edit can actually do.
COORDINATOR_TOOLS: list[str] = [
    "Task",
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
]

# The `submit_enablement_plan` SDK MCP tool that captures the final structured
# output. Created and registered in `agent.py`. The Coordinator's full
# `allowed_tools` list (passed to ClaudeAgentOptions at runtime) extends
# COORDINATOR_TOOLS with this MCP tool name.
SUBMIT_PLAN_TOOL_NAME = "mcp__coordinator__submit_enablement_plan"

_PROMPT_PATH = Path(__file__).parent / "prompts" / "coordinator_system.md"


def _load_system_prompt() -> str:
    """Read the Coordinator's system prompt from disk.

    Read at import time so any missing/empty file fails fast. The prompt is
    not constructed dynamically — it is a checked-in artifact.
    """
    text = _PROMPT_PATH.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError(
            f"Coordinator system prompt at {_PROMPT_PATH} is empty. "
            "This file is required (see BUILD_PLAN.md Phase 3.1)."
        )
    return text


COORDINATOR_SYSTEM_PROMPT: str = _load_system_prompt()

#: The Coordinator's AgentDefinition. `prompt` is the SDK's field for the
#: system prompt; `tools` is its allowed-tools list. (These are the official
#: field names on AgentDefinition in claude-agent-sdk 0.1.81.)
coordinator_definition: AgentDefinition = AgentDefinition(
    description=(
        "Routes inbound enablement requests across specialized Enablement Subagents. "
        "Never produces orchestrator code directly — delegation only. "
        "Final output is always a structured EnablementPlan."
    ),
    prompt=COORDINATOR_SYSTEM_PROMPT,
    tools=[*COORDINATOR_TOOLS, SUBMIT_PLAN_TOOL_NAME],
)
