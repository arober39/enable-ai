"""Real Intercom adapter — Phase 2.3.

Auth: Bearer token in `Authorization` header. Two credentials in total:

  - `INTERCOM_API_TOKEN` — access token from Developer Hub → Settings →
    Workspace apps. Required for ALL actions.
  - `INTERCOM_ADMIN_ID`  — numeric admin id this app posts as.
    Required ONLY for write actions (`send_reply`, `assign_to_agent`).
    Find it at: Settings → Workspace → Teammates → click your service
    admin → URL contains `.../admins/<id>`.

Action coverage:

  - search_conversations  POST  /conversations/search
  - get_conversation      GET   /conversations/{id}?display_as=plaintext
  - send_reply            POST  /conversations/{id}/reply  (admin comment)
  - assign_to_agent       POST  /conversations/{id}/parts  (admin assignment)

Response shape mirrors the stub adapter so workflows that consumed
`{messages: [{role, text}]}` and `{results: [{id, subject}]}` keep
working unchanged. The `mode` field on each response is `"real"` or
`"stub"` — same convention as the Zendesk adapter.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from core.credentials import Credentials

logger = logging.getLogger(__name__)

#: Intercom API version pin. Bumping requires checking shape compatibility.
INTERCOM_API_VERSION = "2.11"

#: Always-required credential. Without it, all actions stub.
TOKEN_CRED = "INTERCOM_API_TOKEN"

#: Write-action required credential. Without it, write actions stub even
#: if the token is present.
ADMIN_ID_CRED = "INTERCOM_ADMIN_ID"

#: Actions that need the admin id.
_WRITE_ACTIONS = {"send_reply", "assign_to_agent"}

_BASE_URL = "https://api.intercom.io"
_TIMEOUT_SECONDS = 15.0
_BODY_TRUNCATE = 500


# ---------------------------------------------------------------------------
# Test seam — same shape as zendesk.py's _make_client.
# ---------------------------------------------------------------------------


def _make_client(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=_BASE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Intercom-Version": INTERCOM_API_VERSION,
        },
        timeout=_TIMEOUT_SECONDS,
    )


# ---------------------------------------------------------------------------
# Stub responses — shape matches real responses for safe interop with the
# workflow's downstream steps. Used when required creds are missing.
# ---------------------------------------------------------------------------


def _stub_response(action: str, params: dict[str, Any], reason: str) -> dict[str, Any]:
    base = {
        "tool": "intercom",
        "action": action,
        "mode": "stub",
        "reason": reason,
        "params": params,
    }
    if action == "search_conversations":
        return {**base, "results": [{"id": "conv_stub_1", "subject": "Sample"}]}
    if action == "get_conversation":
        return {
            **base,
            "id": params.get("id"),
            "state": "open",
            "customer": {"id": "ct_stub_1", "email": "stub@example.com", "name": "Sample"},
            "messages": [{"role": "user", "text": "stub"}],
        }
    if action == "send_reply":
        return {**base, "delivered": True, "conversation_part_id": "part_stub_1"}
    if action == "assign_to_agent":
        return {**base, "assigned_to": params.get("agent_id"), "conversation_part_id": "part_stub_1"}
    return {**base, "error": f"unknown intercom action: {action}"}


# ---------------------------------------------------------------------------
# Real Intercom calls
# ---------------------------------------------------------------------------


def _truncate(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return text if len(text) <= _BODY_TRUNCATE else text[:_BODY_TRUNCATE] + "…"


async def _search_conversations(
    client: httpx.AsyncClient, params: dict[str, Any]
) -> dict[str, Any]:
    query = str(params.get("query") or "").strip()
    if not query:
        return {"mode": "real", "results": [], "error": "missing required param: query"}
    body = {
        "query": {
            "field": "source.body",
            "operator": "~",
            "value": query,
        },
        "pagination": {"per_page": 5},
    }
    resp = await client.post("/conversations/search", json=body)
    resp.raise_for_status()
    data = resp.json() or {}
    return {
        "mode": "real",
        "results": [
            {
                "id": str(c.get("id", "")),
                "subject": (c.get("source") or {}).get("subject")
                or (c.get("source") or {}).get("body", "")[:80]
                or "(no subject)",
                "state": c.get("state"),
                "updated_at": c.get("updated_at"),
            }
            for c in (data.get("conversations") or [])[:5]
        ],
    }


def _messages_from_conversation(conv: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a conversation into a chronological list of {role, text} messages.

    Intercom returns:
      - `source` — the initial message
      - `conversation_parts.conversation_parts[]` — every follow-up
    Customer messages have `author.type == "user"` (or "lead"); admin replies
    have `author.type == "admin"` or "bot".
    """
    messages: list[dict[str, Any]] = []
    source = conv.get("source") or {}
    if source.get("body") or source.get("type"):
        messages.append(
            {
                "role": "user" if (source.get("author") or {}).get("type") in {"user", "lead", "contact"} else "admin",
                "text": _truncate(source.get("body") or ""),
            }
        )
    parts_container = conv.get("conversation_parts") or {}
    for part in parts_container.get("conversation_parts") or []:
        body = part.get("body")
        if not body:
            continue
        author = (part.get("author") or {}).get("type", "")
        role = "user" if author in {"user", "lead", "contact"} else "admin"
        messages.append({"role": role, "text": _truncate(body)})
    return messages


async def _get_conversation(
    client: httpx.AsyncClient, params: dict[str, Any]
) -> dict[str, Any]:
    conv_id = str(params.get("id") or "").strip()
    if not conv_id:
        return {"mode": "real", "error": "missing required param: id"}
    resp = await client.get(f"/conversations/{conv_id}", params={"display_as": "plaintext"})
    resp.raise_for_status()
    conv = resp.json() or {}
    contacts = (conv.get("contacts") or {}).get("contacts") or []
    primary = contacts[0] if contacts else {}
    return {
        "mode": "real",
        "id": str(conv.get("id", conv_id)),
        "state": conv.get("state"),
        "customer": {
            "id": str(primary.get("id", "")) if primary else None,
            "email": primary.get("email") if primary else None,
            "name": primary.get("name") if primary else None,
        },
        "messages": _messages_from_conversation(conv),
    }


async def _send_reply(
    client: httpx.AsyncClient, params: dict[str, Any], admin_id: str
) -> dict[str, Any]:
    conv_id = str(params.get("conversation_id") or "").strip()
    body = str(params.get("body") or "").strip()
    if not conv_id or not body:
        return {
            "mode": "real",
            "error": "missing required params: conversation_id and body",
        }
    payload = {
        "message_type": "comment",
        "type": "admin",
        "admin_id": admin_id,
        "body": body,
    }
    resp = await client.post(f"/conversations/{conv_id}/reply", json=payload)
    resp.raise_for_status()
    data = resp.json() or {}
    # The reply endpoint returns the updated conversation; the new part is
    # typically the last entry in conversation_parts.
    parts = (data.get("conversation_parts") or {}).get("conversation_parts") or []
    last_part_id = parts[-1].get("id") if parts else None
    return {
        "mode": "real",
        "delivered": True,
        "conversation_id": conv_id,
        "conversation_part_id": str(last_part_id) if last_part_id else None,
    }


async def _assign_to_agent(
    client: httpx.AsyncClient, params: dict[str, Any], admin_id: str
) -> dict[str, Any]:
    conv_id = str(params.get("conversation_id") or "").strip()
    agent_id = str(params.get("agent_id") or "").strip()
    if not conv_id or not agent_id:
        return {
            "mode": "real",
            "error": "missing required params: conversation_id and agent_id",
        }
    payload = {
        "message_type": "assignment",
        "type": "admin",
        "admin_id": admin_id,
        "assignee_id": agent_id,
    }
    if note := params.get("note"):
        payload["body"] = str(note)
    resp = await client.post(f"/conversations/{conv_id}/parts", json=payload)
    resp.raise_for_status()
    data = resp.json() or {}
    parts = (data.get("conversation_parts") or {}).get("conversation_parts") or []
    last_part_id = parts[-1].get("id") if parts else None
    return {
        "mode": "real",
        "assigned_to": agent_id,
        "conversation_id": conv_id,
        "conversation_part_id": str(last_part_id) if last_part_id else None,
    }


# ---------------------------------------------------------------------------
# Public adapter
# ---------------------------------------------------------------------------


async def adapter(
    action: str, params: dict[str, Any], creds: Credentials
) -> dict[str, Any]:
    """Dispatch an Intercom action to real REST calls; stub on missing creds."""
    token = creds.get(TOKEN_CRED)
    if not token:
        return _stub_response(action, params, reason=f"missing credential: {TOKEN_CRED}")

    admin_id = creds.get(ADMIN_ID_CRED)
    if action in _WRITE_ACTIONS and not admin_id:
        return _stub_response(
            action,
            params,
            reason=(
                f"missing credential required for write actions: {ADMIN_ID_CRED}. "
                "Read-only Intercom actions still work with just the token."
            ),
        )

    try:
        async with _make_client(token) as client:
            if action == "search_conversations":
                return await _search_conversations(client, params)
            if action == "get_conversation":
                return await _get_conversation(client, params)
            if action == "send_reply":
                return await _send_reply(client, params, str(admin_id))
            if action == "assign_to_agent":
                return await _assign_to_agent(client, params, str(admin_id))
            return {
                "mode": "real",
                "error": f"unknown intercom action: {action}",
            }
    except httpx.HTTPStatusError as exc:
        logger.warning("intercom %s failed: %s", action, exc)
        return {
            "mode": "real",
            "error": (
                f"Intercom {action} returned {exc.response.status_code}: "
                f"{exc.response.text[:200]}"
            ),
        }
    except httpx.HTTPError as exc:
        logger.warning("intercom %s transport error: %s", action, exc)
        return {"mode": "real", "error": f"transport error: {type(exc).__name__}: {exc}"}
