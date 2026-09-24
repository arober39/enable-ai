"""Tests for the HubSpot adapter.

All HTTP calls are intercepted via httpx.MockTransport — no network
calls leave the test process. Missing `HUBSPOT_API_KEY` degrades to stub.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from enablement_agents.tool_adapters import hubspot


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
    return _FakeCreds({"HUBSPOT_API_KEY": "pat-test-key"})


def _patched_client(router, monkeypatch):
    transport = httpx.MockTransport(router)

    def factory(token: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="https://api.hubapi.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            transport=transport,
            timeout=15.0,
        )

    monkeypatch.setattr(hubspot, "_make_client", factory)


# ---------------------------------------------------------------------------
# Stub-fallback path
# ---------------------------------------------------------------------------


async def test_missing_key_returns_stub():
    out = await hubspot.adapter(
        "lookup_contact", {"email": "a@b.com"}, _FakeCreds({})
    )
    assert out["mode"] == "stub"
    assert "HUBSPOT_API_KEY" in out["reason"]
    assert out["contact"]["email"] == "a@b.com"
    assert out["contact"]["id"] == "ct_stub_1"


async def test_stub_shape_matches_real_shape_for_each_action():
    actions_and_keys = [
        ("lookup_contact", {"email": "a@b.com"}, "contact"),
        ("get_account_details", {"account_id": "99"}, "account"),
    ]
    creds = _FakeCreds({})
    for action, params, top_key in actions_and_keys:
        out = await hubspot.adapter(action, params, creds)
        assert out["mode"] == "stub"
        assert top_key in out, f"missing key {top_key!r} for action {action!r}"


# ---------------------------------------------------------------------------
# Real-call paths
# ---------------------------------------------------------------------------


async def test_lookup_contact_get_by_email(real_creds, monkeypatch):
    captured: dict[str, Any] = {}

    def router(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/crm/v3/objects/contacts/" in request.url.path
        assert request.url.params.get("idProperty") == "email"
        captured["auth"] = request.headers.get("Authorization", "")
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "id": "51",
                "properties": {
                    "email": "a@b.com",
                    "firstname": "Ada",
                    "lastname": "Lovelace",
                    "hs_lead_status": "OPEN",
                },
            },
        )

    _patched_client(router, monkeypatch)
    out = await hubspot.adapter(
        "lookup_contact", {"email": "a@b.com"}, real_creds
    )
    assert out["mode"] == "real"
    assert out["contact"]["id"] == "51"
    assert out["contact"]["email"] == "a@b.com"
    assert out["contact"]["firstname"] == "Ada"
    assert captured["auth"] == "Bearer pat-test-key"
    assert "a%40b.com" in captured["path"] or "a@b.com" in captured["path"]


async def test_get_account_details_real(real_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path.endswith("/crm/v3/objects/companies/99")
        return httpx.Response(
            200,
            json={
                "id": "99",
                "properties": {
                    "name": "Serenia & Co.",
                    "annualrevenue": "12000",
                    "type": "CUSTOMER",
                },
            },
        )

    _patched_client(router, monkeypatch)
    out = await hubspot.adapter(
        "get_account_details", {"account_id": "99"}, real_creds
    )
    assert out["mode"] == "real"
    assert out["account"]["id"] == "99"
    assert out["account"]["name"] == "Serenia & Co."
    assert out["account"]["tier"] == "CUSTOMER"
    assert out["account"]["mrr"] == 12000


async def test_http_error_returns_structured_error(real_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid token")

    _patched_client(router, monkeypatch)
    out = await hubspot.adapter(
        "lookup_contact", {"email": "a@b.com"}, real_creds
    )
    assert out["mode"] == "real"
    assert "401" in out["error"]


async def test_missing_param_short_circuits(real_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        pytest.fail("should not call HubSpot when required params missing")
        return httpx.Response(500)

    _patched_client(router, monkeypatch)
    out = await hubspot.adapter("lookup_contact", {}, real_creds)
    assert "email" in out["error"]
    out = await hubspot.adapter("get_account_details", {}, real_creds)
    assert "account_id" in out["error"]


async def test_unknown_action_returns_error(real_creds, monkeypatch):
    def router(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    _patched_client(router, monkeypatch)
    out = await hubspot.adapter("delete_portal", {}, real_creds)
    assert out["mode"] == "real"
    assert "error" in out
