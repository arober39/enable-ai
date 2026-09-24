"""HubSpot adapter — real CRM REST when `HUBSPOT_API_KEY` is set.

Auth: Bearer token in the `Authorization` header. One credential:

  - `HUBSPOT_API_KEY` — private app token from HubSpot
    (Settings → Integrations → Private Apps).

If the key is missing the adapter degrades to a stub response — same
shape as the previous always-stub adapter — with `mode: "stub"` on the
result. When the key is present the adapter calls HubSpot for real and
returns `mode: "real"`. Workflows that consume the response don't need
to know which path ran; the data shape is identical.

API surface (matches the action names already in `ACTION_CATALOG`):

  - lookup_contact       GET /crm/v3/objects/contacts/{email}?idProperty=email
  - get_account_details  GET /crm/v3/objects/companies/{account_id}
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from core.credentials import Credentials

logger = logging.getLogger(__name__)

TOKEN_CRED = "HUBSPOT_API_KEY"

_BASE_URL = "https://api.hubapi.com"
_TIMEOUT_SECONDS = 15.0


# ---------------------------------------------------------------------------
# Test seam — tests monkey-patch this to inject a MockTransport.
# ---------------------------------------------------------------------------


def _make_client(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=_BASE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        timeout=_TIMEOUT_SECONDS,
    )


# ---------------------------------------------------------------------------
# Stub responses — used when creds are missing. Shape matches real responses.
# ---------------------------------------------------------------------------


def _stub_response(action: str, params: dict[str, Any], reason: str) -> dict[str, Any]:
    base = {
        "tool": "hubspot",
        "action": action,
        "mode": "stub",
        "reason": reason,
        "params": params,
    }
    if action == "lookup_contact":
        return {
            **base,
            "contact": {
                "id": "ct_stub_1",
                "email": params.get("email"),
                "plan_tier": "essentials",
            },
        }
    if action == "get_account_details":
        return {
            **base,
            "account": {"id": params.get("account_id"), "tier": "pro", "mrr": 499},
        }
    return {**base, "error": f"unknown hubspot action: {action}"}


# ---------------------------------------------------------------------------
# Real HubSpot CRM calls
# ---------------------------------------------------------------------------


async def _lookup_contact(
    client: httpx.AsyncClient, params: dict[str, Any]
) -> dict[str, Any]:
    email = str(params.get("email") or "").strip()
    if not email:
        return {"mode": "real", "error": "missing required param: email"}
    resp = await client.get(
        f"/crm/v3/objects/contacts/{quote(email, safe='')}",
        params={
            "idProperty": "email",
            "properties": "email,firstname,lastname,hs_object_id",
        },
    )
    resp.raise_for_status()
    data = resp.json() or {}
    props = data.get("properties") or {}
    return {
        "mode": "real",
        "contact": {
            "id": str(data.get("id") or ""),
            "email": props.get("email") or email,
            "firstname": props.get("firstname") or "",
            "lastname": props.get("lastname") or "",
            "plan_tier": props.get("hs_lead_status") or props.get("plan") or "",
        },
    }


async def _get_account_details(
    client: httpx.AsyncClient, params: dict[str, Any]
) -> dict[str, Any]:
    account_id = str(params.get("account_id") or "").strip()
    if not account_id:
        return {"mode": "real", "error": "missing required param: account_id"}
    resp = await client.get(
        f"/crm/v3/objects/companies/{quote(account_id, safe='')}",
        params={"properties": "name,annualrevenue,type,industry"},
    )
    resp.raise_for_status()
    data = resp.json() or {}
    props = data.get("properties") or {}
    raw_rev = props.get("annualrevenue")
    mrr: int | str | None = None
    if raw_rev not in (None, ""):
        try:
            mrr = int(float(str(raw_rev)))
        except (TypeError, ValueError):
            mrr = str(raw_rev)
    return {
        "mode": "real",
        "account": {
            "id": str(data.get("id") or account_id),
            "name": props.get("name") or "",
            "tier": props.get("type") or props.get("industry") or "",
            "mrr": mrr,
        },
    }


# ---------------------------------------------------------------------------
# Public adapter
# ---------------------------------------------------------------------------


async def adapter(
    action: str, params: dict[str, Any], creds: Credentials
) -> dict[str, Any]:
    """Dispatch a HubSpot action to real REST calls; fall back to stub on missing creds."""
    token = creds.get(TOKEN_CRED)
    if not token:
        return _stub_response(action, params, reason=f"missing credential: {TOKEN_CRED}")

    try:
        async with _make_client(token) as client:
            if action == "lookup_contact":
                return await _lookup_contact(client, params)
            if action == "get_account_details":
                return await _get_account_details(client, params)
            return {"mode": "real", "error": f"unknown hubspot action: {action}"}
    except httpx.HTTPStatusError as exc:
        logger.warning("hubspot %s failed: %s", action, exc)
        return {
            "mode": "real",
            "error": (
                f"HubSpot {action} returned {exc.response.status_code}: "
                f"{exc.response.text[:200]}"
            ),
        }
    except httpx.HTTPError as exc:
        logger.warning("hubspot %s transport error: %s", action, exc)
        return {"mode": "real", "error": f"transport error: {type(exc).__name__}: {exc}"}
