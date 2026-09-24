"""Deterministic tests that every role stack loads and resolves in the catalog.

Diagnose/Recommend reads ``stacks/<role>.yaml`` through ``StackFile`` (the
same model ``EnablementAgentBase.parse_stack`` uses) and looks up each
tool via ``core.tool_catalog.load_tool``. These tests pin that contract
so a role cannot ship a stack that names unknown tools or a department
that is not a role on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.identity import local_user
from core.roles import list_roles
from core.state import repo_root
from core.tool_catalog import load_tool
from enablement_agents.base import StackFile

_STACKS_DIR = repo_root() / "stacks"
_MCP_DIR = repo_root() / "mcp_registry"


def _stack_paths() -> list[Path]:
    return sorted(_STACKS_DIR.glob("*.yaml"))


def _load_stack(path: Path) -> StackFile:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return StackFile.model_validate(raw)


@pytest.fixture(scope="module")
def role_ids() -> set[str]:
    return {role.id for role in list_roles()}


@pytest.mark.parametrize("stack_path", _stack_paths(), ids=lambda p: p.stem)
def test_stack_parses_and_department_matches_role(
    stack_path: Path, role_ids: set[str]
) -> None:
    stack = _load_stack(stack_path)
    assert stack_path.stem == stack.department
    assert stack.department in role_ids
    assert stack.tools, "stack must declare at least one tool"


@pytest.mark.parametrize("stack_path", _stack_paths(), ids=lambda p: p.stem)
def test_stack_tools_exist_in_catalog(stack_path: Path) -> None:
    stack = _load_stack(stack_path)
    user = local_user()
    for tool in stack.tools:
        cap = load_tool(user, tool.name)
        assert cap is not None, f"{tool.name} missing from tools/ catalog"
        assert cap.canonical_name == tool.name
        mcp_path = _MCP_DIR / f"{tool.name}.yaml"
        assert mcp_path.exists(), f"{tool.name} missing mcp_registry/{tool.name}.yaml"


def test_every_role_has_a_stack_file(role_ids: set[str]) -> None:
    stack_depts = {path.stem for path in _stack_paths()}
    missing = role_ids - stack_depts
    assert not missing, f"roles missing stacks/<id>.yaml: {sorted(missing)}"
