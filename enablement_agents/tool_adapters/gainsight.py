"""Gainsight stub adapter — CS health / CTA lookups.

Credential (placeholder; HTTP is not implemented yet):

  - `GAINSIGHT_API_KEY`

Missing creds → `mode: "stub"` with a missing-credential reason.
Creds present → still `mode: "stub"` with `reason: "http_not_implemented"`.
Never returns `mode: "real"` — that label is reserved for an actual API call.
"""

from __future__ import annotations

from typing import Any

from core.credentials import Credentials

TOKEN_CRED = "GAINSIGHT_API_KEY"


def _stub_response(action: str, params: dict[str, Any], reason: str) -> dict[str, Any]:
    base = {
        "tool": "gainsight",
        "action": action,
        "mode": "stub",
        "reason": reason,
        "params": params,
    }
    if action == "get_account_health":
        return {
            **base,
            "account_id": params.get("account_id"),
            "health": "green",
            "score": 80,
        }
    if action == "list_ctas":
        return {
            **base,
            "ctas": [{"id": "cta_stub_1", "name": "Renewal risk", "status": "open"}],
        }
    return {**base, "error": f"unknown gainsight action: {action}"}


async def adapter(
    action: str, params: dict[str, Any], creds: Credentials
) -> dict[str, Any]:
    token = creds.get(TOKEN_CRED)
    if not token:
        return _stub_response(action, params, reason=f"missing credential: {TOKEN_CRED}")
    return _stub_response(action, params, reason="http_not_implemented")
