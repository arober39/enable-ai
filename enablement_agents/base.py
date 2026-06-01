"""Abstract base class for department-specific Enablement Subagents.

Each Enablement Agent (Support, Marketing, etc.) inherits from
EnablementAgentBase. The base provides:

  - A Pydantic config object pinning the agent's data dependencies (stack,
    tool registry, MCP registry, domain knowledge).
  - Concrete utility methods for reading those data dependencies —
    parse_stack(), lookup_tool_in_registry(), lookup_mcp_in_registry(),
    stack_file_hash() — so concrete subclasses don't reimplement them.
  - Abstract methods (produce_plan, generate_orchestrator) declaring the
    capabilities every concrete agent must support.

Phase 4 implements produce_plan. Phase 5 implements generate_orchestrator.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from claude_agent_sdk import AgentDefinition
from pydantic import BaseModel, ConfigDict, Field

from coordinator.schemas import EnablementPlan, OrchestratorRunResult

# ---------------------------------------------------------------------------
# Stack file model
# ---------------------------------------------------------------------------


class StackTool(BaseModel):
    """One entry in a department's declared stack file (stacks/<dept>.yaml)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Canonical tool name; matches tools/<name>.yaml.")
    primary_use: str = Field(
        description="One-token primary role (e.g., ticketing, knowledge_base)."
    )
    description: str


class StackFile(BaseModel):
    """Parsed view of a stacks/<department>.yaml file."""

    model_config = ConfigDict(extra="forbid")

    department: str
    declared_at: date = Field(description="Date the stack was declared (ISO 8601).")
    tools: list[StackTool]


# ---------------------------------------------------------------------------
# Agent config
# ---------------------------------------------------------------------------


class EnablementAgentConfig(BaseModel):
    """Per-agent data-dependency config.

    Resolved at construction time so the agent always knows where its inputs
    live. Paths are absolute so the agent works regardless of the caller's
    cwd.
    """

    model_config = ConfigDict(extra="forbid")

    department: str
    stack_path: Path = Field(description="Absolute path to stacks/<department>.yaml.")
    tool_registry_path: Path = Field(description="Absolute path to the tools/ directory.")
    mcp_registry_path: Path = Field(description="Absolute path to the mcp_registry/ directory.")
    domain_knowledge_path: Path = Field(
        description="Absolute path to the agent's domain_knowledge.md."
    )
    scratchpad_path: Path = Field(
        description="Absolute path to agent-state/<agent>-scratchpad.md (created on first write)."
    )


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class EnablementAgentBase(ABC):
    """Base class for every department-specific Enablement Agent.

    Concrete subclasses implement `name`, `version`, `agent_definition`,
    `produce_plan`, and `generate_orchestrator`. The base provides shared
    data-access utilities; subclasses do not reimplement YAML parsing or
    registry lookup.
    """

    def __init__(self, config: EnablementAgentConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Identity (abstract)
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable agent name; matches the key under which the agent is registered."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version of this agent. Stamped into produced PlanMetadata."""

    @property
    @abstractmethod
    def agent_definition(self) -> AgentDefinition:
        """The SDK AgentDefinition used when this agent is invoked as a subagent."""

    # ------------------------------------------------------------------
    # Operational surface (abstract)
    # ------------------------------------------------------------------

    @abstractmethod
    async def produce_plan(self, stack: StackFile) -> EnablementPlan:
        """Run the agent end-to-end against `stack` and return the validated plan.

        For tests and direct invocation. Production flow goes through the
        Coordinator's Task delegation — the agent runs the same way, but
        the entry point is the Coordinator session, not this method.
        """

    @abstractmethod
    async def generate_orchestrator(self, plan: EnablementPlan) -> OrchestratorRunResult:
        """Produce the on-disk orchestrator artifact described by `plan`.

        Implementation lands in Phase 5. Concrete agents may raise
        NotImplementedError here until then.
        """

    # ------------------------------------------------------------------
    # Concrete utilities (shared)
    # ------------------------------------------------------------------

    def parse_stack(self) -> StackFile:
        """Parse and validate the department's stack file."""
        raw = yaml.safe_load(self.config.stack_path.read_text(encoding="utf-8"))
        return StackFile.model_validate(raw)

    def stack_file_hash(self) -> str:
        """sha256 of the stack file bytes. Stamped into PlanMetadata."""
        return hashlib.sha256(self.config.stack_path.read_bytes()).hexdigest()

    def lookup_tool_in_registry(self, tool_name: str) -> dict[str, Any] | None:
        """Return parsed tools/<name>.yaml as a dict, or None if missing."""
        path = self.config.tool_registry_path / f"{tool_name}.yaml"
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data

    def lookup_mcp_in_registry(self, tool_name: str) -> dict[str, Any] | None:
        """Return parsed mcp_registry/<name>.yaml as a dict, or None if missing."""
        path = self.config.mcp_registry_path / f"{tool_name}.yaml"
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data

    def read_domain_knowledge(self) -> str:
        """Return the agent's domain knowledge file contents."""
        return self.config.domain_knowledge_path.read_text(encoding="utf-8")

    def append_to_scratchpad(self, note: str) -> None:
        """Append a note to the agent's scratchpad. Creates the file on first write."""
        self.config.scratchpad_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config.scratchpad_path.open("a", encoding="utf-8") as fh:
            fh.write(note.rstrip() + "\n")

    def read_scratchpad(self) -> str:
        """Return the agent's scratchpad contents, or "" if no scratchpad yet."""
        if not self.config.scratchpad_path.exists():
            return ""
        return self.config.scratchpad_path.read_text(encoding="utf-8")

    def clear_scratchpad(self) -> None:
        """Delete the scratchpad file. Useful between runs in tests."""
        if self.config.scratchpad_path.exists():
            self.config.scratchpad_path.unlink()
