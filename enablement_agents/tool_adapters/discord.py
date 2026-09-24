"""Discord stub adapter — DevRel community channels.

Credential (placeholder; HTTP is not implemented yet):

  - `DISCORD_BOT_TOKEN`

Missing creds → `mode: "stub"` with a missing-credential reason.
Creds present → still `mode: "stub"` with `reason: "http_not_implemented"`.
Never returns `mode: "real"` — that label is reserved for an actual API call.
"""

from __future__ import annotations

from typing import Any

from core.credentials import Credentials

TOKEN_CRED = "DISCORD_BOT_TOKEN"


def _stub_response(action: str, params: dict[str, Any], reason: str) -> dict[str, Any]:
    base = {
        "tool": "discord",
        "action": action,
        "mode": "stub",
        "reason": reason,
        "params": params,
    }
    if action == "list_channels":
        return {
            **base,
            "channels": [{"id": "ch_stub_1", "name": "general"}],
        }
    if action == "search_messages":
        return {
            **base,
            "messages": [{"id": "msg_stub_1", "content": "stub message"}],
        }
    return {**base, "error": f"unknown discord action: {action}"}


async def adapter(action: str, params: dict[str, Any], creds: Credentials) -> dict[str, Any]:
    token = creds.get(TOKEN_CRED)
    if not token:
        return _stub_response(action, params, reason=f"missing credential: {TOKEN_CRED}")
    return _stub_response(action, params, reason="http_not_implemented")
