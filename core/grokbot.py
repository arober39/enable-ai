"""Copy-paste Grok Bot handoff, with an optional Jev placement.

Step 7 asks Jev whether the recommendation is a new bot or belongs on an
existing one, then shows text the user pastes into Grok Bot. It never calls
createAgent or updateAgent. listAgents runs only when gateway credentials
are present, and only to name an existing bot. `apply_recommendation` remains
for a later path that would write the bot itself.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field

from core.credentials import Credentials
from core.jev import CHOICE_FLOOR, JEV_CRED, decide

logger = logging.getLogger(__name__)

URL_KEY = "GROKBOT_GATEWAY_URL"
TOKEN_KEY = "SAND_GATEWAY_TOKEN"
_NEW = "new_bot"
_EXISTING = "existing_bot"
_NAME_LIMIT = 80
_TITLE_LIMIT = 80
_DESCRIPTION_LIMIT = 4000
_REPO_ROOT = Path(__file__).resolve().parents[1]

PlacementAction = Literal["create", "update", "create_fallback"]


class GrokbotHandoff(BaseModel):
    """Ready-to-paste Grok Bot fields. Enable AI does not create the bot."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Bot name to paste, or the existing bot Jev named.")
    title: str = Field(description="Suggested title. Usually the role name.")
    description: str = Field(
        description=(
            "Jev's placement, then the assignment. Enable AI does not call the tools named in it."
        ),
    )
    placement: str = Field(description="Plain sentence about where Jev says this work belongs.")
    action: PlacementAction = Field(
        description=(
            "create when Jev chooses a new bot, update when Jev chooses an existing bot, "
            "create_fallback when Jev did not decide."
        ),
    )
    existing_bot_name: str | None = Field(
        default=None,
        description="Name of the existing bot Jev chose, when the roster included it.",
    )


class HandoffCredentials(Credentials):
    """Settings first, then the process environment, then the repo `.env` file."""

    def __init__(self, store: Credentials) -> None:
        self._store = store

    def get(self, key: str) -> str | None:
        stored = self._store.get(key)
        if stored:
            return stored
        env = os.environ.get(key)
        if env:
            return env
        return _file_env().get(key)


def _file_env() -> dict[str, str]:
    """Non-empty values from the repo `.env`. Does not write `os.environ`."""
    path = _REPO_ROOT / ".env"
    if not path.is_file():
        return {}
    loaded = dotenv_values(path)
    found: dict[str, str] = {}
    for key, value in loaded.items():
        if isinstance(key, str) and isinstance(value, str) and value.strip():
            found[key] = value
    return found


def assignment_text(
    *,
    recommendation_id: str,
    kind: str,
    description: str,
    notes: str | None,
    role_name: str,
    tools: list[str],
) -> str:
    """The bot's job. Enable AI does not call the tools named here."""
    text = description.strip()
    extra = (notes or "").strip()
    tool_list = ", ".join(tools) if tools else "the tools named in the task"
    rec_id = recommendation_id or "recommendation"
    kind_label = kind or "recommendation"
    parts = [
        f"You are the {role_name} bot for Enable AI recommendation {rec_id} ({kind_label}).",
        "Do this work yourself in Grok Bot. Enable AI does not call these tools.",
        f"Tools you should use: {tool_list}",
        text,
    ]
    if extra:
        parts.append(extra)
    return "\n\n".join(part for part in parts if part)


def _bot_name(recommendation_id: str, role_name: str) -> str:
    rec_id = recommendation_id or "recommendation"
    return f"{rec_id} {role_name}".strip()[:_NAME_LIMIT] or rec_id


def _bot_title(role_name: str) -> str:
    return role_name[:_TITLE_LIMIT] or "Enable AI"


def _plain_reason(reason: str | None) -> str:
    if not reason:
        return "no decision"
    if reason == "low_confidence":
        return "low confidence"
    if reason == f"missing credential: {JEV_CRED}":
        return f"missing {JEV_CRED} — add it in Settings or .env"
    return reason


def _advice(
    decision: dict[str, Any],
    suggested_name: str,
    title: str,
    roster: list[dict[str, Any]] | None,
) -> tuple[str, PlacementAction, str, str, str | None]:
    """Placement sentence, action, display name, title, and existing bot name."""
    choice = decision.get("choice")
    if decision.get("source") == "jev" and choice == _NEW:
        line = f"Jev recommends: create a new bot named {suggested_name}."
        return line, "create", suggested_name, title, None
    if decision.get("source") == "jev" and choice == _EXISTING:
        line = (
            "Jev recommends: add this to an existing bot. Pick which bot in Grok Bot."
        )
        return line, "update", suggested_name, title, None
    if decision.get("source") == "jev" and roster:
        match = next((bot for bot in roster if bot.get("id") == choice), None)
        if match is not None:
            bot_name = str(match.get("name") or "bot")
            bot_title = str(match.get("title") or "") or title
            line = f"Jev recommends: add this to existing bot {bot_name}."
            return line, "update", bot_name, bot_title, bot_name
    line = (
        f"Jev did not choose a bot ({_plain_reason(decision.get('reason'))}). "
        f"Create a new bot named {suggested_name}."
    )
    return line, "create_fallback", suggested_name, title, None


def build_handoff(
    *,
    recommendation_id: str,
    kind: str,
    description: str,
    notes: str | None,
    role_name: str,
    tools: list[str],
    creds: Credentials | None = None,
) -> GrokbotHandoff:
    """Name, title, and assignment for the user to paste into Grok Bot.

    Asks Jev where the work belongs. May call listAgents when gateway
    credentials exist. Does not call createAgent or updateAgent.
    """
    suggested = _bot_name(recommendation_id, role_name)
    title = _bot_title(role_name)
    body = assignment_text(
        recommendation_id=recommendation_id,
        kind=kind,
        description=description,
        notes=notes,
        role_name=role_name,
        tools=tools,
    )
    roster = _roster(creds)
    decision = _placement(
        {
            "id": recommendation_id,
            "kind": kind,
            "description": description,
            "notes": notes,
        },
        role_name,
        roster,
        creds,
    )
    placement, action, name, shown_title, existing_name = _advice(
        decision,
        suggested,
        title,
        roster,
    )
    return GrokbotHandoff(
        name=name,
        title=shown_title,
        description=f"{placement}\n\n{body}",
        placement=placement,
        action=action,
        existing_bot_name=existing_name,
    )


def _client() -> httpx.Client:
    return httpx.Client(timeout=20.0)


def _gateway(creds: Credentials | None) -> tuple[str, str] | dict[str, Any]:
    url = (creds.get(URL_KEY) if creds is not None else None) or ""
    token = (creds.get(TOKEN_KEY) if creds is not None else None) or ""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {
            "mode": "stub",
            "reason": f"missing credential: {URL_KEY}",
            "action": "none",
            "source": "heuristic",
            "bot": None,
        }
    if not token:
        return {
            "mode": "stub",
            "reason": f"missing credential: {TOKEN_KEY}",
            "action": "none",
            "source": "heuristic",
            "bot": None,
        }
    return url.rstrip("/"), token


def _command(
    base: str,
    token: str,
    name: str,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    # Gateway JSON is an open payload. Callers narrow the fields they read.
    with _client() as client:
        response = client.post(
            f"{base}/api/{name}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body if body is not None else {},
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict) and not isinstance(payload, list):
        raise RuntimeError(f"{name} returned {type(payload).__name__}")
    return payload if isinstance(payload, dict) else {"items": payload}


def _bots(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    rows = payload if isinstance(payload, list) else payload.get("items", payload)
    agents = payload.get("agents") if isinstance(payload, dict) else None
    if isinstance(payload, dict) and "items" not in payload and isinstance(agents, list):
        rows = payload["agents"]
    if not isinstance(rows, list):
        return []
    bots: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("isGroup"):
            continue
        bot_id = row.get("id")
        name = row.get("name")
        if isinstance(bot_id, str) and isinstance(name, str) and name.strip():
            bots.append(row)
    return bots


def _bot_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "title": row.get("title") or "",
        "description": row.get("description") or "",
    }


def _roster(creds: Credentials | None) -> list[dict[str, Any]] | None:
    """Existing bots, or None when the gateway cannot be read.

    Read-only. A missing gateway or a failed listAgents does not invent bots.
    """
    gateway = _gateway(creds)
    if isinstance(gateway, dict):
        return None
    base, token = gateway
    try:
        listed = _command(base, token, "listAgents", {})
    except Exception as exc:  # noqa: BLE001 — an unread roster is not a decision
        logger.info("grokbot listAgents failed: %s", exc)
        return None
    return _bots(listed if isinstance(listed, dict) else {"items": listed})


def _placement(
    recommendation: dict[str, Any],
    role_name: str,
    bots: list[dict[str, Any]] | None,
    creds: Credentials | None,
) -> dict[str, Any]:
    criteria = {
        _NEW: (
            "This is a distinct role and should be its own bot, "
            "with its own name and description."
        ),
    }
    if bots is None:
        criteria[_EXISTING] = (
            "Add this work to an existing bot. The user will choose which bot."
        )
    else:
        for bot in bots:
            snippet = str(bot.get("description") or "")[:180]
            criteria[str(bot["id"])] = (
                f"Add this work to the existing bot {bot.get('name')}. {snippet}"
            )
    known_bots = bots or []
    result = decide(
        {
            "role": role_name,
            "recommendation_id": recommendation.get("id"),
            "kind": recommendation.get("kind"),
            "description": recommendation.get("description"),
            "notes": recommendation.get("notes"),
            "existing_bots": [_bot_view(bot) for bot in known_bots],
        },
        {
            "placement": {
                "type": "choice",
                "instructions": (
                    "Should this recommendation be a new standalone bot, "
                    "or added to one existing bot?"
                ),
                "criteria": criteria,
            }
        },
        creds,
    )
    answer = (result["answers"] or {}).get("placement") if result["answers"] else None
    choice = answer.get("choice") if isinstance(answer, dict) else None
    confidence = (
        float(answer["confidence"])
        if isinstance(answer, dict) and answer.get("confidence") is not None
        else 0.0
    )
    known = set(criteria)
    if result["mode"] == "real" and choice in known and confidence >= CHOICE_FLOOR:
        return {
            "source": "jev",
            "choice": choice,
            "confidence": confidence,
            "reason": None,
        }
    return {
        "source": "heuristic",
        "choice": None,
        "confidence": confidence or None,
        "reason": "low_confidence" if result["mode"] == "real" else result["reason"],
    }


def _assignment(
    recommendation: dict[str, Any],
    role_name: str,
    tools: list[str],
) -> str:
    notes = recommendation.get("notes")
    return assignment_text(
        recommendation_id=str(recommendation.get("id") or ""),
        kind=str(recommendation.get("kind") or ""),
        description=str(recommendation.get("description") or ""),
        notes=str(notes) if notes is not None else None,
        role_name=role_name,
        tools=tools,
    )


def apply_recommendation(
    recommendation: dict[str, Any],
    role_name: str,
    tools: list[str],
    creds: Credentials | None,
) -> dict[str, Any]:
    """Create or update one Grok Bot after a confident Jev placement.

    Not used by the step 7 UI. That screen calls `build_handoff` and the
    user pastes the result into Grok Bot.
    """
    gateway = _gateway(creds)
    if isinstance(gateway, dict):
        return gateway
    base, token = gateway
    try:
        listed = _command(base, token, "listAgents", {})
        bots = _bots(listed if isinstance(listed, dict) else {"items": listed})
    except Exception as exc:  # noqa: BLE001 — do not invent a roster
        logger.info("grokbot listAgents failed: %s", exc)
        return {
            "mode": "stub",
            "reason": f"grokbot_error: {exc}",
            "action": "none",
            "source": "heuristic",
            "bot": None,
        }

    decision = _placement(recommendation, role_name, bots, creds)
    if decision["source"] != "jev" or not decision["choice"]:
        return {
            "mode": "real",
            "action": "none",
            "source": "heuristic",
            "reason": decision["reason"],
            "confidence": decision["confidence"],
            "bot": None,
        }

    text = str(recommendation.get("description") or "").strip()
    body = _assignment(recommendation, role_name, tools)
    rec_id = str(recommendation.get("id") or "recommendation")
    try:
        if decision["choice"] == _NEW:
            name = _bot_name(rec_id, role_name)
            created = _command(
                base,
                token,
                "createAgent",
                {
                    "name": name,
                    "description": body[:_DESCRIPTION_LIMIT],
                    "title": _bot_title(role_name),
                    "purpose": text[:240],
                },
            )
            agent = created.get("agent") if isinstance(created.get("agent"), dict) else created
            return {
                "mode": "real",
                "action": "created",
                "source": "jev",
                "confidence": decision["confidence"],
                "reason": None,
                "bot": _bot_view(agent if isinstance(agent, dict) else {"name": name}),
            }
        current = next(bot for bot in bots if bot["id"] == decision["choice"])
        previous = str(current.get("description") or "").strip()
        addition = f"Enable AI {rec_id}: {body}".strip()
        description = addition if not previous else f"{previous}\n\n{addition}"
        updated = _command(
            base,
            token,
            "updateAgent",
            {
                "id": current["id"],
                "profile": {
                    "name": str(current.get("name") or "Bot"),
                    "description": description[:_DESCRIPTION_LIMIT],
                    "title": str(current.get("title") or role_name or "Enable AI"),
                },
            },
        )
        agent = updated if isinstance(updated, dict) and updated.get("id") else current
        if isinstance(updated, dict) and isinstance(updated.get("agent"), dict):
            agent = updated["agent"]
        return {
            "mode": "real",
            "action": "updated",
            "source": "jev",
            "confidence": decision["confidence"],
            "reason": None,
            "bot": _bot_view(agent if isinstance(agent, dict) else current),
        }
    except Exception as exc:  # noqa: BLE001
        logger.info("grokbot write failed: %s", exc)
        return {
            "mode": "stub",
            "reason": f"grokbot_error: {exc}",
            "action": "none",
            "source": "jev",
            "confidence": decision["confidence"],
            "bot": None,
        }
