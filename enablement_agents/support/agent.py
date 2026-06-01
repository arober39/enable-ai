"""Concrete Support Enablement Agent.

`SupportEnablementAgent` is the runtime entry point used for direct invocation
and for tests that don't go through the Coordinator. Production flow runs
through `coordinator.agent.run_coordinator`, which delegates to this agent
via the `Task` tool — that path uses the same `support_enablement_agent`
AgentDefinition (from `definition.py`) but does not call `produce_plan()`
here.

`produce_plan()` exists for two reasons:
  1. Direct testing — exercise the support agent without spinning up a
     Coordinator session.
  2. Future single-agent invocation paths if/when we add CLI entry points
     that bypass routing.

`generate_orchestrator()` is a Phase 5 deliverable; this Phase 4 class
raises NotImplementedError when called.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    SystemMessage,
    query,
)
from claude_agent_sdk.types import HookEvent

from coordinator.agent import _build_submit_tool_and_server
from coordinator.hooks.enforce_credentials import enforce_credentials
from coordinator.hooks.enforce_writes import enforce_writes
from coordinator.hooks.normalize_responses import normalize_responses
from coordinator.schemas import EnablementPlan, OrchestratorRunResult
from enablement_agents.base import EnablementAgentBase, EnablementAgentConfig, StackFile
from enablement_agents.support.definition import (
    SUPPORT_AGENT_BASE_TOOLS,
    SUPPORT_AGENT_MCP_TOOLS,
    SUPPORT_AGENT_NAME,
    SUPPORT_AGENT_SYSTEM_PROMPT,
    SUPPORT_AGENT_VERSION,
    support_enablement_agent,
)
from enablement_agents.support.tools import (
    SUPPORT_MCP_SERVER_NAME,
    build_support_mcp_server,
)

logger = logging.getLogger(__name__)

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]


def default_config() -> EnablementAgentConfig:
    """Build the Support Enablement Agent's default config from the repo layout."""
    return EnablementAgentConfig(
        department="support",
        stack_path=_REPO_ROOT / "stacks" / "support.yaml",
        tool_registry_path=_REPO_ROOT / "tools",
        mcp_registry_path=_REPO_ROOT / "mcp_registry",
        domain_knowledge_path=_REPO_ROOT
        / "enablement_agents"
        / "support"
        / "domain_knowledge.md",
        scratchpad_path=_REPO_ROOT / "agent-state" / f"{SUPPORT_AGENT_NAME}-scratchpad.md",
    )


def _build_hooks() -> dict[HookEvent, list[HookMatcher]]:
    """Same three hooks as the Coordinator — applied to this agent's session too."""
    return {
        "PreToolUse": [
            HookMatcher(hooks=[enforce_credentials]),
            HookMatcher(hooks=[enforce_writes]),
        ],
        "PostToolUse": [
            HookMatcher(hooks=[normalize_responses]),
        ],
    }


class SupportEnablementAgent(EnablementAgentBase):
    """Concrete Enablement Agent for Serenia & Co.'s customer support function."""

    @classmethod
    def default(cls) -> SupportEnablementAgent:
        """Construct with the standard repo-layout config."""
        return cls(default_config())

    @property
    def name(self) -> str:
        return SUPPORT_AGENT_NAME

    @property
    def version(self) -> str:
        return SUPPORT_AGENT_VERSION

    @property
    def agent_definition(self) -> AgentDefinition:
        return support_enablement_agent

    # ------------------------------------------------------------------
    # produce_plan
    # ------------------------------------------------------------------

    def _build_initial_prompt(
        self,
        stack: StackFile,
        coordinator_session_id: str,
    ) -> str:
        """Compose the prompt that kicks off the support agent's plan-production turn.

        Passes every piece of context the subagent needs — paths, identifiers,
        the requested deliverable shape — explicitly. The subagent runs in
        isolated context, so anything not in this prompt is invisible to it.
        """
        tool_names = ", ".join(t.name for t in stack.tools)
        stack_hash = self.stack_file_hash()
        generated_at = datetime.now(UTC).isoformat()

        return (
            "You have been invoked to produce an EnablementPlan for the customer "
            "support department of Serenia & Co.\n\n"
            "## Context paths (read these from disk)\n"
            f"- Stack file: {self.config.stack_path}\n"
            f"- Tool registry directory: {self.config.tool_registry_path}\n"
            f"- MCP registry directory: {self.config.mcp_registry_path}\n"
            f"- Domain knowledge: {self.config.domain_knowledge_path}\n"
            f"- Policies (referenced by orchestrator): "
            f"{_REPO_ROOT / 'data' / 'support' / 'policies.md'}\n\n"
            "## Stack summary (already parsed for you)\n"
            f"- department: {stack.department}\n"
            f"- declared_at: {stack.declared_at}\n"
            f"- tools in stack: {tool_names}\n\n"
            "## Metadata values to stamp into your submitted plan\n"
            f"- metadata.agent_name: {self.name}\n"
            f"- metadata.agent_version: {self.version}\n"
            f"- metadata.coordinator_session_id: {coordinator_session_id}\n"
            f"- metadata.stack_file_hash: {stack_hash}\n"
            f"- metadata.generated_at: {generated_at}\n\n"
            "## Deliverable\n"
            "Produce a complete EnablementPlan and submit it via the "
            "`submit_enablement_plan` MCP tool. Populate the "
            "`orchestrator_pr_plan` field — this invocation is for plan "
            "production *including* the metadata describing the orchestrator "
            "that Phase 5 will later generate. Do NOT generate orchestrator "
            "code in this turn — that is a separate operation.\n\n"
            "Begin by reading the domain knowledge file, then proceed through "
            "the plan production flow described in your system prompt."
        )

    async def produce_plan(self, stack: StackFile) -> EnablementPlan:
        """Run the support agent end-to-end and return the validated plan.

        This is the direct-invocation path. It does not go through the
        Coordinator. Use `coordinator.agent.run_coordinator` for the routed
        flow.

        Args:
            stack: Parsed StackFile (obtain via `self.parse_stack()`). Used
                for prompt assembly; the agent itself re-reads the stack
                file from disk to verify hash.

        Returns:
            Validated EnablementPlan submitted by the agent.

        Raises:
            RuntimeError: If the agent finishes without submitting a plan.
        """
        if stack.department != self.config.department:
            raise ValueError(
                f"Stack file department '{stack.department}' does not match agent "
                f"config department '{self.config.department}'."
            )

        captured: dict[str, EnablementPlan] = {}
        submit_server = _build_submit_tool_and_server(captured)
        support_server = build_support_mcp_server()

        # A synthetic session id for direct invocation. When called via the
        # Coordinator, the Coordinator stamps its own session_id into the
        # invocation prompt.
        synthetic_session_id = f"direct-{self.name}-{datetime.now(UTC).timestamp():.0f}"

        prompt = self._build_initial_prompt(
            stack=stack,
            coordinator_session_id=synthetic_session_id,
        )

        options = ClaudeAgentOptions(
            system_prompt=SUPPORT_AGENT_SYSTEM_PROMPT,
            allowed_tools=[*SUPPORT_AGENT_BASE_TOOLS, *SUPPORT_AGENT_MCP_TOOLS],
            mcp_servers={
                SUPPORT_MCP_SERVER_NAME: support_server,
                "coordinator": submit_server,
            },
            hooks=_build_hooks(),
            cwd=str(_REPO_ROOT),
        )

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, SystemMessage):
                pass
            if isinstance(message, (AssistantMessage, ResultMessage)):
                pass

        if "plan" not in captured:
            raise RuntimeError(
                "Support Enablement Agent finished without submitting a plan. "
                "Check the system prompt and the agent's final turn."
            )
        return captured["plan"]

    # ------------------------------------------------------------------
    # generate_orchestrator (Phase 5)
    # ------------------------------------------------------------------

    async def generate_orchestrator(self, plan: EnablementPlan) -> OrchestratorRunResult:
        """Render the support orchestrator tree under `orchestrators/support/`.

        The Phase 5 implementation is template-driven and deterministic so
        the tutorial-critical constants (event names, AI Config name, the
        one-line v1/v2 prompt diff) are bit-exact. See
        `_orchestrator_generator.py` for details and `BUILD_PLAN.md` Phase
        5 for the spec.

        Args:
            plan: EnablementPlan whose `orchestrator_pr_plan` describes the
                artifact to produce. Must be non-None.

        Returns:
            OrchestratorRunResult enumerating the files written.
        """
        from enablement_agents.support._orchestrator_generator import (
            generate_orchestrator_files,
        )

        output_root = _REPO_ROOT / "orchestrators" / self.config.department
        # Run synchronously inside an async method — the work is filesystem
        # I/O and trivial CPU; no benefit to threadpool here, and it keeps
        # the call signature aligned with the abstract base.
        return generate_orchestrator_files(plan, output_root)


# ---------------------------------------------------------------------------
# Convenience entry point for direct invocation
# ---------------------------------------------------------------------------


async def produce_plan_default() -> EnablementPlan:
    """Construct the default-config Support agent and run produce_plan once."""
    agent = SupportEnablementAgent.default()
    stack = agent.parse_stack()
    return await agent.produce_plan(stack)


if __name__ == "__main__":  # pragma: no cover — manual invocation
    plan = asyncio.run(produce_plan_default())
    print(plan.model_dump_json(indent=2))
