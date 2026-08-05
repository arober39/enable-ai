"""Role registry loader.

Each role lives at `enablement_agents/roles/<role_id>/`:
  - role.yaml — id, display_name, department, description, capabilities
  - domain_knowledge.md — the AI-enablement reference for that role

Future sessions adding a role: drop a directory, fill in the two files,
the loader picks it up. No registration step required.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from core.state import repo_root

_ROLES_DIR_NAME = "enablement_agents/roles"
_ROLE_YAML = "role.yaml"
_DOMAIN_KNOWLEDGE = "domain_knowledge.md"


class Role(BaseModel):
    """One enablement role — content + metadata, no behavior."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(min_length=1)
    department: str = Field(min_length=1)
    description: str = Field(min_length=1)
    capabilities: list[str] = Field(min_length=1)

    #: Filesystem path to this role's directory. Not stored in role.yaml;
    #: populated by the loader. Callers read `domain_knowledge_path` for
    #: the system-prompt source.
    directory: Path

    @property
    def domain_knowledge_path(self) -> Path:
        return self.directory / _DOMAIN_KNOWLEDGE

    @property
    def agent_name(self) -> str:
        """Stamped into EnablementPlan.metadata.agent_name."""
        return f"{self.id}_enablement_agent"


def _roles_dir() -> Path:
    return repo_root() / _ROLES_DIR_NAME


def _load_one(role_dir: Path) -> Role | None:
    """Parse role.yaml for one role directory, returning None on error."""
    yaml_path = role_dir / _ROLE_YAML
    if not yaml_path.exists():
        return None
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    return Role.model_validate({**raw, "directory": role_dir})


@lru_cache(maxsize=1)
def list_roles() -> list[Role]:
    """Return all available roles, sorted by display_name.

    Cached for the process lifetime. The Next.js dev server restarts the
    backend on file changes, so adding a new role under
    enablement_agents/roles/ during dev picks up on next request.
    """
    roles: list[Role] = []
    base = _roles_dir()
    if not base.exists():
        return roles
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith("_") or child.name.startswith("."):
            continue
        role = _load_one(child)
        if role is not None:
            roles.append(role)
    roles.sort(key=lambda r: r.display_name)
    return roles


def load_role(role_id: str) -> Role:
    """Return the role with the given id, or raise KeyError."""
    for role in list_roles():
        if role.id == role_id:
            return role
    raise KeyError(f"unknown role: {role_id}")


def default_role() -> Role:
    """Convenience: support, falling back to the first role on disk if absent."""
    roles = list_roles()
    if not roles:
        raise RuntimeError(
            "no roles found under enablement_agents/roles/ — at least one is required"
        )
    for r in roles:
        if r.id == "support":
            return r
    return roles[0]
