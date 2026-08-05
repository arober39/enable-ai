"""Support Orchestrator — runtime entry point.

Handles one customer inquiry end-to-end:
  1. Constructs a LaunchDarkly context (single-context, kind=request).
  2. Fetches the active AI Config variation via ld_ai.config() — falls back
     to the v1-baseline prompt on disk when LD is unreachable.
  3. Classifies intent (refund / escalation / FAQ / status / other).
  4. For each intent class, executes the appropriate skill:
       - FAQ:        knowledge_base.search() → templated answer
       - REFUND:     draft_response() grounded in data/support/policies.md
       - ESCALATION: build_handoff() — structured handoff message
       - STATUS:     templated status-check reply
       - OTHER:      polite fallback that asks for clarification
  5. Returns a structured SupportResponse.
  6. Emits two LaunchDarkly custom events:
       - support.escalation (metric_value=1 if escalated, else 0)
       - support.error (metric_value=1, only on error paths)
  7. Emits OTel spans for each step per .claude/rules/observability.md.

Demo mode (ENABLE_AI_DEMO_MODE=true, the default) skips real LLM calls
and substitutes stub responses with the correct shape. This is what the
Phase 5.2 stub-driven smoke test exercises. Production runs (key set,
demo mode off) use real Claude + LaunchDarkly.

Tutorial-critical constants below are bit-exact:
  - AI Config name:        "support-orchestrator-config"
  - Event names:           "support.escalation", "support.error"
  - Model:                 claude-sonnet-4-6

Do not change these without updating the multi-signal guardrails tutorial.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, ConfigDict, Field

# Walk up from cwd to the repo root and load .env. override=False so vars
# already in the process environment (CI, `set -a; source .env`, tests) win.
load_dotenv(find_dotenv(usecwd=True), override=False)

from core.credentials import runtime_credentials
from orchestrators.support.observability import EXPECTED_SPAN_NAMES, span

logger = logging.getLogger(__name__)

# Locked phase 1 commitment (#1): orchestrators read credentials through a
# Credentials provider, never `os.environ` directly. The spawner (UI's
# /api/run-orchestrator or `make run` with .env loaded) populates env vars
# from the user's credential store before this process starts; the provider
# is a thin read-only wrapper around os.environ today, swappable later.
_CREDS = runtime_credentials()


# ---------------------------------------------------------------------------
# Tutorial-critical constants (bit-exact)
# ---------------------------------------------------------------------------

AI_CONFIG_NAME = "support-orchestrator-config"
EVENT_ESCALATION = "support.escalation"
EVENT_ERROR = "support.error"
MODEL_NAME = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


IntentClass = Literal["FAQ", "REFUND", "ESCALATION", "STATUS", "OTHER"]


class Inquiry(BaseModel):
    """Inbound customer inquiry. Mirrors tickets.json shape minus metadata."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    body: str
    customer_id: str


class SupportResponse(BaseModel):
    """Structured response returned by handle_inquiry()."""

    model_config = ConfigDict(extra="forbid")

    intent: IntentClass
    draft_reply: str
    confidence: float = Field(ge=0.0, le=1.0)
    action_taken: str
    citations: list[str] = Field(default_factory=list)
    escalated: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# Demo-mode gating
# ---------------------------------------------------------------------------


def _demo_mode() -> bool:
    raw = os.environ.get("ENABLE_AI_DEMO_MODE", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _first_text_block(msg: Any) -> str:
    """Return the .text of the first TextBlock in an Anthropic Message, or ''."""
    for block in getattr(msg, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            return text
    return ""


# ---------------------------------------------------------------------------
# LaunchDarkly: AI Config fetch + event tracking
# ---------------------------------------------------------------------------


@dataclass
class AIConfigResult:
    """Subset of the LD AI Config response the orchestrator needs."""

    variation_name: str
    system_prompt: str
    model: str


_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def _load_default_prompt(variation: str = "v1_baseline") -> str:
    """Read the on-disk baseline prompt as the demo-mode fallback."""
    path = _PROMPT_DIR / f"{variation}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


async def fetch_ai_config(request_id: str, customer_id: str) -> AIConfigResult:
    """Fetch the active AI Config variation; fall back to v1-baseline on disk in demo mode."""
    with span(
        "support_orchestrator.fetch_ai_config",
        ai_config_name=AI_CONFIG_NAME,
        customer_id=customer_id,
    ):
        if _demo_mode() or not _CREDS.get("LAUNCHDARKLY_SDK_KEY"):
            return AIConfigResult(
                variation_name="v1-baseline",
                system_prompt=_load_default_prompt("v1_baseline"),
                model=MODEL_NAME,
            )

        # Production path — uses the real LD SDK.
        from ldai.client import LDAIClient  # type: ignore[import-untyped]
        from ldclient import Context, LDClient
        from ldclient.config import Config as LDConfig

        ld_client = LDClient(LDConfig(sdk_key=_CREDS.require("LAUNCHDARKLY_SDK_KEY")))
        ai_client = LDAIClient(ld_client)
        ld_context = Context.builder(request_id).kind("request").build()
        result = ai_client.completion_config(AI_CONFIG_NAME, ld_context, default=None)
        # The exact shape varies; this code is the canonical pattern the
        # tutorial references. Adjust to the SDK's current API surface.
        system_prompt = ""
        if result and getattr(result, "messages", None):
            for msg in result.messages:
                if getattr(msg, "role", None) == "system":
                    system_prompt = msg.content
                    break
        return AIConfigResult(
            variation_name=getattr(result, "variation_name", "v1-baseline"),
            system_prompt=system_prompt or _load_default_prompt("v1_baseline"),
            model=getattr(getattr(result, "model", None), "name", MODEL_NAME),
        )


def track_event(event_name: str, request_id: str, metric_value: int) -> None:
    """Emit a LaunchDarkly custom event. No-op in demo mode."""
    with span("support_orchestrator.emit_events", event_name=event_name, metric_value=metric_value):
        if _demo_mode() or not _CREDS.get("LAUNCHDARKLY_SDK_KEY"):
            logger.debug(
                "track_event (demo-mode no-op): event=%s request_id=%s value=%s",
                event_name,
                request_id,
                metric_value,
            )
            return

        from ldclient import Context, LDClient
        from ldclient.config import Config as LDConfig

        ld_client = LDClient(LDConfig(sdk_key=_CREDS.require("LAUNCHDARKLY_SDK_KEY")))
        ld_context = Context.builder(request_id).kind("request").build()
        ld_client.track(event_name, ld_context, metric_value=metric_value)


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------


_REFUND_HINTS = ("refund", "cancel", "cancellation", "money back", "charge back", "chargeback")
_ESCALATION_HINTS = ("escalate", "manager", "supervisor", "complaint", "unhappy", "lawyer", "legal")
_FAQ_HINTS = ("how do i", "where do i", "what is", "what's the", "policy", "do you", "can i")
_STATUS_HINTS = ("status", "when will", "update on", "where is")


def _stub_classify_intent(inquiry: Inquiry) -> IntentClass:
    """Keyword-based classifier used in demo mode. Realistic enough for the contract."""
    text = (inquiry.subject + " " + inquiry.body).lower()
    if any(h in text for h in _ESCALATION_HINTS):
        return "ESCALATION"
    if any(h in text for h in _REFUND_HINTS):
        return "REFUND"
    if any(h in text for h in _STATUS_HINTS):
        return "STATUS"
    if any(h in text for h in _FAQ_HINTS):
        return "FAQ"
    return "OTHER"


async def classify_intent(inquiry: Inquiry, ai_config: AIConfigResult) -> IntentClass:
    """Classify intent. Uses stub in demo mode; real LLM in production."""
    with span(
        "support_orchestrator.classify_intent",
        variation_name=ai_config.variation_name,
    ) as s:
        if _demo_mode() or not _CREDS.get("ANTHROPIC_API_KEY"):
            intent = _stub_classify_intent(inquiry)
            s.set_attribute("intent", intent)
            s.set_attribute("classifier", "stub")
            return intent

        # Production path — real LLM call.
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic()
        msg = await client.messages.create(
            model=ai_config.model or MODEL_NAME,
            max_tokens=64,
            system=(
                "Classify the customer inquiry into exactly one of: "
                "FAQ, REFUND, ESCALATION, STATUS, OTHER. "
                "Reply with only the label."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Subject: {inquiry.subject}\n\nBody: {inquiry.body}",
                }
            ],
        )
        raw = _first_text_block(msg).strip().upper() if msg.content else "OTHER"
        valid_intents = {"FAQ", "REFUND", "ESCALATION", "STATUS", "OTHER"}
        live_intent = cast(IntentClass, raw if raw in valid_intents else "OTHER")
        s.set_attribute("intent", live_intent)
        s.set_attribute("classifier", "live")
        return live_intent


# ---------------------------------------------------------------------------
# Skill implementations
# ---------------------------------------------------------------------------


_POLICIES_PATH = Path(__file__).resolve().parents[2] / "data" / "support" / "policies.md"


def load_policies() -> str:
    """Read Serenia's policy doc from disk."""
    if _POLICIES_PATH.exists():
        return _POLICIES_PATH.read_text(encoding="utf-8")
    return ""


def search_knowledge_base(inquiry: Inquiry) -> tuple[str, list[str]]:
    """Stub knowledge-base lookup. Returns (templated answer, citations)."""
    with span("support_orchestrator.knowledge_base.search", subject=inquiry.subject):
        # In production this would hit Zendesk's MCP server (search_articles).
        # For v1 the stub returns a templated answer grounded in the policy file.
        text = load_policies()
        snippet = (
            "Final headcount locks 14 days before the event. See the "
            "scope-changes section of our policies for details."
        )
        if "headcount" in (inquiry.subject + inquiry.body).lower() and "scope" in text.lower():
            snippet = (
                "Final headcount locks 14 days before the event. After that, "
                "changes go through your event lead and may carry a per-guest "
                "catering charge."
            )
        return snippet, ["data/support/policies.md#scope-changes"]


async def draft_refund_response(
    inquiry: Inquiry,
    ai_config: AIConfigResult,
) -> tuple[str, list[str]]:
    """Draft a refund-related reply grounded in the policy doc."""
    with span("support_orchestrator.draft_response", variation_name=ai_config.variation_name):
        policy_text = load_policies()
        if _demo_mode() or not _CREDS.get("ANTHROPIC_API_KEY"):
            # Stub: cite the cancellation schedule. Never volunteer policies
            # the customer didn't ask about — even with the v2 prompt.
            reply = (
                "Our cancellation refund schedule is tiered by lead time: "
                "100% refund of paid amounts (excluding the non-refundable "
                "deposit) at 90+ days out, 75% at 60-89 days, 50% at 30-59 "
                "days, 25% at 14-29 days, and 0% inside 14 days. The exact "
                "amount depends on your specific timeline."
            )
            return reply, ["data/support/policies.md#cancellation-refund-schedule"]

        from anthropic import AsyncAnthropic

        client = AsyncAnthropic()
        msg = await client.messages.create(
            model=ai_config.model or MODEL_NAME,
            max_tokens=512,
            system=ai_config.system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Customer question:\n{inquiry.subject}\n\n{inquiry.body}\n\n"
                        f"Policy documentation:\n{policy_text}\n\n"
                        f"Draft a reply that answers the question. "
                        f"Cite policy details only when they directly answer the question."
                    ),
                }
            ],
        )
        reply = _first_text_block(msg).strip() if msg.content else ""
        return reply, ["data/support/policies.md"]


def build_escalation_handoff(inquiry: Inquiry) -> str:
    """Produce a structured handoff message for the team lead."""
    with span("support_orchestrator.build_handoff", customer_id=inquiry.customer_id):
        return json.dumps(
            {
                "type": "support.escalation_handoff",
                "customer_id": inquiry.customer_id,
                "subject": inquiry.subject,
                "summary": inquiry.body[:200],
                "next_action": "tier_2_review",
            },
            indent=2,
        )


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


async def handle_inquiry(inquiry: Inquiry, request_id: str | None = None) -> SupportResponse:
    """Handle one customer inquiry end-to-end. Phase 5.2 behavioral contract."""
    rid = request_id or str(uuid.uuid4())
    with span(
        "support_orchestrator.handle_inquiry",
        request_id=rid,
        customer_id=inquiry.customer_id,
    ):
        try:
            ai_config = await fetch_ai_config(rid, inquiry.customer_id)
            intent = await classify_intent(inquiry, ai_config)

            if intent == "FAQ":
                reply, citations = search_knowledge_base(inquiry)
                response = SupportResponse(
                    intent=intent,
                    draft_reply=reply,
                    confidence=0.8,
                    action_taken="auto_resolved_with_kb",
                    citations=citations,
                    escalated=False,
                )
            elif intent == "REFUND":
                reply, citations = await draft_refund_response(inquiry, ai_config)
                response = SupportResponse(
                    intent=intent,
                    draft_reply=reply,
                    confidence=0.7,
                    action_taken="auto_drafted_for_review",
                    citations=citations,
                    escalated=False,
                )
            elif intent == "ESCALATION":
                handoff = build_escalation_handoff(inquiry)
                response = SupportResponse(
                    intent=intent,
                    draft_reply=handoff,
                    confidence=0.9,
                    action_taken="escalated_to_team_lead",
                    citations=[],
                    escalated=True,
                )
            elif intent == "STATUS":
                response = SupportResponse(
                    intent=intent,
                    draft_reply=(
                        "I can see your booking in our system. Your event lead "
                        "will follow up within one business day with the specific "
                        "status update."
                    ),
                    confidence=0.75,
                    action_taken="auto_acknowledged",
                    citations=[],
                    escalated=False,
                )
            else:  # OTHER
                response = SupportResponse(
                    intent=intent,
                    draft_reply=(
                        "Thanks for reaching out. Could you share a bit more "
                        "context so we can make sure we route this to the right "
                        "person?"
                    ),
                    confidence=0.5,
                    action_taken="auto_acknowledged_clarification",
                    citations=[],
                    escalated=False,
                )

            track_event(EVENT_ESCALATION, rid, metric_value=1 if response.escalated else 0)
            return response

        except Exception as exc:  # noqa: BLE001 — surface errors structurally
            logger.exception("support_orchestrator error: %s", exc)
            track_event(EVENT_ERROR, rid, metric_value=1)
            return SupportResponse(
                intent="OTHER",
                draft_reply="",
                confidence=0.0,
                action_taken="error",
                citations=[],
                escalated=False,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# CLI entry — `python -m orchestrators.support.orchestrator`
# ---------------------------------------------------------------------------


def _sample_inquiry() -> Inquiry:
    """Built-in sample inquiry for the demo `make run` path."""
    return Inquiry(
        subject="Can we still change the appetizer selection?",
        body=(
            "Hi — we picked the autumn appetizer board back in October but "
            "Jordan and I are now leaning toward the cured-meats option. Are "
            "we past the deadline to switch?"
        ),
        customer_id="CUST-001",
    )


async def _amain() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    inquiry = _sample_inquiry()
    result = await handle_inquiry(inquiry)
    print(json.dumps(result.model_dump(), indent=2))


def main() -> None:  # pragma: no cover — manual invocation
    asyncio.run(_amain())


if __name__ == "__main__":
    main()


# Surface for tests — sanity check that all expected span names are emitted
# somewhere in the file. (Tests can grep for these names to verify the
# observability contract from Phase 5.2.)
_REGISTERED_SPAN_NAMES: tuple[str, ...] = EXPECTED_SPAN_NAMES


# Type-checker hint: keep an unused reference to Any so the import isn't
# flagged when the file has no other Any uses in the future.
_TYPE_HINT: Any = None
