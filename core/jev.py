"""Jev decisions for Enable AI.

Jev answers typed questions about state the caller already has. It does
not write plans or call tools. Missing `TYPESAFE_API_KEY`, an HTTP failure, or
a confidence below the floor falls back to a local heuristic and says so.
A heuristic result is never labeled as a Jev decision.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx

from core.credentials import Credentials

logger = logging.getLogger(__name__)

JEV_CRED = "JEV_API_KEY"
TYPESAFE_CRED = "TYPESAFE_API_KEY"
#: `.env` uses the TypeSafe name. `JEV_API_KEY` still works.
JEV_CRED_NAMES = (TYPESAFE_CRED, JEV_CRED)
DECIDE_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
CHOICE_FLOOR = 0.5
#: Noul values inside this band are too close to call.
NOUL_LOW = 0.35
NOUL_HIGH = 0.65

CoverageStatus = Literal["covered", "partial", "gap", "redundant"]
DecisionSource = Literal["jev", "heuristic"]

_ESCALATION_HINTS = (
    "escalate",
    "manager",
    "supervisor",
    "complaint",
    "unhappy",
    "lawyer",
    "legal",
)

_COVERAGE_CRITERIA = {
    "covered": "The tool's native feature is enough for this capability.",
    "partial": "It covers part of the capability but cannot see cross-tool data.",
    "gap": "It does not address the capability.",
    "redundant": "It duplicates another declared tool on the same capability.",
}


def _make_client() -> httpx.Client:
    return httpx.Client(timeout=15.0)


def _heuristic_coverage(categories: list[str]) -> tuple[str, CoverageStatus]:
    cats = " ".join(categories).lower()
    if "ticketing" in cats:
        return ("first_response_drafting", "covered")
    if "knowledge_base" in cats or "documentation" in cats:
        return ("faq_retrieval", "covered")
    if "internal_messaging" in cats or "team_collaboration" in cats:
        return ("escalation_routing", "partial")
    if "crm" in cats:
        return ("knowledge_base_search", "partial")
    return ("intent_classification", "partial")


def _heuristic_escalate(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in _ESCALATION_HINTS)


def _payload_text(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    parts: list[str] = []
    for key in ("inquiry", "subject", "body", "text", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return "\n".join(parts)


def jev_token(creds: Credentials | None) -> str | None:
    """TypeSafe key from the caller, then the older `JEV_API_KEY` name."""
    if creds is None:
        return None
    for name in JEV_CRED_NAMES:
        value = creds.get(name)
        if value:
            return value
    return None


def decide(
    state: Any,
    questions: dict[str, Any],
    creds: Credentials | None,
) -> dict[str, Any]:
    """POST TypeSafe /v1/systemone. Stub shape when the key is missing or the call fails."""
    token = jev_token(creds)
    if not token:
        return {
            "mode": "stub",
            "reason": f"missing credential: {TYPESAFE_CRED}",
            "answers": None,
        }
    try:
        with _make_client() as client:
            response = client.post(
                DECIDE_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"model": MODEL, "state": state, "questions": questions},
            )
            response.raise_for_status()
            body = response.json()
    except Exception as exc:  # noqa: BLE001 — decision must not invent an answer
        logger.info("jev decide failed: %s", exc)
        return {"mode": "stub", "reason": f"jev_error: {exc}", "answers": None}
    answers = body.get("answers") if isinstance(body, dict) else None
    if not isinstance(answers, dict):
        return {"mode": "stub", "reason": "jev_error: missing answers", "answers": None}
    return {"mode": "real", "reason": None, "answers": answers}


def classify_coverage(
    *,
    tool_name: str,
    categories: list[str],
    capability: str | None,
    other_tools: list[str],
    creds: Credentials | None,
) -> dict[str, Any]:
    """Choose covered/partial/gap/redundant for one tool.

    The capability label stays a local heuristic. Jev only picks the status.
    """
    label, heuristic_status = _heuristic_coverage(categories)
    used_capability = capability or label
    result = decide(
        {
            "tool": tool_name,
            "categories": categories,
            "capability": used_capability,
            "other_tools": other_tools,
        },
        {
            "coverage": {
                "type": "choice",
                "instructions": "How well does this tool cover the capability?",
                "criteria": _COVERAGE_CRITERIA,
            }
        },
        creds,
    )
    base = {
        "capability": used_capability,
        "mode": result["mode"],
        "reason": result["reason"],
    }
    answer = (result["answers"] or {}).get("coverage") if result["answers"] else None
    if (
        result["mode"] == "real"
        and isinstance(answer, dict)
        and answer.get("choice") in _COVERAGE_CRITERIA
        and float(answer.get("confidence") or 0) >= CHOICE_FLOOR
    ):
        return {
            **base,
            "status": answer["choice"],
            "source": "jev",
            "abstained": False,
            "confidence": float(answer["confidence"]),
        }
    abstained = result["mode"] == "real"
    return {
        **base,
        "status": heuristic_status,
        "source": "heuristic",
        "abstained": abstained,
        "confidence": (
            float(answer["confidence"])
            if isinstance(answer, dict) and "confidence" in answer
            else None
        ),
        "reason": "low_confidence" if abstained else result["reason"],
    }


def should_escalate(payload: dict[str, Any] | None, creds: Credentials | None) -> dict[str, Any]:
    """Whether this request should stop before tool calls.

    No inquiry text means there is nothing to judge: do not escalate.
    """
    text = _payload_text(payload)
    if not text:
        return {
            "escalate": False,
            "mode": "stub",
            "source": "heuristic",
            "abstained": False,
            "reason": "no_inquiry_text",
            "noul": None,
        }
    heuristic = _heuristic_escalate(text)
    result = decide(
        text,
        {"escalate": {"type": "noul", "instructions": "Escalate to a human now?"}},
        creds,
    )
    answer = (result["answers"] or {}).get("escalate") if result["answers"] else None
    noul = float(answer["noul"]) if isinstance(answer, dict) and "noul" in answer else None
    if result["mode"] == "real" and noul is not None and (noul >= NOUL_HIGH or noul <= NOUL_LOW):
        return {
            "escalate": noul >= NOUL_HIGH,
            "mode": "real",
            "source": "jev",
            "abstained": False,
            "reason": None,
            "noul": noul,
        }
    return {
        "escalate": heuristic,
        "mode": result["mode"],
        "source": "heuristic",
        "abstained": result["mode"] == "real",
        "reason": "low_confidence" if result["mode"] == "real" else result["reason"],
        "noul": noul,
    }


def label_escalation(
    payload: dict[str, Any] | None,
    output: dict[str, Any] | None,
    creds: Credentials | None,
) -> dict[str, Any]:
    """Score whether a finished run escalated. Same honesty rules as the gate."""
    text = _payload_text(payload)
    if output:
        for key in ("text", "body", "message"):
            value = output.get(key)
            if isinstance(value, str):
                text = f"{text}\n{value}".strip()
    return should_escalate({"inquiry": text} if text else None, creds)
