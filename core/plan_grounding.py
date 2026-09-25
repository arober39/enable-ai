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

from coordinator.schemas import CapabilityFinding, EnablementPlan, Recommendation
from core.credentials import Credentials
from core.jev import classify_coverage
from core.roles import Role
from core.tool_catalog import ToolCapability

logger = logging.getLogger(__name__)

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


def workflow_action(cap: ToolCapability) -> str:
    """One clause of work this tool's catalog says it can do."""
    tokens = _category_tokens(cap)
    phrases: list[str] = []
    for keys, phrase in _CATEGORY_ACTIONS:
        if _keys_match(tokens, keys) and phrase not in phrases:
            phrases.append(phrase)
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


def grounded_findings(
    capabilities: list[ToolCapability],
    *,
    missing: list[str] | None = None,
    creds: Credentials | None = None,
) -> list[CapabilityFinding]:
    """One finding per selected tool, named for that tool's catalog domain."""
    findings: list[CapabilityFinding] = []
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
    kind = _workflow_kind(capabilities)
    effort: Literal["small", "medium", "large"] = (
        "small" if kind == "use_native_ai" else "medium"
    )
    recs.append(
        Recommendation(
            id="R-001",
            kind=kind,
            description=_workflow_description(capabilities, role),
            tools_affected=[cap.canonical_name for cap in capabilities],
            effort=effort,
            notes=None,
        )
    )
    next_id = 2
    missing_mcp = [cap for cap in capabilities if not cap.mcp_server.available]
    workflow_already_covers_stubs = kind == "augment_with_custom_ai" and len(
        missing_mcp
    ) == len(capabilities)
    if missing_mcp and not workflow_already_covers_stubs:
        recs.append(
            Recommendation(
                id=f"R-{next_id:03d}",
                kind="augment_with_custom_ai",
                description=_stub_description(missing_mcp, role),
                tools_affected=[cap.canonical_name for cap in missing_mcp],
                effort="medium",
                notes="No vendor-maintained MCP server for these tools yet.",
            )
        )
        next_id += 1
    if not (kind == "use_native_ai" and len(capabilities) == 1):
        for cap in capabilities:
            if not cap.native_ai_features:
                continue
            feature = cap.native_ai_features[0]
            recs.append(
                Recommendation(
                    id=f"R-{next_id:03d}",
                    kind="use_native_ai",
                    description=(
                        f"Use {cap.vendor}'s {feature.name} on {cap.canonical_name} "
                        f"for this workflow when that native feature is enough on its "
                        f"own: {workflow_action(cap)}."
                    ),
                    tools_affected=[cap.canonical_name],
                    effort="small",
                    notes=None,
                )
            )
            break
    return recs


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
    """Keep a plan that already follows the tools. Replace one that does not."""
    if not capabilities or not plan_drifts_from_tools(plan, capabilities, role):
        return plan
    logger.info(
        "replacing findings that do not match selected tools role=%s tools=%s",
        role.id,
        [cap.canonical_name for cap in capabilities],
    )
    return plan.model_copy(
        update={
            "summary": grounded_summary(capabilities, role, synthetic=synthetic),
            "capability_coverage": grounded_findings(capabilities, creds=creds),
            "recommendations": grounded_recommendations(capabilities, role),
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
