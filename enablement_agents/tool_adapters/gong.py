"""Gong stub adapter — call search / transcripts.

Credential (placeholder; HTTP is not implemented yet):

  - `GONG_API_KEY`

Missing creds → `mode: "stub"` with a missing-credential reason.
Creds present → still `mode: "stub"` with `reason: "http_not_implemented"`.
Never returns `mode: "real"` — that label is reserved for an actual API call.
"""

from __future__ import annotations

from typing import Any

from core.credentials import Credentials

TOKEN_CRED = "GONG_API_KEY"


def _stub_response(action: str, params: dict[str, Any], reason: str) -> dict[str, Any]:
    base = {
        "tool": "gong",
        "action": action,
        "mode": "stub",
        "reason": reason,
        "params": params,
    }
    if action == "search_calls":
        return {
            **base,
            "calls": [
                {"id": "call_stub_1", "title": "Sample call", "started": "2026-01-15"}
            ],
        }
    if action == "get_transcript":
        return {
            **base,
            "call_id": params.get("call_id"),
            "transcript": "stub transcript",
        }
    return {**base, "error": f"unknown gong action: {action}"}


async def adapter(
    action: str, params: dict[str, Any], creds: Credentials
) -> dict[str, Any]:
    token = creds.get(TOKEN_CRED)
    if not token:
        return _stub_response(action, params, reason=f"missing credential: {TOKEN_CRED}")
    return _stub_response(action, params, reason="http_not_implemented")
