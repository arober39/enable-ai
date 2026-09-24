"""Unified role catalog: seeded registry + per-user researched cache.

Single source of truth for "give me role X for user Y" across the live
runner, synthetic planner, and UI role picker. Two backends:

- Seeded roles — `enablement_agents/roles/<id>/` shipped with the repo.
  Read-only. Loaded by `core.roles`.
- Researched cache — `agent-state/<user_id>/role_cache/<id>.json`,
  written by `enablement_agents.role_research.research_role`.

Seeded roles win when an id exists in both. A researched card never
hides or rewrites a role that ships on disk.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.identity import UserContext
from core.roles import Role, list_roles, load_role
from core.state import state_path

_CACHE_SUBDIR = "role_cache"

#: Same canonical pattern as tool names: lowercase, digits, underscores.
_CANONICAL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class RoleCard(BaseModel):
    """Capability card stored for a researched job role."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, pattern=_CANONICAL_ID_RE.pattern)
    display_name: str = Field(min_length=1)
    department: str = Field(min_length=1)
    description: str = Field(min_length=1)
    capabilities: list[str] = Field(
        min_length=3,
        description="At least three short phrases for AI-enabled work in this job.",
    )
    domain_knowledge: str = Field(
        min_length=1,
        description=(
            "Markdown describing what AI-enabled work looks like for this job, "
            "including failure modes."
        ),
    )
    source: Literal["seed", "researched"] = "researched"

    @field_validator("capabilities")
    @classmethod
    def _nonempty_capabilities(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values]
        if any(not item for item in cleaned):
            raise ValueError("capabilities must be non-empty strings")
        return cleaned

    @field_validator("domain_knowledge")
    @classmethod
    def _nonblank_domain_knowledge(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("domain_knowledge must not be empty")
        return value

    @model_validator(mode="after")
    def _department_matches_id(self) -> Self:
        if self.department != self.id:
            raise ValueError("department must equal id")
        return self


def normalize_role_id(raw: str) -> str:
    """Coerce a typed job title into a canonical role id.

    Lowercases, replaces spaces and other separators with underscores, and
    strips characters outside `[a-z0-9_]`. Raises ValueError when the
    result is empty or does not match `[a-z][a-z0-9_]*`.
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", raw.strip()).strip("_").lower()
    if not slug or slug[0].isdigit():
        raise ValueError(f"could not derive a role id from {raw!r}")
    if not _CANONICAL_ID_RE.match(slug):
        raise ValueError(f"derived role id {slug!r} fails canonical pattern")
    return slug


def role_from_card(card: RoleCard) -> Role:
    """Runtime Role for a researched card. No directory; text is inline."""
    return Role(
        id=card.id,
        display_name=card.display_name,
        department=card.department,
        description=card.description,
        capabilities=list(card.capabilities),
        domain_knowledge=card.domain_knowledge,
        source="researched",
        directory=None,
    )


def _cache_path(user: UserContext, role_id: str) -> Path | None:
    if not _CANONICAL_ID_RE.match(role_id):
        return None
    return state_path(user, _CACHE_SUBDIR, f"{role_id}.json")


def _load_cached(user: UserContext, role_id: str) -> RoleCard | None:
    path = _cache_path(user, role_id)
    if path is None or not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    if not isinstance(raw, dict) or not raw:
        return None
    raw["source"] = "researched"
    return RoleCard.model_validate(raw)


def _cached_ids(user: UserContext) -> list[str]:
    directory = state_path(user, _CACHE_SUBDIR)
    if not directory.exists():
        return []
    ids = [
        path.stem
        for path in directory.glob("*.json")
        if _CANONICAL_ID_RE.match(path.stem)
    ]
    return sorted(ids)


def cache_role(user: UserContext, card: RoleCard) -> None:
    """Persist a researched role card under the user's role cache."""
    stored = card.model_copy(update={"source": "researched"})
    path = _cache_path(user, stored.id)
    if path is None:
        raise ValueError(f"refusing to cache role id {stored.id!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = stored.model_dump(mode="json")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def delete_cached_role(user: UserContext, role_id: str) -> bool:
    """Remove a researched role from the user's cache.

    Never deletes a seeded role directory. Returns True only when a cache
    file was removed.
    """
    path = _cache_path(user, role_id)
    if path is None or not path.exists():
        return False
    path.unlink()
    return True


def load_role_for_user(user: UserContext, role_id: str) -> Role:
    """Return the role for this user. Seeded roles win over the cache.

    Raises KeyError when the id is neither seeded nor cached for `user`.
    """
    try:
        return load_role(role_id)
    except KeyError:
        cached = _load_cached(user, role_id)
        if cached is None:
            raise KeyError(f"unknown role: {role_id}") from None
        return role_from_card(cached)


def list_available_roles(user: UserContext) -> list[Role]:
    """Seeded roles plus this user's researched roles, sorted by display name.

    When an id exists in both, the seeded role is returned.
    """
    by_id: dict[str, Role] = {role.id: role for role in list_roles()}
    for role_id in _cached_ids(user):
        if role_id in by_id:
            continue
        cached = _load_cached(user, role_id)
        if cached is not None:
            by_id[role_id] = role_from_card(cached)
    return sorted(by_id.values(), key=lambda role: role.display_name)
