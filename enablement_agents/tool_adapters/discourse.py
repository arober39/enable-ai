"""Discourse stub adapter — DevRel docs and forum topics.

Credential (placeholder; HTTP is not implemented yet):

  - `DISCOURSE_API_KEY`

Missing creds → `mode: "stub"` with a missing-credential reason.
Creds present → still `mode: "stub"` with `reason: "http_not_implemented"`.
Never returns `mode: "real"` — that label is reserved for an actual API call.
"""

from __future__ import annotations

from typing import Any

from core.credentials import Credentials

TOKEN_CRED = "DISCOURSE_API_KEY"


def _stub_response(action: str, params: dict[str, Any], reason: str) -> dict[str, Any]:
    base = {
        "tool": "discourse",
        "action": action,
        "mode": "stub",
        "reason": reason,
        "params": params,
    }
    if action == "search_topics":
        return {
            **base,
            "topics": [{"id": "topic_stub_1", "title": "stub topic"}],
        }
    if action == "get_topic":
        return {
            **base,
            "id": params.get("id"),
            "title": "stub topic",
            "posts": [{"id": "post_stub_1", "raw": "stub body"}],
        }
    return {**base, "error": f"unknown discourse action: {action}"}


async def adapter(action: str, params: dict[str, Any], creds: Credentials) -> dict[str, Any]:
    token = creds.get(TOKEN_CRED)
    if not token:
        return _stub_response(action, params, reason=f"missing credential: {TOKEN_CRED}")
    return _stub_response(action, params, reason="http_not_implemented")
