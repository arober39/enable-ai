"""Tests for the Slack adapter.

All HTTP calls are intercepted via httpx.MockTransport — no network
calls leave the test process. Missing `SLACK_BOT_TOKEN` degrades to stub.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from enablement_agents.tool_adapters import slack


class _FakeCreds:
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
    return _FakeCreds({"SLACK_BOT_TOKEN": "xoxb-test-token"})


def _patched_client(router, monkeypatch):
    transport = httpx.MockTransport(router)

    def factory(token: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="https://slack.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            transport=transport,
            timeout=15.0,
        )

    monkeypatch.setattr(slack, "_make_client", factory)


# ---------------------------------------------------------------------------
# Stub-fallback path
# ---------------------------------------------------------------------------


async def test_missing_token_returns_stub():
    out = await slack.adapter(
        "post_message", {"channel": "C1", "text": "hi"}, _FakeCreds({})
    )
    assert out["mode"] == "stub"
    assert "SLACK_BOT_TOKEN" in out["reason"]
    assert out["ts"] == "1700000000.0001"
    assert out["channel"] == "C1"


async def test_stub_shape_matches_real_shape_for_each_action():
    actions_and_keys = [
        ("post_message", {"channel": "C1", "text": "hi"}, "ts"),
        ("list_channels", {}, "channels"),
        ("get_channel_history", {"channel": "C1"}, "messages"),
    ]
    creds = _FakeCreds({})
    for action, params, top_key in actions_and_keys:
        out = await slack.adapter(action, params, creds)
        assert out["mode"] == "stub"
        assert top_key in out, f"missing key {top_key!r} for action {action!r}"


# ---------------------------------------------------------------------------
# Real-call paths
# ---------------------------------------------------------------------------


async def test_post_message_hits_chat_post_message(real_creds, monkeypatch):
    captured: dict[str, Any] = {}

    def router(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/chat.postMessage"
        captured["auth"] = request.headers.get("Authorization", "")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"ok": True, "ts": "1710000000.1234", "channel": "C99"}
        )

    _patched_client(router, monkeypatch)
    out = await slack.adapter(
        "post_message", {"channel": "C99", "text": "hello"}, real_creds
    )
    assert out["mode"] == "real"
    assert out["ts"] == "1710000000.1234"
    assert out["channel"] == "C99"
    assert captured["auth"] == "Bearer xoxb-test-token"
    assert captured["body"] == {"channel": "C99", "text": "hello"}


async def test_list_channels_real(real_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/conversations.list"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "channels": [{"id": "C1", "name": "general"}, {"id": "C2", "name": "eng"}],
            },
        )

    _patched_client(router, monkeypatch)
    out = await slack.adapter("list_channels", {}, real_creds)
    assert out["mode"] == "real"
    assert [c["name"] for c in out["channels"]] == ["general", "eng"]


async def test_get_channel_history_real(real_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/conversations.history"
        assert request.url.params.get("channel") == "C1"
        return httpx.Response(
            200,
            json={"ok": True, "messages": [{"ts": "1.0", "text": "yo"}]},
        )

    _patched_client(router, monkeypatch)
    out = await slack.adapter(
        "get_channel_history", {"channel": "C1", "limit": 5}, real_creds
    )
    assert out["mode"] == "real"
    assert out["messages"][0]["text"] == "yo"


async def test_ok_false_returns_structured_error(real_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "error": "channel_not_found"})

    _patched_client(router, monkeypatch)
    out = await slack.adapter(
        "post_message", {"channel": "Cmissing", "text": "hi"}, real_creds
    )
    assert out["mode"] == "real"
    assert "channel_not_found" in out["error"]


async def test_http_error_returns_structured_error(real_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid_auth")

    _patched_client(router, monkeypatch)
    out = await slack.adapter(
        "post_message", {"channel": "C1", "text": "hi"}, real_creds
    )
    assert out["mode"] == "real"
    assert "401" in out["error"]


async def test_missing_param_short_circuits(real_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        pytest.fail("should not call Slack when required params missing")
        return httpx.Response(500)

    _patched_client(router, monkeypatch)
    out = await slack.adapter("post_message", {"channel": "C1"}, real_creds)
    assert "text" in out["error"]
    out = await slack.adapter("get_channel_history", {}, real_creds)
    assert "channel" in out["error"]


async def test_unknown_action_returns_error(real_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    _patched_client(router, monkeypatch)
    out = await slack.adapter("nuke_workspace", {}, real_creds)
    assert out["mode"] == "real"
    assert "error" in out
