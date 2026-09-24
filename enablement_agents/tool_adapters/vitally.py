"""Vitally stub adapter — CS account health.

Credential (placeholder; HTTP is not implemented yet):

  - `VITALLY_API_KEY`

Missing creds → `mode: "stub"` with a missing-credential reason.
Creds present → still `mode: "stub"` with `reason: "http_not_implemented"`.
Never returns `mode: "real"` — that label is reserved for an actual API call.
"""

from __future__ import annotations

from typing import Any

from core.credentials import Credentials

TOKEN_CRED = "VITALLY_API_KEY"


def _stub_response(action: str, params: dict[str, Any], reason: str) -> dict[str, Any]:
    base = {
        "tool": "vitally",
        "action": action,
        "mode": "stub",
        "reason": reason,
        "params": params,
    }
    if action == "get_account":
        return {
            **base,
            "account": {
                "id": params.get("account_id"),
                "name": "stub account",
                "health": "healthy",
            },
        }
    if action == "list_accounts":
        return {
            **base,
            "accounts": [{"id": "acct_stub_1", "name": "Sample account", "health": "healthy"}],
        }
    return {**base, "error": f"unknown vitally action: {action}"}


async def adapter(
    action: str, params: dict[str, Any], creds: Credentials
) -> dict[str, Any]:
    token = creds.get(TOKEN_CRED)
    if not token:
        return _stub_response(action, params, reason=f"missing credential: {TOKEN_CRED}")
    return _stub_response(action, params, reason="http_not_implemented")
