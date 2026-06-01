"""Support Enablement Agent — SDK AgentDefinition.

This module exports `support_enablement_agent: AgentDefinition`, the value
registered in the Coordinator's `ClaudeAgentOptions.agents` dict under the
key `"support_enablement_agent"`. The Coordinator delegates to it via the
`Task` tool.

The AgentDefinition supplies:
  - the support agent's system prompt (loaded from prompts/support_system.md)
  - the constrained tool list (Read/Grep/Glob/Write/Edit + the two MCP tools)
  - a reference to the two MCP servers the agent uses

MCP servers themselves are registered at the parent ClaudeAgentOptions
level (`coordinator/agent.py`); this AgentDefinition just lists the server
names the subagent is allowed to access.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_agent_sdk import AgentDefinition

from coordinator.definition import SUBMIT_PLAN_TOOL_NAME
from enablement_agents.support.tools import (
    LOOKUP_TOOL_QUALIFIED_NAME,
    SUPPORT_MCP_SERVER_NAME,
)

SUPPORT_AGENT_NAME = "support_enablement_agent"
SUPPORT_AGENT_VERSION = "0.1.0"

#: The two MCP servers this subagent reaches into. Names must match the
#: keys used in the parent ClaudeAgentOptions.mcp_servers dict. Typed as
#: list[str | dict[str, Any]] to match AgentDefinition.mcpServers' invariance.
SUPPORT_AGENT_MCP_SERVERS: list[str | dict[str, Any]] = [
    SUPPORT_MCP_SERVER_NAME,   # hosts lookup_tool_capability
    "coordinator",             # hosts submit_enablement_plan
]

#: Built-in Claude Code tools the subagent is allowed to use.
SUPPORT_AGENT_BASE_TOOLS: list[str] = [
    "Read",
    "Grep",
    "Glob",
    "Write",
    "Edit",
]

#: Fully-qualified MCP tool names available to the subagent.
SUPPORT_AGENT_MCP_TOOLS: list[str] = [
    LOOKUP_TOOL_QUALIFIED_NAME,
    SUBMIT_PLAN_TOOL_NAME,
]

_PROMPT_PATH = Path(__file__).parent / "prompts" / "support_system.md"


def _load_system_prompt() -> str:
    text = _PROMPT_PATH.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError(
            f"Support Enablement Agent system prompt at {_PROMPT_PATH} is empty. "
            "This file is required (see BUILD_PLAN.md Phase 4.2)."
        )
    return text


SUPPORT_AGENT_SYSTEM_PROMPT: str = _load_system_prompt()


support_enablement_agent: AgentDefinition = AgentDefinition(
    description=(
        "Enables AI capabilities for customer support functions. Reads the support "
        "stack file, gathers per-tool capability data via lookup_tool_capability, "
        "consults domain knowledge, and produces a structured EnablementPlan. "
        "On a separate invocation (Phase 5), generates the runnable support orchestrator."
    ),
    prompt=SUPPORT_AGENT_SYSTEM_PROMPT,
    tools=[*SUPPORT_AGENT_BASE_TOOLS, *SUPPORT_AGENT_MCP_TOOLS],
    mcpServers=SUPPORT_AGENT_MCP_SERVERS,
)
