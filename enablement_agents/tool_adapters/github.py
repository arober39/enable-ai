"""GitHub stub adapter — issues / PRs for DevRel workflows.

Credential (placeholder; HTTP is not implemented yet):

  - `GITHUB_TOKEN`

Missing creds → `mode: "stub"` with a missing-credential reason.
Creds present → still `mode: "stub"` with `reason: "http_not_implemented"`.
Never returns `mode: "real"` — that label is reserved for an actual API call.
"""

from __future__ import annotations

from typing import Any

from core.credentials import Credentials

TOKEN_CRED = "GITHUB_TOKEN"


def _stub_response(action: str, params: dict[str, Any], reason: str) -> dict[str, Any]:
    base = {
        "tool": "github",
        "action": action,
        "mode": "stub",
        "reason": reason,
        "params": params,
    }
    if action == "get_issue":
        return {
            **base,
            "id": params.get("number"),
            "title": "stub issue",
            "state": "open",
        }
    if action == "search_issues":
        return {
            **base,
            "issues": [{"id": "1", "title": "stub issue", "state": "open"}],
        }
    return {**base, "error": f"unknown github action: {action}"}


async def adapter(
    action: str, params: dict[str, Any], creds: Credentials
) -> dict[str, Any]:
    token = creds.get(TOKEN_CRED)
    if not token:
        return _stub_response(action, params, reason=f"missing credential: {TOKEN_CRED}")
    return _stub_response(action, params, reason="http_not_implemented")
