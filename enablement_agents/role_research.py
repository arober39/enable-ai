"""LLM-driven role researcher.

Given a free-form job title from the UI, hits Claude with a forced
`submit_role_card` tool_use that conforms to `RoleCard`. The validated
card is cached via `core.role_catalog.cache_role` so the next lookup is
free.

Architectural note: this module talks to Anthropic directly (same
pattern as `enablement_agents.tool_research`). A missing API key is an
error — this module does not invent a capability card.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import ToolUseBlock

from core.credentials import runtime_credentials
from core.identity import UserContext
from core.role_catalog import RoleCard, cache_role, normalize_role_id, role_from_card
from core.roles import Role

logger = logging.getLogger(__name__)

_RESEARCH_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 4096
_SUBMIT_TOOL = "submit_role_card"


def _schema_for_submit() -> dict[str, Any]:
    """RoleCard JSON schema minus fields the server assigns."""
    schema = RoleCard.model_json_schema()
    props = schema.get("properties") or {}
    for key in ("id", "department", "source"):
        props.pop(key, None)
    required = schema.get("required") or []
    schema["required"] = [
        name for name in required if name not in {"id", "department", "source"}
    ]
    return schema


_SYSTEM_PROMPT = """\
You are a Role Capability Researcher for Enable AI.

Given a job title, produce a structured role card describing what
AI-enabled work looks like in that job:

- display_name — the human-readable job title
- description — one short paragraph of what the job is responsible for
- capabilities — at least three short phrases (a few words each) for
  work AI can take on in this job. Not essays.
- domain_knowledge — markdown the enablement agent will treat as its
  reference. Cover what AI-enabled work looks like for this job and the
  failure modes specific to it (bad data, wrong audience, automation
  that hides a human decision, and so on). Be concrete. Do not invent
  vendor product names as if they were required.

Be honest about uncertainty. If the title is ambiguous, pick the most
common reading and say so in domain_knowledge.

Call `submit_role_card` exactly once with the result. Do not include
id, department, or source — the server assigns those.
"""


async def research_role(
    name: str,
    user: UserContext,
    *,
    cache: bool = True,
    role_id: str | None = None,
) -> Role:
    """Research a job role with Claude, validate, and cache the card.

    Args:
        name: Free-form job title typed by the user. Normalized to a
            canonical role id before research.
        user: Identity context — used for cache-write only.
        cache: If True, persist the validated card to the user's role
            cache. Set False for one-off previews.

    Returns:
        A `Role` with `source="researched"`, `department` equal to the
        role id, inline `domain_knowledge`, and no directory.

    Raises:
        RuntimeError: missing API key, model didn't call the tool, or
            validation fails. Never fabricates a card.
        ValueError: if `name` cannot be normalized to a role id.
    """
    creds = runtime_credentials()
    if not creds.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Role research requires it. "
            "Add it via the Settings page in the UI."
        )

    derived = normalize_role_id(name)
    role_id = normalize_role_id(role_id) if role_id else derived
    schema = _schema_for_submit()

    user_message = (
        f"Research the job role: {name!r} (role id: {role_id!r}).\n\n"
        "Produce a role card. display_name should be the human-readable "
        "job title. capabilities must be at least three short phrases. "
        "domain_knowledge is markdown describing what AI-enabled work "
        "looks like for this job, including failure modes."
    )

    # Anthropic SDK reads ANTHROPIC_API_KEY from env. The caller is
    # responsible for populating it before this runs.
    client = AsyncAnthropic()
    model = os.environ.get("UI_RESEARCH_MODEL", _RESEARCH_MODEL)
    logger.info("role research: model=%s name=%s id=%s", model, name, role_id)

    response = await client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        tools=[
            {
                "name": _SUBMIT_TOOL,
                "description": (
                    "Submit the structured role capability card. Call "
                    "exactly once when your research is complete."
                ),
                "input_schema": schema,
            }
        ],
        tool_choice={"type": "tool", "name": _SUBMIT_TOOL},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_uses = [block for block in response.content if isinstance(block, ToolUseBlock)]
    if not tool_uses:
        raise RuntimeError(
            f"Role researcher: model returned no tool_use for {name!r}. "
            f"stop_reason={response.stop_reason}."
        )

    args = tool_uses[0].input
    if not isinstance(args, dict):
        raise RuntimeError(
            f"Role researcher: tool_use args were not a dict for {name!r}."
        )

    # The server owns identity. The model sometimes echoes the typed title.
    args["id"] = role_id
    args["department"] = role_id
    args["source"] = "researched"

    try:
        card = RoleCard.model_validate(args)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Role researcher: validation failed for {name!r}: {exc}"
        ) from exc

    if cache:
        cache_role(user, card)
    return role_from_card(card)
