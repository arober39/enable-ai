"""Runtime AgentDefinition for the Support Orchestrator.

This is the *runtime* agent that handles customer inquiries at Serenia. It
is distinct from the build-time Support Enablement Agent (which produced
this orchestrator). The Coordinator-side agent does planning; this
orchestrator-side agent does customer-facing work.

In v1 the runtime agent's primary job is intent classification and
response drafting against the AI Config variation served by LaunchDarkly.
The agent definition here is the structured config Claude Agent SDK consumers
can use if they want to wrap the orchestrator in a higher-level agent shell.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

SUPPORT_OPS_AGENT_NAME = "support_ops_agent"
SUPPORT_OPS_AGENT_VERSION = "0.1.0"


SUPPORT_OPS_AGENT_DESCRIPTION = (
    "Runtime customer support agent. Handles inbound inquiries by classifying "
    "intent, retrieving the relevant policy or knowledge base content, and "
    "drafting a brand-voice-consistent reply. Honors the active AI Config "
    "variation served by LaunchDarkly."
)


# The runtime agent's actual reasoning loop is implemented in orchestrator.py;
# this AgentDefinition is the metadata shell, useful for wrapping the
# orchestrator in larger agent compositions later.
support_ops_agent: AgentDefinition = AgentDefinition(
    description=SUPPORT_OPS_AGENT_DESCRIPTION,
    prompt=(
        "You are the runtime support agent. Your concrete behavior is "
        "implemented in orchestrator.py; this prompt is a fallback for "
        "interactive sessions that hit this AgentDefinition directly. "
        "Read prompts/v1_baseline.md and policies.md before answering."
    ),
    tools=["Read", "Grep", "Glob"],
)
