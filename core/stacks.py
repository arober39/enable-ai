"""Declared role stacks — `stacks/<department>.yaml`.

The UI and the enablement agents both start from this file: a role
plus the tools that department actually uses. Adding a role is a
directory under `enablement_agents/roles/` and a matching stack file.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from core.roles import load_role
from core.state import repo_root


class StackNotFoundError(FileNotFoundError):
    """Raised when a known role has no `stacks/<department>.yaml`."""


def stack_path_for_role(role_id: str) -> Path:
    """Absolute path to the stack file for `role_id`.

    Raises `KeyError` when the role is not in the registry.
    """
    role = load_role(role_id)
    return repo_root() / "stacks" / f"{role.department}.yaml"


def declared_tool_names(role_id: str) -> list[str]:
    """Return the canonical tool names in the role's declared stack, in file order.

    Raises `KeyError` for an unknown role and `StackNotFoundError` when
    the stack file is missing. The department field inside the file must
    match the role, so a mis-copied stack cannot be served under the
    wrong department.
    """
    path = stack_path_for_role(role_id)
    if not path.exists():
        raise StackNotFoundError(f"No declared stack at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Stack file {path} is not a mapping")
    role = load_role(role_id)
    department = raw.get("department")
    if department != role.department:
        raise ValueError(
            f"Stack {path.name} declares department {department!r}, expected {role.department!r}"
        )
    tools = raw.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError(f"Stack {path.name} has no tools")
    names: list[str] = []
    for item in tools:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError(f"Stack {path.name} has a tool entry without a name")
        names.append(item["name"])
    return names
