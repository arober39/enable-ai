"""Real Zendesk adapter — first real tool wiring (Phase 2.2).

Auth: Zendesk REST uses HTTP Basic with `"{email}/token"` as username and
the API token as password. The user adds three credentials in the UI:

  - `ZENDESK_SUBDOMAIN` — e.g., `mycompany` (from mycompany.zendesk.com)
  - `ZENDESK_EMAIL`     — the user the API token belongs to
  - `ZENDESK_API_TOKEN` — API token (Admin → Apps → API → token)

If any are missing the adapter degrades to a stub response — same shape
as the previous stub adapter — with `mode: "stub"` on the result. When
all three are present the adapter calls Zendesk for real and returns
`mode: "real"`. Workflows that consume the response don't need to know
which path ran; the data shape is identical.

API surface (matches the action names the workflow generator already
sees in `ACTION_CATALOG`):

  - search_articles    GET  /api/v2/help_center/articles/search.json
  - get_article        GET  /api/v2/help_center/articles/{id}.json
  - search_tickets     GET  /api/v2/search.json?query=type:ticket+{q}
  - get_ticket         GET  /api/v2/tickets/{id}.json
  - create_internal_note POST /api/v2/tickets/{id}/comments.json (public=false)

Article bodies are truncated to 500 chars in the response so the
workflow context doesn't balloon.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from core.credentials import Credentials

logger = logging.getLogger(__name__)

#: Required credential names. Adapter degrades to stub if any are missing.
REQUIRED_CREDS = ("ZENDESK_SUBDOMAIN", "ZENDESK_EMAIL", "ZENDESK_API_TOKEN")

#: Per-call HTTP timeout. Zendesk's search can be slow on large instances.
_TIMEOUT_SECONDS = 15.0

#: Cap on article body length in responses (chars). Keeps workflow context lean.
_BODY_TRUNCATE = 500


# ---------------------------------------------------------------------------
# Test seam — tests monkey-patch this to inject a MockTransport.
# Returning AsyncClient lets the adapter use `async with` cleanly.
# ---------------------------------------------------------------------------


def _make_client(base_url: str, auth: httpx.BasicAuth) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, auth=auth, timeout=_TIMEOUT_SECONDS)


# ---------------------------------------------------------------------------
# Stub responses — used when creds are missing. Shape matches real responses.
# ---------------------------------------------------------------------------


def _stub_response(action: str, params: dict[str, Any], reason: str) -> dict[str, Any]:
    base = {
        "tool": "zendesk",
        "action": action,
        "mode": "stub",
        "reason": reason,
        "params": params,
    }
    if action == "search_articles":
        return {**base, "articles": [{"id": "kb_stub_1", "title": "Sample article", "body": "stub body"}]}
    if action == "get_article":
        return {**base, "id": params.get("id"), "title": "stub", "body": "stub body"}
    if action == "search_tickets":
        return {**base, "tickets": [{"id": "tkt_stub_1", "subject": "stub", "status": "open"}]}
    if action == "get_ticket":
        return {**base, "id": params.get("id"), "subject": "stub", "status": "open"}
    if action == "create_internal_note":
        return {**base, "created": True, "comment_id": "comment_stub_1"}
    return {**base, "error": f"unknown zendesk action: {action}"}


# ---------------------------------------------------------------------------
# Real Zendesk calls
# ---------------------------------------------------------------------------


def _truncate(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return text if len(text) <= _BODY_TRUNCATE else text[:_BODY_TRUNCATE] + "…"


async def _search_articles(client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("query") or "").strip()
    if not query:
        return {"mode": "real", "articles": [], "error": "missing required param: query"}
    resp = await client.get(
        "/api/v2/help_center/articles/search.json",
        params={"query": query, "per_page": 5},
    )
    resp.raise_for_status()
    data = resp.json() or {}
    return {
        "mode": "real",
        "articles": [
            {
                "id": str(a.get("id", "")),
                "title": a.get("title") or "",
                "body": _truncate(a.get("body") or ""),
                "url": a.get("html_url"),
            }
            for a in (data.get("results") or [])[:5]
        ],
    }


async def _get_article(client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any]:
    article_id = str(params.get("id") or "").strip()
    if not article_id:
        return {"mode": "real", "error": "missing required param: id"}
    resp = await client.get(f"/api/v2/help_center/articles/{article_id}.json")
    resp.raise_for_status()
    article = (resp.json() or {}).get("article") or {}
    return {
        "mode": "real",
        "id": str(article.get("id", article_id)),
        "title": article.get("title") or "",
        "body": _truncate(article.get("body") or ""),
        "url": article.get("html_url"),
    }


async def _search_tickets(client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("query") or "").strip()
    full_query = f"type:ticket {query}".strip()
    resp = await client.get(
        "/api/v2/search.json", params={"query": full_query, "per_page": 5}
    )
    resp.raise_for_status()
    data = resp.json() or {}
    return {
        "mode": "real",
        "tickets": [
            {
                "id": str(t.get("id", "")),
                "subject": t.get("subject") or "",
                "status": t.get("status") or "",
                "priority": t.get("priority"),
            }
            for t in (data.get("results") or [])[:5]
        ],
    }


async def _get_ticket(client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any]:
    ticket_id = str(params.get("id") or "").strip()
    if not ticket_id:
        return {"mode": "real", "error": "missing required param: id"}
    resp = await client.get(f"/api/v2/tickets/{ticket_id}.json")
    resp.raise_for_status()
    ticket = (resp.json() or {}).get("ticket") or {}
    return {
        "mode": "real",
        "id": str(ticket.get("id", ticket_id)),
        "subject": ticket.get("subject") or "",
        "description": _truncate(ticket.get("description") or ""),
        "status": ticket.get("status") or "",
        "priority": ticket.get("priority"),
        "requester_id": ticket.get("requester_id"),
    }


async def _create_internal_note(
    client: httpx.AsyncClient, params: dict[str, Any]
) -> dict[str, Any]:
    ticket_id = str(params.get("ticket_id") or "").strip()
    body = str(params.get("body") or "").strip()
    if not ticket_id or not body:
        return {
            "mode": "real",
            "error": "missing required params: ticket_id and body",
        }
    payload = {
        "ticket": {
            "comment": {"body": body, "public": False},
        }
    }
    resp = await client.put(f"/api/v2/tickets/{ticket_id}.json", json=payload)
    resp.raise_for_status()
    data = resp.json() or {}
    audit = (data.get("audit") or {})
    return {
        "mode": "real",
        "created": True,
        "ticket_id": ticket_id,
        "audit_id": audit.get("id"),
    }


# ---------------------------------------------------------------------------
# Public adapter
# ---------------------------------------------------------------------------


async def adapter(
    action: str, params: dict[str, Any], creds: Credentials
) -> dict[str, Any]:
    """Dispatch a Zendesk action to real REST calls; fall back to stub on missing creds."""
    subdomain = creds.get("ZENDESK_SUBDOMAIN")
    email = creds.get("ZENDESK_EMAIL")
    token = creds.get("ZENDESK_API_TOKEN")
    missing = [
        name
        for name, value in zip(
            REQUIRED_CREDS, (subdomain, email, token), strict=True
        )
        if not value
    ]
    if missing:
        return _stub_response(
            action,
            params,
            reason=f"missing credentials in vault: {missing}",
        )

    base_url = f"https://{subdomain}.zendesk.com"
    auth = httpx.BasicAuth(f"{email}/token", token or "")
    try:
        async with _make_client(base_url, auth) as client:
            if action == "search_articles":
                return await _search_articles(client, params)
            if action == "get_article":
                return await _get_article(client, params)
            if action == "search_tickets":
                return await _search_tickets(client, params)
            if action == "get_ticket":
                return await _get_ticket(client, params)
            if action == "create_internal_note":
                return await _create_internal_note(client, params)
            return {
                "mode": "real",
                "error": f"unknown zendesk action: {action}",
            }
    except httpx.HTTPStatusError as exc:
        logger.warning("zendesk %s failed: %s", action, exc)
        return {
            "mode": "real",
            "error": (
                f"Zendesk {action} returned "
                f"{exc.response.status_code}: {exc.response.text[:200]}"
            ),
        }
    except httpx.HTTPError as exc:
        logger.warning("zendesk %s transport error: %s", action, exc)
        return {"mode": "real", "error": f"transport error: {type(exc).__name__}: {exc}"}
