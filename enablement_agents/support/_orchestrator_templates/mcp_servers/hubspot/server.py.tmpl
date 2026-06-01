"""Minimal HubSpot MCP server stub.

Wraps a small set of HubSpot REST endpoints into MCP tools the support
orchestrator can call. In demo mode (no HUBSPOT_API_KEY) the tools return
synthetic data with the same shape as the real responses, so the
orchestrator runs end-to-end without HubSpot credentials.

Tools exposed:
  - get_contact_by_email(email: str)
  - get_subscription_status(contact_id: str)
  - get_recent_tickets(contact_id: str, limit: int = 10)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from claude_agent_sdk import McpServerConfig, create_sdk_mcp_server, tool

logger = logging.getLogger(__name__)

_HUBSPOT_BASE = "https://api.hubapi.com"


def _demo_mode() -> bool:
    return os.environ.get("ENABLE_AI_DEMO_MODE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _structured_error(category: str, message: str) -> dict[str, Any]:
    return {
        "isError": True,
        "errorCategory": category,
        "isRetryable": False,
        "message": message,
    }


async def _hubspot_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wrapper around HubSpot's REST API. Demo mode returns synthetic data."""
    if _demo_mode() or not os.environ.get("HUBSPOT_API_KEY"):
        return {
            "_stub": True,
            "_note": (
                "Demo mode — synthetic response. Set HUBSPOT_API_KEY and "
                "ENABLE_AI_DEMO_MODE=false for real calls."
            ),
            "path": path,
            "params": params or {},
        }
    headers = {
        "Authorization": f"Bearer {os.environ['HUBSPOT_API_KEY']}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(_HUBSPOT_BASE + path, headers=headers, params=params)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data


@tool(
    "get_contact_by_email",
    (
        "Look up a HubSpot contact by email. Returns the contact's id, plan tier, "
        "and basic profile fields. Demo mode returns synthetic data with the "
        "same shape as the real HubSpot response."
    ),
    {
        "type": "object",
        "properties": {
            "email": {"type": "string", "description": "Customer email address."}
        },
        "required": ["email"],
        "additionalProperties": False,
    },
)
async def get_contact_by_email(args: dict[str, Any]) -> dict[str, Any]:
    email = args.get("email")
    if not isinstance(email, str) or not email.strip():
        err = _structured_error("validation", "email is required.")
        return {
            "content": [{"type": "text", "text": json.dumps(err, indent=2)}],
            "is_error": True,
        }
    data = await _hubspot_get(
        "/crm/v3/objects/contacts/search",
        params={"properties": "email,plan,subscription_status", "email": email},
    )
    return {"content": [{"type": "text", "text": json.dumps(data, indent=2)}]}


@tool(
    "get_subscription_status",
    "Return the subscription status for a HubSpot contact id.",
    {
        "type": "object",
        "properties": {
            "contact_id": {"type": "string", "description": "HubSpot contact id."}
        },
        "required": ["contact_id"],
        "additionalProperties": False,
    },
)
async def get_subscription_status(args: dict[str, Any]) -> dict[str, Any]:
    contact_id = args.get("contact_id")
    if not isinstance(contact_id, str) or not contact_id.strip():
        err = _structured_error("validation", "contact_id is required.")
        return {
            "content": [{"type": "text", "text": json.dumps(err, indent=2)}],
            "is_error": True,
        }
    data = await _hubspot_get(
        f"/crm/v3/objects/contacts/{contact_id}",
        params={"properties": "subscription_status,plan"},
    )
    return {"content": [{"type": "text", "text": json.dumps(data, indent=2)}]}


@tool(
    "get_recent_tickets",
    "Return recent support tickets for a HubSpot contact id.",
    {
        "type": "object",
        "properties": {
            "contact_id": {"type": "string", "description": "HubSpot contact id."},
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "description": "Max number of tickets to return. Defaults to 10.",
            },
        },
        "required": ["contact_id"],
        "additionalProperties": False,
    },
)
async def get_recent_tickets(args: dict[str, Any]) -> dict[str, Any]:
    contact_id = args.get("contact_id")
    limit = int(args.get("limit", 10) or 10)
    if not isinstance(contact_id, str) or not contact_id.strip():
        err = _structured_error("validation", "contact_id is required.")
        return {
            "content": [{"type": "text", "text": json.dumps(err, indent=2)}],
            "is_error": True,
        }
    data = await _hubspot_get(
        f"/crm/v3/objects/contacts/{contact_id}/associations/tickets",
        params={"limit": limit},
    )
    return {"content": [{"type": "text", "text": json.dumps(data, indent=2)}]}


def build_hubspot_mcp_server() -> McpServerConfig:
    """Factory: in-process MCP server hosting the three HubSpot tools."""
    return create_sdk_mcp_server(
        name="hubspot",
        version="0.1.0",
        tools=[get_contact_by_email, get_subscription_status, get_recent_tickets],
    )
