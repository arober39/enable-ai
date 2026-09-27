"""Agent Architect: what to supervise, not another place to build an agent.

The occupational list is a first pass. A modern job-description pattern is
the second. The tasks the person keeps are the job that outranks both.

Full O*NET ingest is deferred. Developer Advocate / DevRel is the catalog
that is filled in by hand. Other roles get a short list from their
capability phrases.

LaunchDarkly autonomy flags (L0 recommend through L4 orchestrate) are named
here and not evaluated. Wiring agent-research, agent-github-write,
agent-notion-create, and agent-autonomous-execution is deferred.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.plan_grounding import workflow_action
from core.roles import Role, load_role
from core.tool_catalog import ToolCapability

Classification = Literal["AUTOMATE", "ASSIST", "AGENTIC", "HUMAN"]
HitlKind = Literal["direct", "review", "approve", "exception"]
TaskSource = Literal["occupational", "job_description", "actual"]
SupervisionPotential = Literal["low", "moderate", "high"]

#: Named for a later guarded rollout. Not read by the flag client in this MVP.
AUTONOMY_FLAGS: tuple[str, ...] = (
    "agent-research",
    "agent-github-write",
    "agent-notion-create",
    "agent-autonomous-execution",
)

_AUTONOMY_NOTE = (
    "Progressive autonomy runs from L0 recommend to L4 orchestrate. "
    "Flags agent-research, agent-github-write, agent-notion-create, and "
    "agent-autonomous-execution are reserved and not wired in this demo."
)


class TaskSignal(BaseModel):
    """Scores that decide automate, assist, agent, or human."""

    model_config = ConfigDict(extra="forbid")

    frequency: Literal["rare", "weekly", "daily"]
    repetition: Literal["low", "medium", "high"]
    judgment: Literal["low", "medium", "high"]
    risk: Literal["low", "medium", "high"]
    permissions: Literal["read", "draft", "write"]
    context: Literal["single_tool", "multi_tool"]
    reversibility: Literal["easy", "costly", "irreversible"]


class WorkTask(BaseModel):
    """One thing a person might actually do."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    detail: str
    source: TaskSource
    signals: TaskSignal


class TaskSelection(BaseModel):
    """A task the person confirmed. Actual tasks they added have no catalog id."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    source: TaskSource = "actual"


class TaskAssessment(BaseModel):
    """One task after automation reasoning."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    label: str
    source: TaskSource
    signals: TaskSignal
    classification: Classification
    why: str
    deterministic_preferred: bool
    supervision_potential: SupervisionPotential
    hitl: HitlKind
    ai_steps: str
    human_steps: str


class BuildTarget(BaseModel):
    """A system this product feeds. Not a runtime this product replaces."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    recommended: bool
    why: str


class AgentBlueprint(BaseModel):
    """What agent to build, and how the person supervises it."""

    model_config = ConfigDict(extra="forbid")

    supervision_shift: str
    current_workflow: str
    pain_points: list[str]
    trigger: str
    agent_responsibilities: list[str]
    tools: list[str]
    autonomous_actions: list[str]
    human_in_the_loop: list[str]
    architecture: str
    assessments: list[TaskAssessment]
    build_targets: list[BuildTarget]
    autonomy_flags: list[str] = Field(default_factory=lambda: list(AUTONOMY_FLAGS))
    autonomy_note: str = _AUTONOMY_NOTE


def _signal(
    *,
    frequency: Literal["rare", "weekly", "daily"],
    repetition: Literal["low", "medium", "high"],
    judgment: Literal["low", "medium", "high"],
    risk: Literal["low", "medium", "high"],
    permissions: Literal["read", "draft", "write"],
    context: Literal["single_tool", "multi_tool"],
    reversibility: Literal["easy", "costly", "irreversible"],
) -> TaskSignal:
    return TaskSignal(
        frequency=frequency,
        repetition=repetition,
        judgment=judgment,
        risk=risk,
        permissions=permissions,
        context=context,
        reversibility=reversibility,
    )


#: DevRel is the first role filled in as an occupational pass plus JD patterns.
#: Not a live O*NET download.
_DEVREL_TASKS: tuple[WorkTask, ...] = (
    WorkTask(
        id="content_research",
        label="Content research",
        detail=(
            "Occupational first pass: gather what practitioners are asking and "
            "update what you know. Confirm you still do this before an agent collects it."
        ),
        source="occupational",
        signals=_signal(
            frequency="weekly",
            repetition="high",
            judgment="medium",
            risk="low",
            permissions="read",
            context="multi_tool",
            reversibility="easy",
        ),
    ),
    WorkTask(
        id="community_intelligence",
        label="Community intelligence",
        detail=(
            "Occupational first pass: monitor community channels and cluster themes. "
            "The useful version joins a Discord thread to the GitHub issue it is about."
        ),
        source="occupational",
        signals=_signal(
            frequency="daily",
            repetition="high",
            judgment="medium",
            risk="low",
            permissions="read",
            context="multi_tool",
            reversibility="easy",
        ),
    ),
    WorkTask(
        id="sample_verification",
        label="Verify a demo still runs",
        detail=(
            "Occupational first pass: check work for errors. Re-run a sample against "
            "the API. This is repetition, not judgment."
        ),
        source="occupational",
        signals=_signal(
            frequency="daily",
            repetition="high",
            judgment="low",
            risk="low",
            permissions="read",
            context="single_tool",
            reversibility="easy",
        ),
    ),
    WorkTask(
        id="demo_creation",
        label="Demo creation",
        detail=(
            "Modern DevRel job descriptions ask for runnable demos. Drafting can be "
            "assisted. Proving the sample runs is a fixed check, not an agent."
        ),
        source="job_description",
        signals=_signal(
            frequency="weekly",
            repetition="medium",
            judgment="high",
            risk="medium",
            permissions="draft",
            context="multi_tool",
            reversibility="costly",
        ),
    ),
    WorkTask(
        id="release_enablement",
        label="Product-release enablement",
        detail=(
            "Modern JDs ask DevRel to turn a release into notes, samples, and a "
            "community post. Publishing stays an approval."
        ),
        source="job_description",
        signals=_signal(
            frequency="weekly",
            repetition="medium",
            judgment="medium",
            risk="medium",
            permissions="draft",
            context="multi_tool",
            reversibility="costly",
        ),
    ),
    WorkTask(
        id="event_prep",
        label="Event prep",
        detail=(
            "Modern JDs ask for talk outlines and demo scripts. The angle is a "
            "judgment you keep. An assistant can assemble the brief."
        ),
        source="job_description",
        signals=_signal(
            frequency="rare",
            repetition="low",
            judgment="high",
            risk="low",
            permissions="draft",
            context="single_tool",
            reversibility="easy",
        ),
    ),
    WorkTask(
        id="public_reply",
        label="Send the public reply",
        detail=(
            "A public community reply is hard to undo. Job descriptions mention "
            "community engagement. You still send it."
        ),
        source="job_description",
        signals=_signal(
            frequency="daily",
            repetition="high",
            judgment="high",
            risk="high",
            permissions="write",
            context="multi_tool",
            reversibility="irreversible",
        ),
    ),
)


def tasks_for_role(role: Role) -> list[WorkTask]:
    """Baseline tasks for a role. DevRel is the detailed catalog."""
    if role.id == "devrel":
        return list(_DEVREL_TASKS)
    tasks: list[WorkTask] = []
    for index, phrase in enumerate(role.capabilities[:5]):
        tasks.append(
            WorkTask(
                id=f"{role.id}-{index}",
                label=phrase.strip(),
                detail=(
                    "From this role's capability list, treated as a job-description "
                    "pattern. Uncheck it if it is not work you actually do."
                ),
                source="job_description",
                signals=_signal(
                    frequency="weekly",
                    repetition="medium",
                    judgment="medium",
                    risk="low",
                    permissions="draft",
                    context="multi_tool",
                    reversibility="easy",
                ),
            )
        )
    return tasks


def tasks_for_role_id(role_id: str) -> list[WorkTask]:
    """Load a seeded role and return its baseline tasks."""
    return tasks_for_role(load_role(role_id))


def compile_blueprint(
    *,
    role: Role,
    capabilities: list[ToolCapability],
    selected_tasks: list[TaskSelection] | None,
    friction: str = "",
) -> AgentBlueprint:
    """Build the blueprint from confirmed tasks and the selected tools."""
    catalog = {task.id: task for task in tasks_for_role(role)}
    chosen = _resolve_tasks(catalog, selected_tasks)
    assessments = [_assess(task, capabilities) for task in chosen]
    vendors = [cap.vendor for cap in capabilities]
    tool_ids = [cap.canonical_name for cap in capabilities]
    return AgentBlueprint(
        supervision_shift=_supervision_shift(role, assessments),
        current_workflow=_current_workflow(role, chosen, vendors),
        pain_points=_pain_points(capabilities, assessments, friction),
        trigger=_trigger(vendors),
        agent_responsibilities=_responsibilities(role, capabilities, assessments),
        tools=tool_ids,
        autonomous_actions=[
            item.ai_steps for item in assessments if item.classification != "HUMAN"
        ],
        human_in_the_loop=[item.human_steps for item in assessments],
        architecture=_architecture(vendors, assessments),
        assessments=assessments,
        build_targets=_build_targets(capabilities, assessments),
    )


def _resolve_tasks(
    catalog: dict[str, WorkTask],
    selected: list[TaskSelection] | None,
) -> list[WorkTask]:
    if selected is None:
        return list(catalog.values())
    resolved: list[WorkTask] = []
    for item in selected:
        known = catalog.get(item.id)
        if known is not None:
            resolved.append(known)
            continue
        resolved.append(
            WorkTask(
                id=item.id,
                label=item.label.strip() or item.id,
                detail="Added from the person's actual job. It outranks the baseline lists.",
                source="actual",
                signals=_signal(
                    frequency="weekly",
                    repetition="medium",
                    judgment="medium",
                    risk="low",
                    permissions="draft",
                    context="multi_tool",
                    reversibility="easy",
                ),
            )
        )
    return resolved


def _assess(task: WorkTask, capabilities: list[ToolCapability]) -> TaskAssessment:
    classification, deterministic, hitl, why = _classify(task, len(capabilities))
    vendors = _vendor_phrase(capabilities)
    if classification == "AUTOMATE":
        ai_steps = f"Run a fixed check for {task.label} in {vendors}."
        human_steps = "Step in only when the check fails."
    elif classification == "HUMAN":
        ai_steps = f"Assemble context for {task.label}. Do not take the action."
        human_steps = f"You {task.label.lower()} yourself."
    elif classification == "AGENTIC":
        ai_steps = (
            f"Read across {vendors}, combine the result, and prepare {task.label}."
        )
        human_steps = "You review or approve before anything public or hard to undo."
    else:
        ai_steps = f"Draft {task.label} from {vendors} for you to steer."
        human_steps = "You keep the judgment and approve what leaves the team."
    if deterministic and classification != "AUTOMATE":
        ai_steps += " Verify with a deterministic workflow, not a second agent."
    return TaskAssessment(
        task_id=task.id,
        label=task.label,
        source=task.source,
        signals=task.signals,
        classification=classification,
        why=why,
        deterministic_preferred=deterministic,
        supervision_potential=_potential(classification),
        hitl=hitl,
        ai_steps=ai_steps,
        human_steps=human_steps,
    )


def _classify(
    task: WorkTask,
    tool_count: int,
) -> tuple[Classification, bool, HitlKind, str]:
    signals = task.signals
    if signals.risk == "high" and (
        signals.reversibility == "irreversible" or signals.judgment == "high"
    ):
        return (
            "HUMAN",
            False,
            "exception",
            "Risk and irreversibility stay with you. An agent may gather context. "
            "It does not take this action.",
        )
    if (
        signals.repetition == "high"
        and signals.judgment == "low"
        and signals.risk == "low"
        and signals.reversibility == "easy"
    ):
        return (
            "AUTOMATE",
            True,
            "exception",
            "This is frequent, repetitive, and easy to undo. Use a deterministic "
            "workflow. An agent would invent judgment this step does not need.",
        )
    if (
        signals.permissions == "draft"
        and signals.risk == "medium"
        and signals.judgment == "high"
    ):
        return (
            "ASSIST",
            True,
            "approve",
            "An assistant drafts. A deterministic check runs before anything is "
            "published. You approve the public result. Do not hand publish rights "
            "to an agent.",
        )
    if (
        signals.context == "multi_tool"
        and tool_count >= 2
        and signals.judgment != "high"
        and signals.risk != "high"
    ):
        hitl: HitlKind = (
            "approve"
            if signals.risk == "medium" or signals.reversibility == "costly"
            else "review"
        )
        return (
            "AGENTIC",
            False,
            hitl,
            "The work crosses the selected tools and needs a bounded agent. "
            "You supervise the result instead of collecting it by hand.",
        )
    if signals.judgment == "high":
        return (
            "ASSIST",
            False,
            "direct",
            "You keep the judgment. An assistant prepares the brief you steer.",
        )
    return (
        "ASSIST",
        False,
        "review",
        "An assistant can prepare this. You review the result before it is used.",
    )


def _potential(classification: Classification) -> SupervisionPotential:
    if classification in {"AUTOMATE", "AGENTIC"}:
        return "high"
    if classification == "ASSIST":
        return "moderate"
    return "low"


def _vendor_phrase(capabilities: list[ToolCapability]) -> str:
    vendors = [cap.vendor for cap in capabilities]
    if not vendors:
        return "the tools you add"
    if len(vendors) == 1:
        return vendors[0]
    if len(vendors) == 2:
        return f"{vendors[0]} and {vendors[1]}"
    return ", ".join(vendors[:-1]) + f", and {vendors[-1]}"


def _supervision_shift(role: Role, assessments: list[TaskAssessment]) -> str:
    high = [item.label for item in assessments if item.supervision_potential == "high"]
    if not assessments:
        return (
            f"No tasks are confirmed for {role.display_name}. "
            "Add the work you actually do before designing what you would supervise."
        )
    if not high:
        focus = "the drafts an assistant prepares"
    elif len(high) == 1:
        focus = high[0]
    else:
        focus = ", ".join(high[:-1]) + f", and {high[-1]}"
    return (
        f"Supervision potential is highest on {focus}. "
        "That recovers execution time for higher-leverage work: the judgment, "
        "the relationship, and the decisions only you should make. "
        f"A {role.display_name} moves from worker to operator to supervisor. "
        "You keep the judgment those steps still need."
    )


def _current_workflow(
    role: Role,
    tasks: list[WorkTask],
    vendors: list[str],
) -> str:
    if not tasks:
        return f"A {role.display_name} has not confirmed which tasks are actually theirs."
    labels = ", ".join(task.label for task in tasks)
    if not vendors:
        return f"Today a {role.display_name} does {labels} by hand."
    return (
        f"Today a {role.display_name} does {labels} by hand across "
        f"{_vendor_phrase_from_names(vendors)}."
    )


def _vendor_phrase_from_names(vendors: list[str]) -> str:
    if len(vendors) == 1:
        return vendors[0]
    if len(vendors) == 2:
        return f"{vendors[0]} and {vendors[1]}"
    return ", ".join(vendors[:-1]) + f", and {vendors[-1]}"


def _pain_points(
    capabilities: list[ToolCapability],
    assessments: list[TaskAssessment],
    friction: str,
) -> list[str]:
    points: list[str] = []
    cleaned = " ".join(friction.split())
    if cleaned:
        points.append(cleaned)
    if len(capabilities) >= 2:
        points.append(
            f"The same facts are retyped across {_vendor_phrase(capabilities)} "
            "instead of one supervised handoff."
        )
    for item in assessments:
        if item.classification == "AUTOMATE":
            points.append(
                f"{item.label} is still manual even though a fixed check could run it."
            )
        if item.classification == "HUMAN":
            points.append(f"{item.label} stays manual because it is hard to undo.")
    if not points:
        points.append("The baseline lists do not name a friction yet. Add one in your own words.")
    return points


def _trigger(vendors: list[str]) -> str:
    if not vendors:
        return "Start when work you kept shows up and a tool can see it."
    return (
        f"Start when {_vendor_phrase_from_names(vendors)} changes in a way that "
        "matches a task you kept: a thread, an issue, a release, or a demo to recheck."
    )


def _responsibilities(
    role: Role,
    capabilities: list[ToolCapability],
    assessments: list[TaskAssessment],
) -> list[str]:
    lines: list[str] = []
    if len(capabilities) >= 2:
        steps = [
            f"use {cap.vendor} to {workflow_action(cap)}" for cap in capabilities
        ]
        lines.append(
            "Combine the selected tools in one supervised workflow: "
            + "; then ".join(steps)
            + ". Pass the output of each tool into the next."
        )
    for item in assessments:
        if item.classification == "AUTOMATE":
            lines.append(
                f"Do not assign {item.label} to an agent. Run it as a deterministic workflow."
            )
        elif item.classification == "HUMAN":
            lines.append(f"Do not automate {item.label}. Prepare context only.")
        elif item.classification == "AGENTIC":
            lines.append(f"A bounded agent prepares {item.label}. You supervise it.")
        else:
            lines.append(f"An assistant drafts {item.label}. You steer it.")
    if not lines:
        lines.append(
            f"No agent yet. Confirm the {role.display_name} tasks you actually do."
        )
    return lines


def _architecture(vendors: list[str], assessments: list[TaskAssessment]) -> str:
    tool_count = len(vendors) if vendors else 0
    agentic = sum(1 for item in assessments if item.classification == "AGENTIC")
    automate = sum(1 for item in assessments if item.deterministic_preferred)
    return (
        f"One orchestrator sequences the run across {tool_count} tool"
        f"{'s' if tool_count != 1 else ''}. "
        f"{agentic} bounded agent step{'s' if agentic != 1 else ''} sit under it. "
        f"{automate} step{'s' if automate != 1 else ''} stay deterministic workflows "
        "where a fixed check is the better fit. Human and assist steps stop for you. "
        "You design what you supervise, then build it in the system you choose."
    )


def _build_targets(
    capabilities: list[ToolCapability],
    assessments: list[TaskAssessment],
) -> list[BuildTarget]:
    needs_agent = any(
        item.classification in {"AGENTIC", "ASSIST"} for item in assessments
    )
    needs_workflow = any(item.deterministic_preferred for item in assessments)
    needs_mcp = any(not cap.mcp_server.available for cap in capabilities) or not capabilities
    missing = [
        cap.vendor for cap in capabilities if not cap.mcp_server.available
    ]
    if missing:
        mcp_why = (
            "Describe a custom MCP server for "
            + _vendor_phrase_from_names(missing)
            + ". The catalog has no server for it yet."
        )
    else:
        mcp_why = "Choose custom MCP when a tool you add has no server yet."
    specs: tuple[tuple[str, str, bool, str], ...] = (
        (
            "openai_agents",
            "OpenAI Agents SDK",
            needs_agent,
            "Feed a bounded agent that drafts or combines tools.",
        ),
        (
            "claude",
            "Claude",
            needs_agent,
            "Feed drafting and cross-tool reading. Tools stay the system of record.",
        ),
        (
            "langgraph",
            "LangGraph",
            needs_agent or len(capabilities) >= 2,
            "Feed the orchestrator-plus-agents graph, including review stops.",
        ),
        (
            "n8n",
            "n8n",
            needs_workflow,
            "Feed fixed steps here when a deterministic workflow is the better fit.",
        ),
        (
            "copilot_studio",
            "Copilot Studio",
            False,
            "Choose this when operators already work in Copilot Studio.",
        ),
        (
            "zapier",
            "Zapier",
            needs_workflow,
            "Feed a trigger-and-action handoff when the step is not a judgment.",
        ),
        (
            "custom_mcp",
            "Custom MCP",
            needs_mcp,
            mcp_why,
        ),
    )
    return [
        BuildTarget(id=target_id, label=label, recommended=recommended, why=why)
        for target_id, label, recommended, why in specs
    ]
