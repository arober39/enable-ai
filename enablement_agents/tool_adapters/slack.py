"""Slack adapter — real Web API when `SLACK_BOT_TOKEN` is set.

Auth: Bearer token in the `Authorization` header. One credential:

  - `SLACK_BOT_TOKEN` — bot token (`xoxb-...`) from a Slack app
    (OAuth & Permissions → Bot User OAuth Token).

If the token is missing the adapter degrades to a stub response — same
shape as the previous always-stub adapter — with `mode: "stub"` on the
result. When the token is present the adapter calls Slack for real and
returns `mode: "real"`. Workflows that consume the response don't need
to know which path ran; the data shape is identical.

API surface (matches the action names already in `ACTION_CATALOG`):

  - post_message         POST /api/chat.postMessage
  - list_channels        GET  /api/conversations.list
  - get_channel_history  GET  /api/conversations.history
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from core.credentials import Credentials

logger = logging.getLogger(__name__)

TOKEN_CRED = "SLACK_BOT_TOKEN"

_BASE_URL = "https://slack.com"
_TIMEOUT_SECONDS = 15.0


# ---------------------------------------------------------------------------
# Test seam — tests monkey-patch this to inject a MockTransport.
# ---------------------------------------------------------------------------


def _make_client(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=_BASE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=_TIMEOUT_SECONDS,
    )


# ---------------------------------------------------------------------------
# Stub responses — used when creds are missing. Shape matches real responses.
# ---------------------------------------------------------------------------


def _stub_response(action: str, params: dict[str, Any], reason: str) -> dict[str, Any]:
    base = {
        "tool": "slack",
        "action": action,
        "mode": "stub",
        "reason": reason,
        "params": params,
    }
    if action == "post_message":
        return {**base, "ts": "1700000000.0001", "channel": params.get("channel")}
    if action == "list_channels":
        return {**base, "channels": [{"id": "C123", "name": "general"}]}
    if action == "get_channel_history":
        return {**base, "messages": [{"ts": "1", "text": "stub"}]}
    return {**base, "error": f"unknown slack action: {action}"}


# ---------------------------------------------------------------------------
# Real Slack Web API calls
# ---------------------------------------------------------------------------


def _slack_error(data: dict[str, Any]) -> str:
    return str(data.get("error") or "unknown")


async def _post_message(client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any]:
    channel = str(params.get("channel") or "").strip()
    text = str(params.get("text") or "").strip()
    if not channel or not text:
        return {"mode": "real", "error": "missing required params: channel and text"}
    resp = await client.post(
        "/api/chat.postMessage", json={"channel": channel, "text": text}
    )
    resp.raise_for_status()
    data = resp.json() or {}
    if not data.get("ok"):
        return {"mode": "real", "error": f"slack error: {_slack_error(data)}"}
    return {
        "mode": "real",
        "ts": data.get("ts"),
        "channel": data.get("channel") or channel,
    }


async def _list_channels(client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any]:
    resp = await client.get(
        "/api/conversations.list",
        params={"limit": 20, "exclude_archived": "true"},
    )
    resp.raise_for_status()
    data = resp.json() or {}
    if not data.get("ok"):
        return {"mode": "real", "error": f"slack error: {_slack_error(data)}", "channels": []}
    return {
        "mode": "real",
        "channels": [
            {"id": c.get("id") or "", "name": c.get("name") or ""}
            for c in (data.get("channels") or [])[:20]
        ],
    }


async def _get_channel_history(
    client: httpx.AsyncClient, params: dict[str, Any]
) -> dict[str, Any]:
    channel = str(params.get("channel") or "").strip()
    if not channel:
        return {"mode": "real", "error": "missing required param: channel"}
    limit = int(params.get("limit") or 10)
    resp = await client.get(
        "/api/conversations.history",
        params={"channel": channel, "limit": limit},
    )
    resp.raise_for_status()
    data = resp.json() or {}
    if not data.get("ok"):
        return {"mode": "real", "error": f"slack error: {_slack_error(data)}", "messages": []}
    return {
        "mode": "real",
        "messages": [
            {"ts": m.get("ts") or "", "text": m.get("text") or ""}
            for m in (data.get("messages") or [])[:limit]
        ],
    }


# ---------------------------------------------------------------------------
# Public adapter
# ---------------------------------------------------------------------------


async def adapter(
    action: str, params: dict[str, Any], creds: Credentials
) -> dict[str, Any]:
    """Dispatch a Slack action to real REST calls; fall back to stub on missing creds."""
    token = creds.get(TOKEN_CRED)
    if not token:
        return _stub_response(action, params, reason=f"missing credential: {TOKEN_CRED}")

    try:
        async with _make_client(token) as client:
            if action == "post_message":
                return await _post_message(client, params)
            if action == "list_channels":
                return await _list_channels(client, params)
            if action == "get_channel_history":
                return await _get_channel_history(client, params)
            return {"mode": "real", "error": f"unknown slack action: {action}"}
    except httpx.HTTPStatusError as exc:
        logger.warning("slack %s failed: %s", action, exc)
        return {
            "mode": "real",
            "error": (
                f"Slack {action} returned {exc.response.status_code}: "
                f"{exc.response.text[:200]}"
            ),
        }
    except httpx.HTTPError as exc:
        logger.warning("slack %s transport error: %s", action, exc)
        return {"mode": "real", "error": f"transport error: {type(exc).__name__}: {exc}"}
