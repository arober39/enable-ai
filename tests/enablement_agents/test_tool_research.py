"""Tool research normalization. Anthropic is mocked. No live network."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from anthropic.types import ToolUseBlock

from core.identity import UserContext
from core.tool_catalog import load_tool
from enablement_agents.tool_research import research_tool

_FEATURES = [
    {
        "name": "Insights",
        "description": "Natural-language analysis of product usage.",
        "maturity": "ga",
        "coverage": "high",
    }
]

# The Mixpanel failure: native_ai_features arrived as a string whose tail
# included markup around fallback_if_unavailable.
_MESSY_FEATURES = (
    '[\n {\n "name": "Insights",\n "description": '
    '"Natural-language analysis of product usage.",\n '
    '"maturity": "ga",\n "coverage": "high"\n }\n]'
    '</parameter name="fallback_if_unavailable">direct_api'
)


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def _state_path(user: UserContext, *parts: str) -> Path:
        return tmp_path.joinpath(user.user_id, *parts)

    monkeypatch.setattr("core.tool_catalog.state_path", _state_path)
    return tmp_path


def _user() -> UserContext:
    return UserContext(user_id="alice")


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "canonical_name": "Mixpanel",
        "vendor": "Mixpanel",
        "categories": ["product_analytics"],
        "native_ai_features": _MESSY_FEATURES,
        "api_surface": {
            "has_rest_api": True,
            "has_webhooks": True,
            "rate_limits": "standard",
        },
        "integration_patterns": json.dumps(
            ["use_native_ai", "augment_with_custom_ai"]
        ),
        "notes": "In-product assistants over product analytics.",
        "mcp_server": {"available": False, "tools_exposed": []},
        "fallback_if_unavailable": "direct_api",
    }
    payload.update(overrides)
    return payload


def _block(**overrides: object) -> ToolUseBlock:
    return ToolUseBlock(
        id="toolu_test",
        name="submit_tool_capability",
        input=_payload(**overrides),
        type="tool_use",
    )


class _Messages:
    def __init__(self, content: list[object]) -> None:
        self._content = content

    async def create(self, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(content=self._content, stop_reason="tool_use")


class _Client:
    def __init__(self, content: list[object]) -> None:
        self.messages = _Messages(content)


def _install_client(
    monkeypatch: pytest.MonkeyPatch, content: list[object]
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        "enablement_agents.tool_research.AsyncAnthropic",
        lambda: _Client(content),
    )


async def test_research_accepts_stringified_native_ai_features(
    isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_client(monkeypatch, [_block()])

    capability = await research_tool("mixpanel", _user())

    assert capability.canonical_name == "mixpanel"
    assert capability.source == "researched"
    assert len(capability.native_ai_features) == 1
    assert capability.native_ai_features[0].name == "Insights"
    assert capability.native_ai_features[0].coverage == "high"
    assert capability.integration_patterns == [
        "use_native_ai",
        "augment_with_custom_ai",
    ]

    cached = json.loads(
        (isolated_state / "alice" / "tool_cache" / "mixpanel.json").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(cached["native_ai_features"], list)
    assert cached["native_ai_features"][0]["name"] == "Insights"
    loaded = load_tool(_user(), "mixpanel")
    assert loaded is not None
    assert loaded.native_ai_features[0].description == (
        "Natural-language analysis of product usage."
    )


async def test_research_error_omits_raw_pydantic_dump(
    isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_client(
        monkeypatch,
        [_block(vendor="", native_ai_features=_MESSY_FEATURES)],
    )

    with pytest.raises(RuntimeError, match="validation failed") as exc_info:
        await research_tool("mixpanel", _user())

    message = str(exc_info.value)
    assert "input_value" not in message
    assert "list_type" not in message
    assert "native_ai_features" not in message
    assert "vendor" in message
