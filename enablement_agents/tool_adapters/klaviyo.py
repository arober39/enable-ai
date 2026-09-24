"""Klaviyo stub adapter — marketing campaigns and profiles.

Credential (placeholder; HTTP is not implemented yet):

  - `KLAVIYO_API_KEY`

Missing creds → `mode: "stub"` with a missing-credential reason.
Creds present → still `mode: "stub"` with `reason: "http_not_implemented"`.
Never returns `mode: "real"` — that label is reserved for an actual API call.
"""

from __future__ import annotations

from typing import Any

from core.credentials import Credentials

TOKEN_CRED = "KLAVIYO_API_KEY"


def _stub_response(action: str, params: dict[str, Any], reason: str) -> dict[str, Any]:
    base = {
        "tool": "klaviyo",
        "action": action,
        "mode": "stub",
        "reason": reason,
        "params": params,
    }
    if action == "list_campaigns":
        return {
            **base,
            "campaigns": [{"id": "cmp_stub_1", "name": "stub campaign", "status": "draft"}],
        }
    if action == "get_profile":
        return {
            **base,
            "email": params.get("email"),
            "profile": {"id": "prf_stub_1", "email": params.get("email")},
        }
    return {**base, "error": f"unknown klaviyo action: {action}"}


async def adapter(action: str, params: dict[str, Any], creds: Credentials) -> dict[str, Any]:
    token = creds.get(TOKEN_CRED)
    if not token:
        return _stub_response(action, params, reason=f"missing credential: {TOKEN_CRED}")
    return _stub_response(action, params, reason="http_not_implemented")
