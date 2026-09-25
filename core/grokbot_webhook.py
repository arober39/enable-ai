"""POST a finished Grok Bot handoff to an optional webhook.

Copy-paste stays the handoff. When ``GROKBOT_HANDOFF_WEBHOOK_URL`` and
``GROKBOT_HANDOFF_WEBHOOK_KEY`` are both set in the process environment or
the repo ``.env`` (via :class:`core.grokbot.HandoffCredentials`), Enable AI
also POSTs the assignment so Grok Bot can wake up. Missing settings skip
the POST. A failed POST does not fail the handoff.

The sender key is sent as ``Authorization: Bearer <key>``. Redirects are
not followed, so the key is not forwarded to another host.
"""

from __future__ import annotations

import logging
import os
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from core.credentials import Credentials
from core.grokbot import WEBHOOK_KEY_ENV, WEBHOOK_URL_ENV, PlacementAction

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT_SECONDS = 8.0
WEBHOOK_SENT = "Sent to Grok Bot webhook"
WEBHOOK_FAILED = "Webhook failed; copy-paste still works"

WebhookDeliveryStatus = Literal["skipped", "sent", "failed"]


class GrokbotWebhookPayload(BaseModel):
    """JSON body posted to the Grok Bot handoff webhook."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["enable-ai"] = "enable-ai"
    bot_name: str
    name: str
    title: str
    description: str = Field(description="Full copyable assignment text.")
    placement: str
    action: PlacementAction
    recommendation_id: str
    role_name: str
    role_id: str | None = None
    tools: list[str] = Field(default_factory=list)
    existing_bot_name: str | None = None


class HandoffWebhookResult(BaseModel):
    """Outcome of an optional webhook delivery. Never fatal to the handoff."""

    model_config = ConfigDict(extra="forbid")

    status: WebhookDeliveryStatus
    message: str | None = None


def build_webhook_payload(
    *,
    name: str,
    title: str,
    description: str,
    placement: str,
    action: PlacementAction,
    recommendation_id: str,
    role_name: str,
    role_id: str | None,
    tools: list[str],
    existing_bot_name: str | None,
) -> GrokbotWebhookPayload:
    """Shape the handoff into the webhook JSON body."""
    role = (role_id or "").strip() or None
    existing = (existing_bot_name or "").strip() or None
    return GrokbotWebhookPayload(
        bot_name=name,
        name=name,
        title=title,
        description=description,
        placement=placement,
        action=action,
        recommendation_id=recommendation_id,
        role_name=role_name,
        role_id=role,
        tools=list(tools),
        existing_bot_name=existing,
    )


def deliver_handoff_webhook(
    creds: Credentials | None,
    *,
    name: str,
    title: str,
    description: str,
    placement: str,
    action: PlacementAction,
    recommendation_id: str,
    role_name: str,
    role_id: str | None,
    tools: list[str],
    existing_bot_name: str | None,
) -> HandoffWebhookResult:
    """POST the handoff when both webhook settings are set.

    Returns ``skipped`` with no message when either setting is missing.
    Network, timeout, and HTTP errors become ``failed`` and do not raise.
    """
    configured = _configured(creds)
    if configured is None:
        logger.debug("grokbot handoff webhook skipped; credentials unset")
        return HandoffWebhookResult(status="skipped")
    try:
        return _post(
            configured[0],
            configured[1],
            build_webhook_payload(
                name=name,
                title=title,
                description=description,
                placement=placement,
                action=action,
                recommendation_id=recommendation_id,
                role_name=role_name,
                role_id=role_id,
                tools=tools,
                existing_bot_name=existing_bot_name,
            ),
        )
    except Exception as exc:  # noqa: BLE001 — webhook delivery is not fatal
        logger.warning("grokbot handoff webhook failed error=%s", type(exc).__name__)
        return HandoffWebhookResult(status="failed", message=WEBHOOK_FAILED)


def _configured(creds: Credentials | None) -> tuple[str, str] | None:
    url = _value(creds, WEBHOOK_URL_ENV)
    key = _value(creds, WEBHOOK_KEY_ENV)
    if url is None or key is None:
        return None
    return url, key


def _value(creds: Credentials | None, key: str) -> str | None:
    if creds is not None:
        raw = creds.get(key)
    else:
        raw = os.environ.get(key)
        if not raw:
            from core.grokbot import _file_env

            raw = _file_env().get(key)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text or None


def _post(url: str, key: str, payload: GrokbotWebhookPayload) -> HandoffWebhookResult:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        logger.warning("grokbot handoff webhook URL is not http(s)")
        return HandoffWebhookResult(status="failed", message=WEBHOOK_FAILED)
    host = parsed.hostname or "unknown"
    body = payload.model_dump(mode="json")
    try:
        with _client() as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=body,
                follow_redirects=False,
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning(
            "grokbot handoff webhook failed host=%s error=%s",
            host,
            type(exc).__name__,
        )
        return HandoffWebhookResult(status="failed", message=WEBHOOK_FAILED)
    logger.info(
        "grokbot handoff webhook sent host=%s recommendation=%s",
        host,
        payload.recommendation_id,
    )
    return HandoffWebhookResult(status="sent", message=WEBHOOK_SENT)


def _client() -> httpx.Client:
    return httpx.Client(timeout=WEBHOOK_TIMEOUT_SECONDS)
