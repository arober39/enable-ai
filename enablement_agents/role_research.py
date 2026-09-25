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
from collections.abc import Sequence
from typing import Any, cast

from anthropic import AsyncAnthropic
from anthropic.types import Message, MessageParam, ToolUseBlock
from pydantic import ValidationError

from core.credentials import runtime_credentials
from core.identity import UserContext
from core.role_catalog import (
    RoleCard,
    cache_role,
    list_available_roles,
    normalize_role_id,
    role_from_card,
)
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

_VALIDATION_SUMMARY_LIMIT = 400


def _validation_summary(exc: ValidationError) -> str:
    """Short field errors for the UI. Omits raw input values and type tags."""
    parts: list[str] = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err["loc"]) or "payload"
        parts.append(f"{location}: {err['msg']}")
    summary = "; ".join(parts) if parts else "invalid role card"
    if len(summary) > _VALIDATION_SUMMARY_LIMIT:
        return summary[: _VALIDATION_SUMMARY_LIMIT - 3] + "..."
    return summary


def _field_names(exc: ValidationError) -> list[str]:
    names: list[str] = []
    for err in exc.errors():
        if not err["loc"]:
            continue
        name = str(err["loc"][0])
        if name not in names:
            names.append(name)
    return names


def _retry_instruction(exc: ValidationError) -> str:
    fields = _field_names(exc)
    named = ", ".join(fields) if fields else "the invalid fields"
    return (
        "The previous submit_role_card call failed validation "
        f"({_validation_summary(exc)}). Call submit_role_card exactly once more. "
        f"Fix these fields: {named}. "
        "capabilities must be a JSON array of at least three short strings, "
        "not a string and not XML. "
        "domain_knowledge must be a non-empty markdown string."
    )


def _has_thinking(content: Sequence[object]) -> bool:
    for block in content:
        if getattr(block, "type", None) in {"thinking", "redacted_thinking"}:
            return True
    return False


def _retry_messages(
    user_message: str,
    response_content: Sequence[object],
    tool_use_id: str | None,
    instruction: str,
) -> list[MessageParam]:
    """One follow-up. Echo the assistant turn only when thinking blocks exist.

    A continuation that drops thinking blocks is rejected by the API. When
    those blocks are present, the assistant tool_use is echoed and the
    follow-up is a tool_result that names the missing fields. Otherwise this
    is a fresh re-ask so the retry does not depend on replaying tool_use.
    `Any` is the Anthropic message content union (text, blocks, or a tool_result).
    """
    if _has_thinking(response_content) and tool_use_id:
        # Echoed blocks plus a tool_result. The SDK message union is wider
        # than this dict, so the cast stays at the boundary.
        return cast(
            list[MessageParam],
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": list(response_content)},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "is_error": True,
                            "content": instruction,
                        }
                    ],
                },
            ],
        )
    return cast(
        list[MessageParam],
        [{"role": "user", "content": f"{user_message}\n\n{instruction}"}],
    )


def _display_key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _reject_prefix_query(name: str, user: UserContext, role_id: str) -> None:
    """Refuse a typed fragment of an existing title unless that role id is named.

    "deve" would otherwise become a new role next to Developer Relations.
    Research on the card passes the existing id and is allowed through.
    """
    known = list_available_roles(user)
    if any(role.id == role_id for role in known):
        return
    query = _display_key(name)
    if len(query) < 2:
        return
    matches = []
    for role in known:
        display = _display_key(role.display_name)
        if display.startswith(query) and display != query:
            matches.append(role)
    if not matches:
        return
    listed = ", ".join(f"{role.display_name} ({role.id})" for role in matches)
    raise ValueError(
        f"{name!r} matches the start of an existing role: {listed}. "
        "Pick that role and use Research on its card, or type the full title."
    )


def _card_from_tool_args(role_id: str, args: dict[str, Any]) -> RoleCard:
    # The server owns identity. The model sometimes echoes the typed title.
    payload = dict(args)
    payload["id"] = role_id
    payload["department"] = role_id
    payload["source"] = "researched"
    return RoleCard.model_validate(payload)


def _tool_args(
    name: str,
    content: Sequence[object],
    stop_reason: str | None,
) -> tuple[dict[str, Any], str | None]:
    tool_uses = [block for block in content if isinstance(block, ToolUseBlock)]
    if not tool_uses:
        raise RuntimeError(
            f"Role researcher: model returned no tool_use for {name!r}. "
            f"stop_reason={stop_reason}."
        )
    args = tool_uses[0].input
    if not isinstance(args, dict):
        raise RuntimeError(
            f"Role researcher: tool_use args were not a dict for {name!r}."
        )
    return args, tool_uses[0].id


def _card_from_response(
    name: str,
    role_id: str,
    content: Sequence[object],
    stop_reason: str | None,
) -> tuple[RoleCard | None, str | None, ValidationError | None]:
    """Return a card, or the validation error plus the tool_use id for a retry."""
    args, tool_use_id = _tool_args(name, content, stop_reason)
    try:
        return _card_from_tool_args(role_id, args), tool_use_id, None
    except ValidationError as exc:
        return None, tool_use_id, exc


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
        role_id: Existing role id when research is started from that card.
            A typed prefix of another role's title is rejected unless this
            id already exists.

    Returns:
        A `Role` with `source="researched"`, `department` equal to the
        role id, inline `domain_knowledge`, and no directory.

    Raises:
        RuntimeError: missing API key, model didn't call the tool, or
            validation fails after one retry. Never fabricates a card.
        ValueError: if `name` cannot be normalized to a role id, or the
            typed name is only a prefix of an existing role.
    """
    derived = normalize_role_id(name)
    role_id = normalize_role_id(role_id) if role_id else derived
    _reject_prefix_query(name, user, role_id)

    creds = runtime_credentials()
    if not creds.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Role research requires it. "
            "Add it via the Settings page in the UI."
        )

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

    async def _complete(messages: list[MessageParam]) -> Message:
        return await client.messages.create(
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
            messages=messages,
        )

    response = await _complete(
        cast(list[MessageParam], [{"role": "user", "content": user_message}])
    )
    card, tool_use_id, error = _card_from_response(
        name, role_id, response.content, response.stop_reason
    )
    if error is not None:
        logger.warning(
            "role research: validation failed for %s (%s); retrying once",
            name,
            ", ".join(_field_names(error)) or "payload",
        )
        response = await _complete(
            _retry_messages(
                user_message,
                response.content,
                tool_use_id,
                _retry_instruction(error),
            )
        )
        card, _tool_use_id, error = _card_from_response(
            name, role_id, response.content, response.stop_reason
        )
        if error is not None or card is None:
            raise RuntimeError(
                f"Role researcher: validation failed for {name!r}: "
                f"{_validation_summary(error) if error is not None else 'invalid role card'}"
            ) from error
    if card is None:
        raise RuntimeError(f"Role researcher: validation failed for {name!r}: invalid role card")

    if cache:
        cache_role(user, card)
    return role_from_card(card)
