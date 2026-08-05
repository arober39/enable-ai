"""Tests for the real Intercom adapter (Phase 2.3).

All HTTP intercepted via httpx.MockTransport. The adapter degrades to
stub responses when the token is missing, and stubs write actions
specifically when only the admin id is missing.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from enablement_agents.tool_adapters import intercom


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
def read_only_creds() -> _FakeCreds:
    """Token but no admin id — read actions real, write actions stub."""
    return _FakeCreds({"INTERCOM_API_TOKEN": "TOKEN"})


@pytest.fixture
def full_creds() -> _FakeCreds:
    return _FakeCreds(
        {"INTERCOM_API_TOKEN": "TOKEN", "INTERCOM_ADMIN_ID": "99"}
    )


def _patched_client(router, monkeypatch):
    transport = httpx.MockTransport(router)

    def factory(token: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="https://api.intercom.io",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Intercom-Version": intercom.INTERCOM_API_VERSION,
            },
            transport=transport,
            timeout=15.0,
        )

    monkeypatch.setattr(intercom, "_make_client", factory)


# ---------------------------------------------------------------------------
# Stub-fallback paths
# ---------------------------------------------------------------------------


async def test_missing_token_returns_stub_for_all_actions():
    creds = _FakeCreds({})
    for action, params in [
        ("search_conversations", {"query": "x"}),
        ("get_conversation", {"id": "1"}),
        ("send_reply", {"conversation_id": "1", "body": "hi"}),
        ("assign_to_agent", {"conversation_id": "1", "agent_id": "2"}),
    ]:
        out = await intercom.adapter(action, params, creds)
        assert out["mode"] == "stub", action
        assert "INTERCOM_API_TOKEN" in out["reason"]


async def test_token_only_makes_writes_stub_but_reads_real(
    read_only_creds, monkeypatch
):
    """Writes stub on missing admin id; reads still hit the API."""

    def router(request: httpx.Request) -> httpx.Response:
        # Read endpoints — return a valid plaintext conversation
        assert "/conversations/" in str(request.url)
        return httpx.Response(
            200,
            json={
                "id": "1",
                "state": "open",
                "contacts": {"contacts": [{"id": "ct1", "email": "u@example.com", "name": "U"}]},
                "source": {"body": "Hello", "type": "conversation", "author": {"type": "user"}},
                "conversation_parts": {"conversation_parts": []},
            },
        )

    _patched_client(router, monkeypatch)

    # Read goes real
    out = await intercom.adapter("get_conversation", {"id": "1"}, read_only_creds)
    assert out["mode"] == "real"
    assert out["customer"]["email"] == "u@example.com"

    # Write stubs out
    out = await intercom.adapter(
        "send_reply",
        {"conversation_id": "1", "body": "hi"},
        read_only_creds,
    )
    assert out["mode"] == "stub"
    assert "INTERCOM_ADMIN_ID" in out["reason"]


async def test_stub_shape_matches_real_shape():
    """The downstream workflow can't tell real from stub by shape."""
    creds = _FakeCreds({})
    actions_and_keys = [
        ("search_conversations", {"query": "x"}, "results"),
        ("get_conversation", {"id": "1"}, "messages"),
        ("send_reply", {"conversation_id": "1", "body": "n"}, "delivered"),
        ("assign_to_agent", {"conversation_id": "1", "agent_id": "2"}, "assigned_to"),
    ]
    for action, params, key in actions_and_keys:
        out = await intercom.adapter(action, params, creds)
        assert out["mode"] == "stub"
        assert key in out, f"missing key {key!r} for action {action!r}"


# ---------------------------------------------------------------------------
# Real-call paths
# ---------------------------------------------------------------------------


async def test_get_conversation_flattens_to_role_text_messages(
    full_creds, monkeypatch
):
    def router(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/conversations/abc" in str(request.url)
        assert request.url.params.get("display_as") == "plaintext"
        return httpx.Response(
            200,
            json={
                "id": "abc",
                "state": "open",
                "contacts": {"contacts": [{"id": "ct1", "email": "x@y.z", "name": "Cust"}]},
                "source": {"body": "First customer message", "author": {"type": "user"}},
                "conversation_parts": {
                    "conversation_parts": [
                        {"body": "Hi, how can I help?", "author": {"type": "admin"}},
                        {"body": "I have a billing issue", "author": {"type": "user"}},
                        {"body": "(internal note)", "author": {"type": "admin"}},
                    ]
                },
            },
        )

    _patched_client(router, monkeypatch)
    out = await intercom.adapter("get_conversation", {"id": "abc"}, full_creds)
    assert out["mode"] == "real"
    assert [m["role"] for m in out["messages"]] == ["user", "admin", "user", "admin"]
    assert out["messages"][0]["text"] == "First customer message"
    assert out["customer"]["email"] == "x@y.z"


async def test_search_conversations_uses_substring_query(full_creds, monkeypatch):
    captured: dict[str, Any] = {}

    def router(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/conversations/search"
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "conversations": [
                    {
                        "id": 12345,
                        "source": {"subject": "Refund question", "body": "Need help"},
                        "state": "open",
                        "updated_at": 1700000000,
                    }
                ]
            },
        )

    _patched_client(router, monkeypatch)
    out = await intercom.adapter("search_conversations", {"query": "refund"}, full_creds)
    assert out["mode"] == "real"
    assert out["results"][0]["id"] == "12345"
    assert out["results"][0]["subject"] == "Refund question"
    body = captured["body"]
    assert body["query"]["field"] == "source.body"
    assert body["query"]["operator"] == "~"
    assert body["query"]["value"] == "refund"


async def test_send_reply_sets_admin_id_and_comment_type(full_creds, monkeypatch):
    captured: dict[str, Any] = {}

    def router(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/conversations/77/reply" in str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "conversation_parts": {
                    "conversation_parts": [{"id": "part_42"}],
                }
            },
        )

    _patched_client(router, monkeypatch)
    out = await intercom.adapter(
        "send_reply",
        {"conversation_id": "77", "body": "Hi there"},
        full_creds,
    )
    assert out["mode"] == "real"
    assert out["delivered"] is True
    assert out["conversation_part_id"] == "part_42"
    assert captured["body"] == {
        "message_type": "comment",
        "type": "admin",
        "admin_id": "99",
        "body": "Hi there",
    }


async def test_assign_to_agent_sets_assignment_payload(full_creds, monkeypatch):
    captured: dict[str, Any] = {}

    def router(request: httpx.Request) -> httpx.Response:
        assert "/conversations/77/parts" in str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"conversation_parts": {"conversation_parts": [{"id": "part_99"}]}},
        )

    _patched_client(router, monkeypatch)
    out = await intercom.adapter(
        "assign_to_agent",
        {"conversation_id": "77", "agent_id": "5", "note": "tier-1 escalation"},
        full_creds,
    )
    assert out["mode"] == "real"
    assert out["assigned_to"] == "5"
    assert captured["body"]["message_type"] == "assignment"
    assert captured["body"]["admin_id"] == "99"
    assert captured["body"]["assignee_id"] == "5"
    assert captured["body"]["body"] == "tier-1 escalation"


async def test_http_error_returns_structured_error(full_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid token")

    _patched_client(router, monkeypatch)
    out = await intercom.adapter("get_conversation", {"id": "1"}, full_creds)
    assert out["mode"] == "real"
    assert "401" in out["error"]


async def test_missing_param_short_circuits(full_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        pytest.fail("should not call API when required params missing")
        return httpx.Response(500)  # unreachable

    _patched_client(router, monkeypatch)
    # search_conversations needs query
    out = await intercom.adapter("search_conversations", {}, full_creds)
    assert "query" in out["error"]
    # send_reply needs conversation_id + body
    out = await intercom.adapter("send_reply", {"conversation_id": "1"}, full_creds)
    assert "conversation_id" in out["error"] or "body" in out["error"]
    # assign_to_agent needs conversation_id + agent_id
    out = await intercom.adapter("assign_to_agent", {"conversation_id": "1"}, full_creds)
    assert "agent_id" in out["error"] or "conversation_id" in out["error"]


async def test_unknown_action_returns_error(full_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    _patched_client(router, monkeypatch)
    out = await intercom.adapter("nuke_workspace", {}, full_creds)
    assert "error" in out


async def test_bearer_auth_header_set(full_creds, monkeypatch):
    captured: dict[str, str] = {}

    def router(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization", "")
        captured["version"] = request.headers.get("Intercom-Version", "")
        return httpx.Response(
            200,
            json={
                "id": "1",
                "state": "open",
                "contacts": {"contacts": []},
                "source": {"body": "", "author": {"type": "user"}},
                "conversation_parts": {"conversation_parts": []},
            },
        )

    _patched_client(router, monkeypatch)
    await intercom.adapter("get_conversation", {"id": "1"}, full_creds)
    assert captured["auth"] == "Bearer TOKEN"
    assert captured["version"] == intercom.INTERCOM_API_VERSION
