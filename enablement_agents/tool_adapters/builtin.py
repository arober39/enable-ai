"""Built-in adapters: llm / return / set + stub adapters for seed tools.

The stub adapters return synthetic data shaped like the real APIs would.
They exist so workflows are runnable end-to-end before real MCP wiring
lands. Each stub also logs the action it was asked to perform, so the
UI's response pane visibly says "I would have called X with Y."
"""

from __future__ import annotations

import logging
import os
from typing import Any

from anthropic import AsyncAnthropic

from core.credentials import Credentials

from .registry import ACTION_CATALOG, register

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Special adapters
# ---------------------------------------------------------------------------


#: Allowlist of model IDs the llm adapter accepts. Anything not in this
#: set (including model IDs the workflow generator's LLM might hallucinate
#: from older training data) is logged and downgraded to the default.
_VALID_MODELS = frozenset(
    {
        "claude-opus-4-8",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    }
)
_DEFAULT_LLM_MODEL = "claude-haiku-4-5-20251001"


def _resolve_model(requested: Any) -> str:
    """Coerce a requested model name to a known-valid one, with fallback."""
    if isinstance(requested, str) and requested in _VALID_MODELS:
        return requested
    if requested:
        logger.warning(
            "llm step requested unknown model %r; falling back to %s",
            requested,
            _DEFAULT_LLM_MODEL,
        )
    return _DEFAULT_LLM_MODEL


async def _llm_adapter(
    action: str, params: dict[str, Any], creds: Credentials
) -> dict[str, Any]:
    """Adapter for the `llm` tool — calls Claude.

    Supported actions:
      - complete: { system: str, user: str, model?: str, max_tokens?: int }
                  Returns { text: str, model: str, stop_reason: str }.

    Model ids are validated against `_VALID_MODELS`; unknown ids downgrade
    to the default rather than 404ing.
    """
    if action != "complete":
        return {"error": f"unknown llm action: {action}"}

    api_key = creds.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "stub": True,
            "reason": "ANTHROPIC_API_KEY not set in credential vault",
            "would_have_called": "anthropic.messages.create",
            "params": params,
        }

    model = _resolve_model(params.get("model"))
    max_tokens = int(params.get("max_tokens") or 512)
    system = str(params.get("system") or "")
    user = str(params.get("user") or "")
    # Anthropic SDK reads ANTHROPIC_API_KEY from env; the spawner has
    # already populated it via credentials_in_env in the API layer.
    os.environ.setdefault("ANTHROPIC_API_KEY", api_key)

    client = AsyncAnthropic()
    resp = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system or "You are a helpful assistant.",
        messages=[{"role": "user", "content": user}],
    )
    text = ""
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text = str(getattr(block, "text", "") or "")
            break
    return {
        "text": text,
        "model": resp.model,
        "stop_reason": resp.stop_reason or "",
    }


async def _return_adapter(
    action: str, params: dict[str, Any], creds: Credentials
) -> dict[str, Any]:
    """`return` adapter — emits its params as the workflow's final output.

    The workflow interpreter uses the last `return` step's output as the
    overall workflow result. If no `return` step runs, the interpreter
    returns a summary of all step outputs.
    """
    return dict(params)


async def _set_adapter(
    action: str, params: dict[str, Any], creds: Credentials
) -> dict[str, Any]:
    """`set` adapter — copies values around the context.

    Useful for shape changes: the params (already $ref-resolved by the
    interpreter) become the output verbatim. Step's `output_key` decides
    where the values land in context.
    """
    return dict(params)


# ---------------------------------------------------------------------------
# Stub adapters for seed catalog tools
# ---------------------------------------------------------------------------


# Intercom's adapter is real (REST) when INTERCOM_API_TOKEN is present;
# stub fallback when missing. Write actions (send_reply, assign_to_agent)
# also need INTERCOM_ADMIN_ID. Lives in its own module — see
# `enablement_agents/tool_adapters/intercom.py`.
from .intercom import adapter as _intercom_adapter


# Zendesk's adapter is real (REST) when creds are present; stub otherwise.
# Lives in its own module — see `enablement_agents/tool_adapters/zendesk.py`.
from .zendesk import adapter as _zendesk_adapter


async def _slack_adapter(
    action: str, params: dict[str, Any], creds: Credentials
) -> dict[str, Any]:
    stub = {"tool": "slack", "action": action, "params": params, "stub": True}
    if action == "post_message":
        return {**stub, "ts": "1700000000.0001", "channel": params.get("channel")}
    if action == "list_channels":
        return {**stub, "channels": [{"id": "C123", "name": "general"}]}
    if action == "get_channel_history":
        return {**stub, "messages": [{"ts": "1", "text": "stub"}]}
    return {**stub, "error": f"unknown slack action: {action}"}


async def _hubspot_adapter(
    action: str, params: dict[str, Any], creds: Credentials
) -> dict[str, Any]:
    stub = {"tool": "hubspot", "action": action, "params": params, "stub": True}
    if action == "lookup_contact":
        return {**stub, "contact": {"id": "ct_stub_1", "email": params.get("email"), "plan_tier": "essentials"}}
    if action == "get_account_details":
        return {**stub, "account": {"id": params.get("account_id"), "tier": "pro", "mrr": 499}}
    return {**stub, "error": f"unknown hubspot action: {action}"}


# ---------------------------------------------------------------------------
# Register everything
# ---------------------------------------------------------------------------


def install_builtins() -> None:
    """Register every built-in adapter. Idempotent; safe to call repeatedly."""
    register("llm", _llm_adapter)
    register("return", _return_adapter)
    register("set", _set_adapter)
    register("intercom", _intercom_adapter)
    register("zendesk", _zendesk_adapter)
    register("slack", _slack_adapter)
    register("hubspot", _hubspot_adapter)

    ACTION_CATALOG.update(
        {
            "llm": {
                "complete": (
                    "Call Claude. params: {system: str, user: str, "
                    "model?: str, max_tokens?: int}. Returns {text, model, stop_reason}."
                ),
            },
            "return": {
                "value": (
                    "Emit the params as the workflow's final output. Run "
                    "this as the last step in every workflow."
                ),
            },
            "set": {
                "value": (
                    "Copy / reshape values into the context under "
                    "`output_key`. Useful for transforms between steps."
                ),
            },
            "intercom": {
                "search_conversations": "Search Intercom conversations by body substring. params: {query: str}. Real when INTERCOM_API_TOKEN is set; stub otherwise.",
                "get_conversation": "Fetch one conversation (plaintext). params: {id: str}. Returns {customer, messages: [{role, text}]}.",
                "send_reply": "Reply to a conversation as an admin. params: {conversation_id: str, body: str}. Needs INTERCOM_API_TOKEN + INTERCOM_ADMIN_ID.",
                "assign_to_agent": "Reassign a conversation to another admin. params: {conversation_id: str, agent_id: str, note?: str}. Needs INTERCOM_API_TOKEN + INTERCOM_ADMIN_ID.",
            },
            "zendesk": {
                "search_articles": "Semantic search of help center. params: {query: str}. Real if ZENDESK_{SUBDOMAIN,EMAIL,API_TOKEN} are set; stub otherwise.",
                "get_article": "Fetch one article. params: {id: str}",
                "search_tickets": "Find tickets. params: {query: str}",
                "get_ticket": "Fetch one ticket. params: {id: str}",
                "create_internal_note": "Add internal note. params: {ticket_id: str, body: str}",
            },
            "slack": {
                "post_message": "Post to channel. params: {channel: str, text: str}",
                "list_channels": "List channels. params: {}",
                "get_channel_history": "Read recent channel messages. params: {channel: str, limit?: int}",
            },
            "hubspot": {
                "lookup_contact": "Find a contact. params: {email: str}",
                "get_account_details": "Account info. params: {account_id: str}",
            },
        }
    )


# Auto-install on import so callers don't have to remember.
install_builtins()
