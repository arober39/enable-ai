"""Role research tests. Anthropic is mocked. No live network."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from anthropic.types import ToolUseBlock

from core.identity import UserContext
from core.role_catalog import RoleCard, load_role_for_user
from enablement_agents.role_research import research_role

# The Developer Relations failure: capabilities arrived as a string whose
# body is a JSON list wrapped in a parameter tag. Pydantic truncated it to
# '\n<parameter name="conte...m product updates"\n]\n'.
_MESSY_CAPABILITIES = (
    '\n<parameter name="content">'
    '["tutorial and blog drafting", "code sample generation", '
    '"community sentiment analysis", "documentation gap identification", '
    '"open-source issue and PR triage", "developer survey synthesis", '
    '"conference talk recommendation", "summarize product updates"\n]\n'
)


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def _state_path(user: UserContext, *parts: str) -> Path:
        return tmp_path.joinpath(user.user_id, *parts)

    monkeypatch.setattr("core.role_catalog.state_path", _state_path)
    return tmp_path


def _user() -> UserContext:
    return UserContext(user_id="alice")


_DROP = object()


def _block(**overrides: object) -> ToolUseBlock:
    payload: dict[str, object] = {
        "id": "not_the_slug",
        "department": "sales",
        "display_name": "Account Executive",
        "description": "Owns quota, pipeline, and the next conversation.",
        "capabilities": ["call notes", "deal risk", "forecast hygiene"],
        "domain_knowledge": (
            "## AI-enabled work\n\n"
            "Draft follow-ups from call notes.\n\n"
            "## Failure modes\n\n"
            "Invented discounts.\n"
        ),
    }
    payload.update(overrides)
    for key, value in list(payload.items()):
        if value is _DROP:
            del payload[key]
    return ToolUseBlock(
        id="toolu_test",
        name="submit_role_card",
        input=payload,
        type="tool_use",
    )


class _Messages:
    def __init__(self, rounds: list[list[object]]) -> None:
        self._rounds = rounds
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self._rounds) - 1)
        return SimpleNamespace(content=self._rounds[index], stop_reason="tool_use")


class _Client:
    def __init__(self, content: list[object] | list[list[object]]) -> None:
        rounds = content if content and isinstance(content[0], list) else [content]
        self.messages = _Messages(rounds)  # type: ignore[arg-type]


async def test_missing_api_key_does_not_call_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Anthropic client was constructed")

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("enablement_agents.role_research.AsyncAnthropic", _boom)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        await research_role("Account Executive", _user())


async def test_mocked_tool_use_caches_and_load_finds_it(
    isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client([_block()])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("UI_RESEARCH_MODEL", raising=False)
    monkeypatch.setattr(
        "enablement_agents.role_research.AsyncAnthropic",
        lambda: client,
    )

    user = _user()
    role = await research_role("Account Executive", user)

    assert client.messages.calls
    call = client.messages.calls[0]
    assert call["model"] == "claude-haiku-4-5-20251001"
    assert call["tool_choice"] == {"type": "tool", "name": "submit_role_card"}
    assert role.id == "account_executive"
    assert role.department == "account_executive"
    assert role.source == "researched"
    assert role.directory is None
    assert len(role.capabilities) >= 3
    assert "Failure modes" in role.domain_knowledge

    path = isolated_state / "alice" / "role_cache" / "account_executive.json"
    assert path.is_file()
    loaded = load_role_for_user(user, "account_executive")
    assert loaded.display_name == role.display_name
    assert loaded.domain_knowledge == role.domain_knowledge
    assert loaded.capabilities == role.capabilities


def _install(
    monkeypatch: pytest.MonkeyPatch, client: _Client
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        "enablement_agents.role_research.AsyncAnthropic",
        lambda: client,
    )


def _message_text(call: dict[str, object]) -> str:
    messages = call["messages"]
    assert isinstance(messages, list)
    chunks: list[str] = []
    for message in messages:
        assert isinstance(message, dict)
        content = message["content"]
        if isinstance(content, str):
            chunks.append(content)
            continue
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("content"), str):
                    chunks.append(block["content"])
    return "\n".join(chunks)


def test_role_card_accepts_stringified_capabilities() -> None:
    card = RoleCard.model_validate(
        {
            "id": "devrel",
            "display_name": "Developer Relations",
            "department": "devrel",
            "description": "Developer content, samples, and community.",
            "capabilities": _MESSY_CAPABILITIES,
            "domain_knowledge": "Draft tutorials. Do not invent product behavior.",
            "source": "researched",
        }
    )
    assert card.capabilities[0] == "tutorial and blog drafting"
    assert "summarize product updates" in card.capabilities
    assert len(card.capabilities) >= 3


async def test_research_accepts_stringified_capabilities(
    isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(
        [
            _block(
                display_name="Developer Relations",
                description="Developer content, samples, and community.",
                capabilities=_MESSY_CAPABILITIES,
                domain_knowledge="Draft tutorials. Do not invent product behavior.",
            )
        ]
    )
    _install(monkeypatch, client)

    role = await research_role(
        "Developer Relations",
        _user(),
        role_id="devrel",
    )

    assert len(client.messages.calls) == 1
    assert role.id == "devrel"
    assert role.capabilities[0] == "tutorial and blog drafting"
    assert "summarize product updates" in role.capabilities
    cached = json.loads(
        (isolated_state / "alice" / "role_cache" / "devrel.json").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(cached["capabilities"], list)
    assert cached["capabilities"][0] == "tutorial and blog drafting"


async def test_missing_domain_knowledge_retries_once(
    isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = _block(domain_knowledge=_DROP)
    client = _Client([[broken], [_block(display_name="Account Executive")]])
    _install(monkeypatch, client)

    role = await research_role("Account Executive", _user())

    assert len(client.messages.calls) == 2
    follow_up = _message_text(client.messages.calls[1])
    assert "domain_knowledge" in follow_up
    assert role.domain_knowledge
    assert (isolated_state / "alice" / "role_cache" / "account_executive.json").is_file()


async def test_validation_error_omits_raw_pydantic_dump(
    isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = _block(domain_knowledge=_DROP)
    client = _Client([[broken], [broken]])
    _install(monkeypatch, client)

    with pytest.raises(RuntimeError, match="validation failed") as exc_info:
        await research_role("Account Executive", _user())

    message = str(exc_info.value)
    assert "input_value" not in message
    assert "list_type" not in message
    assert "domain_knowledge" in message
    assert len(client.messages.calls) == 2


async def test_thinking_retry_echoes_the_assistant_turn(
    isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thinking = SimpleNamespace(type="thinking", thinking="draft the card")
    first = [thinking, _block(domain_knowledge=_DROP)]
    client = _Client([first, [_block()]])
    _install(monkeypatch, client)

    await research_role("Account Executive", _user())

    messages = client.messages.calls[1]["messages"]
    assert isinstance(messages, list)
    assert [message["role"] for message in messages] == ["user", "assistant", "user"]
    assert messages[1]["content"][0] is thinking
    follow_up = messages[2]["content"]
    assert isinstance(follow_up, list)
    assert follow_up[0]["type"] == "tool_result"
    assert follow_up[0]["is_error"] is True
    assert "domain_knowledge" in follow_up[0]["content"]


async def test_prefix_query_does_not_invent_a_role(
    isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Anthropic client was constructed")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("enablement_agents.role_research.AsyncAnthropic", _boom)

    with pytest.raises(ValueError, match="Developer Relations") as exc_info:
        await research_role("deve", _user())
    message = str(exc_info.value)
    assert "full title" in message
    assert "card" in message

    assert not (isolated_state / "alice" / "role_cache").exists()


async def test_research_on_existing_card_allows_that_id(
    isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(
        [
            _block(
                display_name="Developer Relations",
                description="Developer content, samples, and community.",
                capabilities=[
                    "tutorial drafting",
                    "code samples",
                    "community replies",
                ],
                domain_knowledge="Draft tutorials. Do not invent APIs.",
            )
        ]
    )
    _install(monkeypatch, client)

    role = await research_role("deve", _user(), role_id="devrel")

    assert role.id == "devrel"
    assert (isolated_state / "alice" / "role_cache" / "devrel.json").is_file()
    assert not (isolated_state / "alice" / "role_cache" / "deve.json").exists()
