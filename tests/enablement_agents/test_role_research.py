"""Role research tests. Anthropic is mocked. No live network."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from anthropic.types import ToolUseBlock

from core.identity import UserContext
from core.role_catalog import load_role_for_user
from enablement_agents.role_research import research_role


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def _state_path(user: UserContext, *parts: str) -> Path:
        return tmp_path.joinpath(user.user_id, *parts)

    monkeypatch.setattr("core.role_catalog.state_path", _state_path)
    return tmp_path


def _user() -> UserContext:
    return UserContext(user_id="alice")


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
    return ToolUseBlock(
        id="toolu_test",
        name="submit_role_card",
        input=payload,
        type="tool_use",
    )


class _Messages:
    def __init__(self, content: list[object]) -> None:
        self._content = content
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(content=self._content, stop_reason="tool_use")


class _Client:
    def __init__(self, content: list[object]) -> None:
        self.messages = _Messages(content)


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
