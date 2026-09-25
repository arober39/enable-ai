"""Tool research normalization. Anthropic is mocked. No live network."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from anthropic.types import ToolUseBlock

from core.identity import UserContext
from core.tool_catalog import ToolCapability, cache_tool, load_tool
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


def _capability(**overrides: object) -> ToolCapability:
    payload: dict[str, object] = {
        "canonical_name": "google_docs",
        "vendor": "Google Docs",
        "categories": ["documents"],
        "native_ai_features": [],
        "api_surface": {
            "has_rest_api": True,
            "has_webhooks": False,
            "rate_limits": "standard",
        },
        "integration_patterns": ["use_native_ai"],
        "notes": "Collaborative documents.",
        "mcp_server": {"available": False, "tools_exposed": []},
        "fallback_if_unavailable": "direct_api",
        "source": "researched",
    }
    payload.update(overrides)
    return ToolCapability.model_validate(payload)


def _forbid_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Anthropic client was constructed")

    monkeypatch.setattr("enablement_agents.tool_research.AsyncAnthropic", _boom)


async def test_docs_reuses_existing_google_docs(
    isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    cache_tool(user, _capability())
    cache_path = isolated_state / "alice" / "tool_cache" / "google_docs.json"
    before = cache_path.read_text(encoding="utf-8")
    _forbid_client(monkeypatch)

    capability = await research_tool("docs", user)

    assert capability.canonical_name == "google_docs"
    assert capability.vendor == "Google Docs"
    assert "docs" in (capability.notes or "")
    assert "duplicate" in (capability.notes or "")
    assert cache_path.read_text(encoding="utf-8") == before
    assert not (isolated_state / "alice" / "tool_cache" / "docs.json").exists()


async def test_gdocs_reuses_vendor_match_when_slug_differs(
    isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    cache_tool(
        user,
        _capability(canonical_name="drive_docs", vendor="Google Docs", notes="Drive"),
    )
    _forbid_client(monkeypatch)

    capability = await research_tool("gdocs", user)

    assert capability.canonical_name == "drive_docs"
    cache_dir = isolated_state / "alice" / "tool_cache"
    assert not (cache_dir / "gdocs.json").exists()
    assert not (cache_dir / "docs.json").exists()
    assert not (cache_dir / "google_docs.json").exists()


async def test_docs_prefers_canonical_google_docs_over_another_vendor_match(
    isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    cache_tool(user, _capability(canonical_name="drive_docs", notes="other"))
    cache_tool(user, _capability())
    _forbid_client(monkeypatch)

    capability = await research_tool("docs", user)

    assert capability.canonical_name == "google_docs"
    assert not (isolated_state / "alice" / "tool_cache" / "docs.json").exists()


async def test_docs_is_researched_when_google_docs_is_absent(
    isolated_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_client(
        monkeypatch,
        [_block(vendor="Product documentation", notes="A documentation site.")],
    )

    capability = await research_tool("docs", _user())

    assert capability.canonical_name == "docs"
    assert capability.vendor == "Product documentation"
    cache_dir = isolated_state / "alice" / "tool_cache"
    assert (cache_dir / "docs.json").is_file()
    assert not (cache_dir / "google_docs.json").exists()
