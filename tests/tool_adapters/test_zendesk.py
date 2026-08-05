"""Tests for the real Zendesk adapter (Phase 2.2).

All HTTP calls are intercepted via httpx.MockTransport — no network
calls leave the test process. The adapter degrades to stub responses
when any required credential is missing, so we cover both paths.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from enablement_agents.tool_adapters import zendesk


class _FakeCreds:
    """Minimal Credentials impl backed by a dict."""

    def __init__(self, data: dict[str, str]):
        self._d = data

    def get(self, key: str) -> str | None:
        return self._d.get(key)

    def require(self, key: str) -> str:
        v = self.get(key)
        if v is None:
            raise KeyError(key)
        return v


@pytest.fixture
def real_creds() -> _FakeCreds:
    return _FakeCreds(
        {
            "ZENDESK_SUBDOMAIN": "mycompany",
            "ZENDESK_EMAIL": "user@example.com",
            "ZENDESK_API_TOKEN": "TOKEN",
        }
    )


def _patched_client(router, monkeypatch):
    """Install a MockTransport-backed AsyncClient as the adapter's client factory."""
    transport = httpx.MockTransport(router)

    def factory(base_url: str, auth: httpx.BasicAuth) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url, auth=auth, transport=transport, timeout=15.0
        )

    monkeypatch.setattr(zendesk, "_make_client", factory)


# ---------------------------------------------------------------------------
# Stub-fallback path
# ---------------------------------------------------------------------------


async def test_missing_all_creds_returns_stub():
    out = await zendesk.adapter("search_articles", {"query": "x"}, _FakeCreds({}))
    assert out["mode"] == "stub"
    assert "missing credentials" in out["reason"]
    assert len(out["articles"]) == 1


async def test_partial_creds_returns_stub():
    creds = _FakeCreds({"ZENDESK_SUBDOMAIN": "mycompany"})
    out = await zendesk.adapter("get_article", {"id": "1"}, creds)
    assert out["mode"] == "stub"


async def test_stub_shape_matches_real_shape_for_each_action():
    """Critical: workflows can't tell real from stub by shape."""
    actions_and_keys = [
        ("search_articles", {"query": "x"}, "articles"),
        ("get_article", {"id": "1"}, "id"),
        ("search_tickets", {"query": "x"}, "tickets"),
        ("get_ticket", {"id": "1"}, "id"),
        ("create_internal_note", {"ticket_id": "1", "body": "n"}, "created"),
    ]
    creds = _FakeCreds({})
    for action, params, top_key in actions_and_keys:
        out = await zendesk.adapter(action, params, creds)
        assert out["mode"] == "stub"
        assert top_key in out, f"missing key {top_key!r} for action {action!r}"


# ---------------------------------------------------------------------------
# Real-call paths
# ---------------------------------------------------------------------------


async def test_search_articles_truncates_body_and_caps_results(
    real_creds, monkeypatch
):
    def router(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "mycompany.zendesk.com"
        assert "/help_center/articles/search.json" in str(request.url)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"id": i, "title": f"t{i}", "body": "X" * 1000, "html_url": "u"}
                    for i in range(10)
                ]
            },
        )

    _patched_client(router, monkeypatch)
    out = await zendesk.adapter("search_articles", {"query": "x"}, real_creds)
    assert out["mode"] == "real"
    assert len(out["articles"]) == 5  # capped at 5
    assert out["articles"][0]["body"].endswith("…")  # truncated


async def test_create_internal_note_sets_public_false(real_creds, monkeypatch):
    captured: dict[str, Any] = {}

    def router(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert "/tickets/42.json" in str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"audit": {"id": 999}})

    _patched_client(router, monkeypatch)
    out = await zendesk.adapter(
        "create_internal_note",
        {"ticket_id": "42", "body": "internal note"},
        real_creds,
    )
    assert out["mode"] == "real"
    assert out["audit_id"] == 999
    assert captured["body"]["ticket"]["comment"]["public"] is False


async def test_search_tickets_prefixes_type_query(real_creds, monkeypatch):
    captured_params: dict[str, str] = {}

    def router(request: httpx.Request) -> httpx.Response:
        captured_params.update(dict(request.url.params))
        return httpx.Response(200, json={"results": []})

    _patched_client(router, monkeypatch)
    await zendesk.adapter("search_tickets", {"query": "priority:high"}, real_creds)
    assert "type:ticket" in captured_params.get("query", "")


async def test_http_error_returns_structured_error(real_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="not authorized")

    _patched_client(router, monkeypatch)
    out = await zendesk.adapter("get_article", {"id": "1"}, real_creds)
    assert out["mode"] == "real"
    assert "401" in out["error"]


async def test_missing_param_returns_graceful_error(real_creds, monkeypatch):
    """Calling search_articles without a query short-circuits before the HTTP call."""

    def router(request: httpx.Request) -> httpx.Response:
        pytest.fail("should not call the API when required params missing")
        return httpx.Response(500)  # unreachable

    _patched_client(router, monkeypatch)
    out = await zendesk.adapter("search_articles", {}, real_creds)
    assert "error" in out
    assert "query" in out["error"]


async def test_unknown_action_returns_error(real_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    _patched_client(router, monkeypatch)
    out = await zendesk.adapter("nuke_account", {}, real_creds)
    assert "error" in out


async def test_basic_auth_uses_email_slash_token(real_creds, monkeypatch):
    captured_auth: dict[str, str] = {}

    def router(request: httpx.Request) -> httpx.Response:
        captured_auth["header"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json={"results": []})

    _patched_client(router, monkeypatch)
    await zendesk.adapter("search_articles", {"query": "x"}, real_creds)
    # Basic auth header is base64-encoded "{email}/token:{api_token}"
    import base64

    assert captured_auth["header"].startswith("Basic ")
    decoded = base64.b64decode(captured_auth["header"].split(" ", 1)[1]).decode()
    assert decoded == "user@example.com/token:TOKEN"
