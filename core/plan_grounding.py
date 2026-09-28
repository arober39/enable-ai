"""Findings and recommendations grounded in the selected tools.

The role says who the workflow is for. The tool catalog says what the
workflow can do. A DevRel playbook about tutorials and code samples must
not be reused when the selected tools are travel, expense, or email.

Demo plans are built from this module. Live plans that still recite role
themes the catalog does not support are replaced with the same output.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from coordinator.schemas import (
    CapabilityFinding,
    EnablementPlan,
    Recommendation,
    ResearchSource,
)
from core.credentials import Credentials
from core.jev import classify_coverage
from core.roles import Role
from core.tool_catalog import ToolCapability

logger = logging.getLogger(__name__)

#: Shared planner instructions for relationship findings, a richer
#: recommendation set, and catalog-backed research. Role agents and the
#: UI live runner both include this text.
CROSS_TOOL_PLAN_INSTRUCTIONS = (
    "When two or more tools are selected, lead capability_coverage with "
    "relationship findings before any single-tool finding. Set focus to "
    '"relationship" and tools_involved to every selected tool id. In notes, '
    "explain how those tools relate, how to combine them, and a concrete "
    "numbered workflow that uses all of them for this role. Then add one "
    'focus "tool" finding per tool.\n\n'
    "Produce a rich recommendation list, not a single item. Include an "
    "orchestrate recommendation for the combined workflow, a second "
    "recommendation that sequences the handoff between the tools, "
    "use_native_ai when a catalog native feature is enough on its own, and "
    "consolidate when two selected tools cover the same category.\n\n"
    "Integrating Claude is appropriate when catalog notes show a tool's "
    "native AI cannot see the other selected tools, or when none of the "
    "selected tools has a native model. Moving idea generation to ChatGPT "
    "or OpenAI is appropriate when this role works on content, community, "
    "or campaigns and a selected tool is a community, content, docs, or "
    "campaign surface. Omit the Claude and ChatGPT recommendations when the "
    "catalog and the role do not support them.\n\n"
    "Every recommendation must include research: a list of objects with "
    "title, evidence, and source. Evidence quotes or paraphrases the tool "
    "catalog (notes, native feature, API, or MCP) so the recommendation is "
    "documented and doable.\n"
)

_Status = Literal["covered", "partial", "gap", "redundant"]
_Kind = Literal["use_native_ai", "augment_with_custom_ai", "consolidate", "orchestrate"]

#: Category token -> work that token can support. Matched against catalog
#: categories, not against a role playbook. Unknown categories fall through
#: to the tool's own notes.
_CATEGORY_ACTIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("travel", "trip", "itinerary", "booking"),
        "track upcoming trips, remind people before departure, and surface itinerary changes",
    ),
    (
        ("expense", "spend", "receipt", "reimbursement"),
        "remind people to submit expense reports and draft them from receipts, "
        "card charges, or a connected bank feed",
    ),
    (
        ("email", "inbox", "mail"),
        "send reminders and read the email those workflows need",
    ),
    (
        ("calendar", "scheduling"),
        "watch the calendar and remind people before events",
    ),
    (
        ("crm", "customer"),
        "read account context and keep the customer record current",
    ),
    (
        ("ticket", "helpdesk", "support"),
        "triage incoming requests and draft the next reply from the record",
    ),
    (
        ("chat", "messaging", "collaboration", "handoff"),
        "post the update to the team channel that owns the work",
    ),
    (
        ("knowledge", "documentation", "docs"),
        "search and update the knowledge the workflow relies on",
    ),
    (
        ("source", "code", "repository"),
        "read the repository changes the workflow needs to cite",
    ),
    (
        ("issue", "jira", "tracker", "backlog"),
        "track the work item, update its status, and record who owns it",
    ),
    (
        ("marketing", "campaign"),
        "prepare the campaign message the workflow should send",
    ),
    (
        ("analytics", "attribution"),
        "pull the performance numbers the workflow should report",
    ),
    (
        ("community", "forum"),
        "read the community threads the workflow should answer",
    ),
    (
        ("billing", "payment", "invoice", "bank"),
        "check invoices, payments, or the bank feed the workflow should follow up on",
    ),
)

_STOP_WORDS = frozenset(
    {
        "and",
        "with",
        "the",
        "for",
        "from",
        "that",
        "this",
        "into",
        "over",
        "your",
        "their",
        "than",
        "then",
        "only",
        "when",
        "what",
        "work",
        "using",
        "use",
        "based",
        "role",
        "each",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

#: Unigrams that show up in ordinary plan prose and in role titles. Bigrams
#: built from the same capability phrases are still checked.
_GENERIC_UNIGRAMS = frozenset(
    {
        "analysis",
        "content",
        "developer",
        "issue",
        "recommendation",
        "recommendations",
        "source",
        "survey",
    }
)


def catalog_corpus(capabilities: list[ToolCapability]) -> str:
    """Lowercased catalog text for the selected tools."""
    parts: list[str] = []
    for cap in capabilities:
        parts.append(cap.canonical_name)
        parts.append(cap.vendor)
        parts.extend(cap.categories)
        if cap.notes:
            parts.append(cap.notes)
        for feature in cap.native_ai_features:
            parts.append(feature.name)
            parts.append(feature.description)
    return " ".join(parts).lower()


#: Broad families. Used only when no more specific category matched, so a
#: code tool is not described as a team chat channel.
_GENERIC_ACTION_PHRASES = frozenset(
    {
        "post the update to the team channel that owns the work",
        "read account context and keep the customer record current",
    }
)


def workflow_action(cap: ToolCapability) -> str:
    """One clause of work this tool's catalog says it can do."""
    tokens = _category_tokens(cap)
    specific: list[str] = []
    generic: list[str] = []
    for keys, phrase in _CATEGORY_ACTIONS:
        if not _keys_match(tokens, keys):
            continue
        bucket = generic if phrase in _GENERIC_ACTION_PHRASES else specific
        if phrase not in bucket:
            bucket.append(phrase)
    phrases = (specific or generic)[:2]
    if phrases:
        if len(phrases) == 1:
            return phrases[0]
        return ", and ".join(phrases)
    if cap.notes:
        sentence = cap.notes.strip().split(".", 1)[0].strip()
        if sentence:
            return sentence[0].lower() + sentence[1:] if sentence[0].isupper() else sentence
    if cap.native_ai_features:
        description = cap.native_ai_features[0].description.strip()
        if description:
            return description
    if cap.categories:
        readable = ", ".join(category.replace("_", " ") for category in cap.categories)
        return f"carry out its {readable} work"
    return f"carry out the work {cap.vendor} is used for"


def capability_label(cap: ToolCapability) -> str:
    """Short finding name taken from the tool, not the role checklist."""
    if cap.categories:
        return cap.categories[0].replace("_", " ")
    return f"{cap.vendor} workflow"


def relationship_findings(
    capabilities: list[ToolCapability],
    role: Role,
) -> list[CapabilityFinding]:
    """How the selected tools relate, and one workflow that uses all of them."""
    if len(capabilities) < 2:
        return []
    names = [cap.canonical_name for cap in capabilities]
    title = _name_list([cap.vendor for cap in capabilities])
    return [
        CapabilityFinding(
            capability=f"How {title} work together",
            status="partial",
            tools_involved=names,
            notes=_how_tools_relate(capabilities, role),
            focus="relationship",
        ),
        CapabilityFinding(
            capability=f"Workflow using {title}",
            status="partial",
            tools_involved=names,
            notes=_combined_workflow(capabilities, role),
            focus="relationship",
        ),
    ]


def grounded_findings(
    capabilities: list[ToolCapability],
    *,
    missing: list[str] | None = None,
    creds: Credentials | None = None,
    role: Role | None = None,
) -> list[CapabilityFinding]:
    """Relationship findings first, then one finding per selected tool."""
    findings: list[CapabilityFinding] = []
    if role is not None:
        findings.extend(relationship_findings(capabilities, role))
    names = [cap.canonical_name for cap in capabilities]
    for tool_name in missing or []:
        findings.append(
            CapabilityFinding(
                capability="catalog_lookup",
                status="gap",
                tools_involved=[tool_name],
                notes=(
                    f"No catalog entry for '{tool_name}'. Research the tool "
                    "before recommending a workflow for it."
                ),
            )
        )
    for cap in capabilities:
        others = [name for name in names if name != cap.canonical_name]
        judged = classify_coverage(
            tool_name=cap.canonical_name,
            categories=list(cap.categories),
            capability=capability_label(cap),
            other_tools=others,
            creds=creds,
        )
        action = workflow_action(cap)
        source = f"Judged by {judged['source']} ({judged['mode']})."
        catalog_note = (cap.notes or "").strip()
        notes = f"{action}.\n{source}"
        if catalog_note:
            notes = f"{catalog_note}\n{notes}"
        findings.append(
            CapabilityFinding(
                capability=capability_label(cap),
                status=_as_status(judged.get("status")),
                tools_involved=[cap.canonical_name],
                notes=notes.strip(),
                focus="tool",
            )
        )
    return findings


def grounded_recommendations(
    capabilities: list[ToolCapability],
    role: Role,
) -> list[Recommendation]:
    """Recommendations that name the selected tools and their catalog work."""
    if not capabilities:
        return []
    recs: list[Recommendation] = []
    names = [cap.canonical_name for cap in capabilities]
    kind = _workflow_kind(capabilities)
    effort: Literal["small", "medium", "large"] = (
        "small" if kind == "use_native_ai" else "medium"
    )
    _push(
        recs,
        Recommendation(
            id="R-001",
            kind=kind,
            description=_workflow_description(capabilities, role),
            tools_affected=names,
            effort=effort,
            notes="Runs the selected tools as one job.",
            research=_research_sources(
                capabilities,
                why=(
                    "Each selected tool can "
                    f"{_research_why_actions(capabilities)}. "
                    "Hand the result of one step to the next tool instead of treating "
                    "them as separate lists."
                ),
            ),
        ),
    )
    if len(capabilities) >= 2:
        _push(
            recs,
            Recommendation(
                id="R-000",
                kind="orchestrate",
                description=_handoff_description(capabilities, role),
                tools_affected=names,
                effort="medium",
                notes="Sequences the handoff so every selected tool is used.",
                research=_research_sources(
                    capabilities,
                    why=(
                        "The catalog gives each tool a distinct action. The workflow "
                        "is feasible because those actions can be called in order and "
                        "the last step writes the outcome back to the first tool."
                    ),
                ),
            ),
        )
    if claude_integration_fits(capabilities):
        _push(
            recs,
            Recommendation(
                id="R-000",
                kind="augment_with_custom_ai",
                description=_claude_description(capabilities, role),
                tools_affected=names,
                effort="medium",
                notes="Claude is the reasoning step. The selected tools stay the system of record.",
                research=_research_sources(
                    capabilities,
                    why=(
                        "Catalog notes show these tools' own AI cannot see the rest of "
                        "the stack. Claude can read the records their APIs already expose "
                        "and write the result back."
                    ),
                ),
            ),
        )
    if idea_generation_fits(capabilities, role):
        surfaces = [cap for cap in capabilities if _is_idea_surface(cap)]
        _push(
            recs,
            Recommendation(
                id="R-000",
                kind="augment_with_custom_ai",
                description=_chatgpt_description(capabilities, role, surfaces),
                tools_affected=names,
                effort="medium",
                notes="ChatGPT proposes options. Publishing stays in the selected tools.",
                research=_research_sources(
                    surfaces or capabilities,
                    why=(
                        "The role works with content, community, or campaigns, and the "
                        "catalog marks at least one selected tool as that kind of surface. "
                        "Idea generation can move to ChatGPT without replacing the tools "
                        "that store the work."
                    ),
                ),
            ),
        )
    overlap = _overlapping_tools(capabilities)
    if len(overlap) >= 2:
        _push(
            recs,
            Recommendation(
                id="R-000",
                kind="consolidate",
                description=_consolidate_description(overlap, role),
                tools_affected=[cap.canonical_name for cap in overlap],
                effort="large",
                notes="These tools cover the same catalog category.",
                research=_research_sources(
                    overlap,
                    why=(
                        "Their categories overlap, so one of them can remain the system "
                        "of record while the other becomes an input."
                    ),
                ),
            ),
        )
    missing_mcp = [cap for cap in capabilities if not cap.mcp_server.available]
    workflow_already_covers_stubs = kind == "augment_with_custom_ai" and len(
        missing_mcp
    ) == len(capabilities)
    if missing_mcp and not workflow_already_covers_stubs:
        _push(
            recs,
            Recommendation(
                id="R-000",
                kind="augment_with_custom_ai",
                description=_stub_description(missing_mcp, role),
                tools_affected=[cap.canonical_name for cap in missing_mcp],
                effort="medium",
                notes="No vendor-maintained MCP server for these tools yet.",
                research=_research_sources(
                    missing_mcp,
                    why=(
                        "The catalog marks these tools as having no MCP server. A minimal "
                        "stub can still call the API the catalog already records."
                    ),
                ),
            ),
        )
    if not (kind == "use_native_ai" and len(capabilities) == 1):
        for cap in capabilities:
            if not cap.native_ai_features:
                continue
            feature = cap.native_ai_features[0]
            _push(
                recs,
                Recommendation(
                    id="R-000",
                    kind="use_native_ai",
                    description=(
                        f"Use {cap.vendor}'s {feature.name} on {cap.canonical_name} "
                        f"for this workflow when that native feature is enough on its "
                        f"own: {workflow_action(cap)}."
                    ),
                    tools_affected=[cap.canonical_name],
                    effort="small",
                    notes=feature.description.strip() or None,
                    research=_research_sources(
                        [cap],
                        why=(
                            f"{feature.name} is already in the {cap.vendor} catalog "
                            f"({feature.maturity}, coverage {feature.coverage}). Use it "
                            "when the job stays inside that product."
                        ),
                    ),
                ),
            )
    return _number_recommendations(recs)


def grounded_summary(
    capabilities: list[ToolCapability],
    role: Role,
    *,
    synthetic: bool,
) -> str:
    """Summary that names the selected tools rather than a role checklist."""
    if not capabilities:
        names = "no catalogued tools"
    else:
        names = ", ".join(f"{cap.vendor} ({cap.canonical_name})" for cap in capabilities)
    prefix = "[DEMO/SYNTHETIC] " if synthetic else ""
    return (
        f"{prefix}{role.display_name} enablement plan grounded in the selected "
        f"tools: {names}. Findings and recommendations follow those tools' "
        f"catalog capabilities for a {role.display_name} workflow."
    )


def plan_drifts_from_tools(
    plan: EnablementPlan,
    capabilities: list[ToolCapability],
    role: Role,
) -> bool:
    """True when the plan recites role themes the selected tools do not support."""
    if not capabilities:
        return False
    text = _plan_text(plan)
    lowered = text.lower()
    for cap in capabilities:
        if cap.canonical_name.lower() not in lowered and cap.vendor.lower() not in lowered:
            return True
    selected = {cap.canonical_name for cap in capabilities}
    for finding in plan.capability_coverage:
        if any(name not in selected for name in finding.tools_involved):
            return True
    for rec in plan.recommendations:
        if any(name not in selected for name in rec.tools_affected):
            return True
    corpus = catalog_corpus(capabilities)
    return any(marker in lowered for marker in _absent_markers(role, corpus))


def apply_tool_grounding(
    plan: EnablementPlan,
    capabilities: list[ToolCapability],
    role: Role,
    *,
    creds: Credentials | None = None,
    synthetic: bool = False,
) -> EnablementPlan:
    """Keep a plan that already follows the tools. Replace one that does not.

    A kept plan still gains relationship findings, a fuller recommendation
    list, and catalog research when those pieces are missing.
    """
    if not capabilities:
        return plan
    if plan_drifts_from_tools(plan, capabilities, role):
        logger.info(
            "replacing findings that do not match selected tools role=%s tools=%s",
            role.id,
            [cap.canonical_name for cap in capabilities],
        )
        plan = plan.model_copy(
            update={
                "summary": grounded_summary(capabilities, role, synthetic=synthetic),
                "capability_coverage": grounded_findings(
                    capabilities, creds=creds, role=role
                ),
                "recommendations": grounded_recommendations(capabilities, role),
            }
        )
    findings = list(plan.capability_coverage)
    if not _has_relationship(findings, capabilities):
        findings = relationship_findings(capabilities, role) + findings
    recommendations = _ensure_recommendation_depth(
        plan.recommendations, capabilities, role
    )
    if findings == list(plan.capability_coverage) and recommendations == list(
        plan.recommendations
    ):
        return plan
    return plan.model_copy(
        update={
            "capability_coverage": findings,
            "recommendations": recommendations,
        }
    )


def _category_tokens(cap: ToolCapability) -> set[str]:
    tokens: set[str] = set()
    for category in cap.categories:
        for part in _TOKEN_RE.findall(category.lower()):
            tokens.add(part)
    return tokens


def _keys_match(tokens: set[str], keys: tuple[str, ...]) -> bool:
    for token in tokens:
        for key in keys:
            if len(key) < 4:
                if token == key:
                    return True
                continue
            if token == key or key in token or token in key:
                return True
    return False


def _as_status(value: object) -> _Status:
    if value == "covered" or value == "partial" or value == "gap" or value == "redundant":
        return value
    return "partial"


def _workflow_kind(capabilities: list[ToolCapability]) -> _Kind:
    if len(capabilities) >= 2:
        return "orchestrate"
    cap = capabilities[0]
    if not cap.mcp_server.available:
        return "augment_with_custom_ai"
    if cap.native_ai_features:
        return "use_native_ai"
    return "augment_with_custom_ai"


def _workflow_description(capabilities: list[ToolCapability], role: Role) -> str:
    clauses = [
        f"use {cap.vendor} ({cap.canonical_name}) to {workflow_action(cap)}"
        for cap in capabilities
    ]
    joined = "; ".join(clauses)
    if len(capabilities) == 1:
        return f"For a {role.display_name} teammate, {joined}."
    return (
        f"For a {role.display_name} teammate, connect the selected tools into "
        f"one workflow: {joined}."
    )


def _stub_description(capabilities: list[ToolCapability], role: Role) -> str:
    names = ", ".join(f"{cap.vendor} ({cap.canonical_name})" for cap in capabilities)
    actions = "; ".join(workflow_action(cap) for cap in capabilities)
    return (
        f"Add a minimal MCP stub for {names} so a {role.display_name} workflow "
        f"can {actions}."
    )


_MIN_GROUNDED_RECOMMENDATIONS = 4

_GAP_MARKERS = (
    "cannot",
    "can't",
    "does not",
    "doesn't",
    "do not",
    "limited to",
    "not exposed",
    "not a reasoning",
    "own model",
    "outside",
    "will not",
    "won't",
)

_IDEA_CATEGORY_KEYS = (
    "community",
    "forum",
    "content",
    "marketing",
    "campaign",
    "documentation",
    "docs",
    "document",
    "blog",
    "social",
    "publishing",
    "knowledge",
)

_OVERLAP_FAMILIES: tuple[tuple[str, ...], ...] = (
    ("ticket", "ticketing", "helpdesk"),
    ("crm", "customer"),
    ("marketing", "campaign"),
    ("email", "inbox", "mail"),
    ("chat", "messaging"),
    ("community", "forum"),
    ("knowledge", "documentation", "docs"),
    ("source", "code", "repository"),
)


def claude_integration_fits(capabilities: list[ToolCapability]) -> bool:
    """Claude fits when native AI cannot see the rest of the selected stack."""
    if len(capabilities) >= 2 and any(_catalog_gap(cap) for cap in capabilities):
        return True
    if len(capabilities) >= 2 and all(not cap.native_ai_features for cap in capabilities):
        return True
    return len(capabilities) == 1 and _catalog_gap(capabilities[0]) and not (
        capabilities[0].native_ai_features
    )


def idea_generation_fits(capabilities: list[ToolCapability], role: Role) -> bool:
    """ChatGPT fits when the role and at least one tool are a content surface."""
    if not _role_wants_ideas(role):
        return False
    return any(_is_idea_surface(cap) for cap in capabilities)


def _catalog_gap(cap: ToolCapability) -> bool:
    notes = (cap.notes or "").lower()
    return any(marker in notes for marker in _GAP_MARKERS)


def _is_idea_surface(cap: ToolCapability) -> bool:
    return _keys_match(_category_tokens(cap), _IDEA_CATEGORY_KEYS)


def _role_wants_ideas(role: Role) -> bool:
    identity = f"{role.id} {role.display_name} {role.department}".lower()
    if any(
        token in identity
        for token in ("devrel", "developer relation", "marketing", "advocate", "content")
    ):
        return True
    blob = " ".join(role.capabilities).lower()
    phrases = (
        "content",
        "campaign",
        "community",
        "blog",
        "talk",
        "tutorial",
        "persona",
        "seo",
        "documentation",
    )
    return any(phrase in blob for phrase in phrases)


def _name_list(labels: list[str]) -> str:
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _category_phrase(cap: ToolCapability) -> str:
    if not cap.categories:
        return "its catalog work"
    return ", ".join(category.replace("_", " ") for category in cap.categories[:3])


def _how_tools_relate(capabilities: list[ToolCapability], role: Role) -> str:
    clauses = [
        f"{cap.vendor} ({_category_phrase(cap)}) can {workflow_action(cap)}"
        for cap in capabilities
    ]
    vendors = _name_list([cap.vendor for cap in capabilities])
    joined = ". ".join(clauses)
    return (
        f"{vendors} relate as one {role.display_name} workflow, not as separate "
        f"capability lists. {joined}. Combine them by handing the result of each "
        f"step to the next tool, so a {role.display_name} teammate finishes the "
        "job without retyping the same facts into every product."
    )


def _combined_workflow(capabilities: list[ToolCapability], role: Role) -> str:
    lines: list[str] = []
    for index, cap in enumerate(capabilities):
        action = workflow_action(cap)
        if index == 0:
            lines.append(f"1. In {cap.vendor}, {action}. Keep that output.")
            continue
        previous = capabilities[index - 1]
        lines.append(
            f"{index + 1}. Pass that {previous.vendor} output into {cap.vendor} "
            f"and {action}."
        )
    last = capabilities[-1]
    first = capabilities[0]
    lines.append(
        f"{len(capabilities) + 1}. Write the {last.vendor} outcome back into "
        f"{first.vendor} so both tools show the same finished {role.display_name} job."
    )
    vendors = _name_list([cap.vendor for cap in capabilities])
    return f"Concrete workflow that uses all of {vendors}:\n" + "\n".join(lines)


def _handoff_description(capabilities: list[ToolCapability], role: Role) -> str:
    steps: list[str] = []
    for index, cap in enumerate(capabilities):
        action = workflow_action(cap)
        if index == 0:
            steps.append(f"start in {cap.vendor} to {action}")
            continue
        previous = capabilities[index - 1]
        steps.append(f"pass that {previous.vendor} output into {cap.vendor} to {action}")
    sequence = ", then ".join(steps)
    return (
        f"For a {role.display_name} teammate, run one handoff across the selected "
        f"tools: {sequence}. Finish by writing the outcome back to "
        f"{capabilities[0].vendor}."
    )


def _claude_description(capabilities: list[ToolCapability], role: Role) -> str:
    vendors = _name_list([cap.vendor for cap in capabilities])
    gaps = [
        f"{cap.vendor} ({cap.canonical_name})"
        for cap in capabilities
        if _catalog_gap(cap) or not cap.native_ai_features
    ]
    cited = _name_list(gaps) if gaps else vendors
    return (
        f"Integrate Claude as the reasoning step for a {role.display_name} workflow "
        f"across {vendors}. Claude drafts or classifies from records those tools "
        f"already store, then writes the result back through their APIs. Catalog "
        f"evidence that native AI cannot see the whole stack: {cited}."
    )


def _chatgpt_description(
    capabilities: list[ToolCapability],
    role: Role,
    surfaces: list[ToolCapability],
) -> str:
    surface_names = _name_list([cap.vendor for cap in (surfaces or capabilities)])
    fuel = [cap.vendor for cap in capabilities if cap not in surfaces]
    fuel_names = _name_list(fuel) if fuel else surface_names
    return (
        f"Move idea generation for the {role.display_name} job to ChatGPT (OpenAI). "
        f"Draft options from {fuel_names}, pick one, and publish it through "
        f"{surface_names}. The selected tools stay the system of record."
    )


def _consolidate_description(capabilities: list[ToolCapability], role: Role) -> str:
    vendors = _name_list([cap.vendor for cap in capabilities])
    shared = _shared_family_label(capabilities)
    return (
        f"Consolidate overlapping {shared} coverage in {vendors} for a "
        f"{role.display_name} teammate. Keep one tool as the system of record and "
        "use the others as inputs to that record."
    )


def _overlapping_tools(capabilities: list[ToolCapability]) -> list[ToolCapability]:
    best: list[ToolCapability] = []
    for keys in _OVERLAP_FAMILIES:
        matched = [cap for cap in capabilities if _keys_match(_category_tokens(cap), keys)]
        if len(matched) > len(best):
            best = matched
    if len(best) < 2:
        return []
    return best


def _shared_family_label(capabilities: list[ToolCapability]) -> str:
    for keys in _OVERLAP_FAMILIES:
        if all(_keys_match(_category_tokens(cap), keys) for cap in capabilities):
            return keys[0].replace("_", " ")
    if capabilities and capabilities[0].categories:
        return capabilities[0].categories[0].replace("_", " ")
    return "catalog"


def _research_why_actions(capabilities: list[ToolCapability]) -> str:
    return "; ".join(workflow_action(cap) for cap in capabilities)


def _research_sources(
    capabilities: list[ToolCapability],
    *,
    why: str,
) -> list[ResearchSource]:
    sources: list[ResearchSource] = []
    for cap in capabilities:
        note = (cap.notes or "").strip()
        if note:
            sources.append(
                ResearchSource(
                    title=f"{cap.vendor} catalog notes",
                    evidence=note,
                    source=f"catalog notes for {cap.canonical_name}",
                )
            )
        if cap.native_ai_features:
            feature = cap.native_ai_features[0]
            sources.append(
                ResearchSource(
                    title=f"{cap.vendor}: {feature.name}",
                    evidence=feature.description.strip() or feature.name,
                    source=f"native_ai_features on {cap.canonical_name}",
                )
            )
        channels: list[str] = []
        if cap.api_surface.has_rest_api:
            channels.append("a REST API")
        if cap.api_surface.has_webhooks:
            channels.append("webhooks")
        if cap.mcp_server.available:
            origin = cap.mcp_server.origin or "listed"
            channels.append(f"an MCP server ({origin})")
        if channels:
            sources.append(
                ResearchSource(
                    title=f"{cap.vendor} can be automated",
                    evidence=(
                        f"{cap.vendor} exposes {', '.join(channels)}, so this step "
                        "can run against the product instead of a manual export."
                    ),
                    source=f"api_surface and mcp_server for {cap.canonical_name}",
                )
            )
        if len(sources) >= 4:
            break
    kept = sources[:4]
    kept.append(
        ResearchSource(
            title="Why this is feasible",
            evidence=why,
            source="selected tool catalog",
        )
    )
    return kept


def _push(recs: list[Recommendation], rec: Recommendation) -> None:
    if any(existing.description == rec.description for existing in recs):
        return
    recs.append(rec)


def _number_recommendations(recs: list[Recommendation]) -> list[Recommendation]:
    return [
        rec.model_copy(update={"id": f"R-{index:03d}"})
        for index, rec in enumerate(recs, start=1)
    ]


def _has_relationship(
    findings: list[CapabilityFinding],
    capabilities: list[ToolCapability],
) -> bool:
    selected = {cap.canonical_name for cap in capabilities}
    if len(selected) < 2:
        return True
    for finding in findings:
        involved = set(finding.tools_involved)
        if len(involved) < 2 or not involved <= selected:
            continue
        if finding.focus == "relationship":
            return True
        notes = (finding.notes or "").lower()
        if "workflow" in notes or "combine" in notes:
            return True
    return False


def _caps_for(
    names: list[str],
    capabilities: list[ToolCapability],
) -> list[ToolCapability]:
    by_name = {cap.canonical_name: cap for cap in capabilities}
    matched = [by_name[name] for name in names if name in by_name]
    return matched or list(capabilities)


def _ensure_recommendation_depth(
    recommendations: list[Recommendation],
    capabilities: list[ToolCapability],
    role: Role,
) -> list[Recommendation]:
    recs = _fill_research(list(recommendations), capabilities)
    if len(capabilities) < 2 or len(recs) >= _MIN_GROUNDED_RECOMMENDATIONS:
        return recs
    for extra in grounded_recommendations(capabilities, role):
        if len(recs) >= _MIN_GROUNDED_RECOMMENDATIONS:
            break
        if any(existing.description == extra.description for existing in recs):
            continue
        recs.append(extra)
    return _number_recommendations(_fill_research(recs, capabilities))


def _fill_research(
    recommendations: list[Recommendation],
    capabilities: list[ToolCapability],
) -> list[Recommendation]:
    filled: list[Recommendation] = []
    for rec in recommendations:
        if rec.research:
            filled.append(rec)
            continue
        involved = _caps_for(rec.tools_affected, capabilities)
        why = (
            f"This uses {_name_list([cap.vendor for cap in involved])} through "
            "capabilities already in the catalog, so it can be built without adding "
            "a new system of record."
        )
        filled.append(rec.model_copy(update={"research": _research_sources(involved, why=why)}))
    return filled


def _plan_text(plan: EnablementPlan) -> str:
    chunks = [plan.summary]
    for finding in plan.capability_coverage:
        chunks.append(finding.capability)
        if finding.notes:
            chunks.append(finding.notes)
        chunks.extend(finding.tools_involved)
    for rec in plan.recommendations:
        chunks.append(rec.description)
        if rec.notes:
            chunks.append(rec.notes)
        chunks.extend(rec.tools_affected)
        for item in rec.research:
            chunks.append(item.title)
            chunks.append(item.evidence)
            chunks.append(item.source)
    return "\n".join(chunks)


def _theme_markers(role: Role) -> set[str]:
    """Phrases from the role checklist. Not a tool's catalog."""
    markers: set[str] = set()
    for raw in role.capabilities:
        phrase = " ".join(raw.lower().split())
        if phrase:
            markers.add(phrase)
        words = [
            word
            for word in _TOKEN_RE.findall(phrase)
            if word not in _STOP_WORDS and len(word) >= 5
        ]
        markers.update(words)
        pairs = zip(words, words[1:], strict=False)
        markers.update(f"{left} {right}" for left, right in pairs)
    return {marker for marker in markers if marker}


def _role_identity_tokens(role: Role) -> set[str]:
    text = f"{role.display_name} {role.id} {role.department}"
    return set(_TOKEN_RE.findall(text.lower()))


def _absent_markers(role: Role, corpus: str) -> list[str]:
    corpus_l = corpus.lower()
    identity = _role_identity_tokens(role)
    absent: list[str] = []
    for marker in _theme_markers(role):
        if " " not in marker and (marker in _GENERIC_UNIGRAMS or marker in identity):
            continue
        if marker not in corpus_l:
            absent.append(marker)
    return absent
