"""Deterministic tests for the per-user researched role cache.

Writes only under tmp_path. No network, no LLM. Seeded roles on disk
stay on disk when an id collides. The user's researched card wins.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.identity import UserContext
from core.role_catalog import (
    RoleCard,
    cache_role,
    delete_cached_role,
    list_available_roles,
    load_role_for_user,
    normalize_role_id,
    role_from_card,
)
from core.roles import list_roles, load_role
from core.state import repo_root
from ui.api.live_runner import _build_system_prompt


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Route role cache files under tmp_path instead of repo agent-state/."""

    def _state_path(user: UserContext, *parts: str) -> Path:
        return tmp_path.joinpath(user.user_id, *parts)

    monkeypatch.setattr("core.role_catalog.state_path", _state_path)
    return tmp_path


def _user(user_id: str = "alice") -> UserContext:
    return UserContext(user_id=user_id)


def _card(**overrides: object) -> RoleCard:
    payload: dict[str, object] = {
        "id": "account_executive",
        "display_name": "Account Executive",
        "department": "account_executive",
        "description": "Owns quota, pipeline, and the next conversation.",
        "capabilities": ["call notes", "deal risk", "forecast hygiene"],
        "domain_knowledge": (
            "## AI-enabled work\n\n"
            "Draft follow-ups from call notes.\n\n"
            "## Failure modes\n\n"
            "Invented discounts.\n"
        ),
        "source": "researched",
    }
    payload.update(overrides)
    return RoleCard.model_validate(payload)


def _seed_snapshot() -> list[tuple[str, str, str, str, tuple[str, ...]]]:
    return [
        (role.id, role.display_name, role.department, role.description, tuple(role.capabilities))
        for role in list_roles()
    ]


def test_normalize_role_id_matches_tool_slug_rules() -> None:
    assert normalize_role_id("Account Executive") == "account_executive"
    assert normalize_role_id("  AI-PM  ") == "ai_pm"


@pytest.mark.parametrize("raw", ["", "   ", "!!!", "123"])
def test_normalize_role_id_rejects_empty(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_role_id(raw)


def test_card_requires_three_capabilities() -> None:
    with pytest.raises(ValidationError):
        _card(capabilities=["only", "two"])


def test_cache_roundtrip(isolated_state: Path) -> None:
    user = _user()
    card = _card()
    cache_role(user, card)

    path = isolated_state / user.user_id / "role_cache" / "account_executive.json"
    assert path.is_file()
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["id"] == "account_executive"
    assert stored["department"] == "account_executive"
    assert stored["source"] == "researched"
    assert len(stored["capabilities"]) >= 3
    assert "Failure modes" in stored["domain_knowledge"]

    loaded = load_role_for_user(user, "account_executive")
    assert loaded.id == card.id
    assert loaded.display_name == card.display_name
    assert loaded.department == card.id
    assert loaded.description == card.description
    assert loaded.capabilities == card.capabilities
    assert loaded.domain_knowledge == card.domain_knowledge
    assert loaded.source == "researched"
    assert loaded.directory is None
    assert loaded.domain_knowledge_path is None

    other = _user("bob")
    with pytest.raises(KeyError):
        load_role_for_user(other, "account_executive")


def test_research_replaces_seed_for_the_user_only(isolated_state: Path) -> None:
    before = _seed_snapshot()
    user = _user()
    cache_role(
        user,
        _card(
            id="support",
            department="support",
            display_name="Not The Seeded Support Role",
        ),
    )
    cache_role(user, _card())

    assert _seed_snapshot() == before
    seeded = load_role("support")
    assert seeded.source == "seed"
    assert seeded.display_name != "Not The Seeded Support Role"
    resolved = load_role_for_user(user, "support")
    assert resolved.display_name == "Not The Seeded Support Role"
    assert resolved.source == "researched"
    assert resolved.directory is None

    available = {role.id: role for role in list_available_roles(user)}
    assert "support" in available
    assert available["support"].source == "researched"
    assert available["account_executive"].source == "researched"

    duplicate = _user("cara")
    cache_role(
        duplicate,
        _card(
            id="customer_support",
            department="customer_support",
            display_name="Customer Support",
            description="Researched copy of the seeded support role.",
        ),
    )
    named = [
        role
        for role in list_available_roles(duplicate)
        if role.display_name == "Customer Support"
    ]
    assert len(named) == 1
    assert named[0].id == "customer_support"
    assert named[0].source == "researched"

    seed_yaml = repo_root() / "enablement_agents" / "roles" / "support" / "role.yaml"
    assert seed_yaml.is_file()
    assert delete_cached_role(user, "support") is True
    assert seed_yaml.is_file()
    assert load_role("support").id == "support"
    assert delete_cached_role(user, "support") is False
    assert delete_cached_role(user, "../support") is False


def test_researched_prompt_uses_inline_domain_knowledge() -> None:
    role = role_from_card(_card())
    assert role.domain_knowledge_path is None
    prompt = _build_system_prompt(role)
    assert "Invented discounts." in prompt
    assert role.display_name in prompt


def test_seeded_prompt_still_reads_domain_file() -> None:
    role = load_role("support")
    path = role.domain_knowledge_path
    assert path is not None
    body = path.read_text(encoding="utf-8")
    assert body.strip()
    assert body.strip() in _build_system_prompt(role)
