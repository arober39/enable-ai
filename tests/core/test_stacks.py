"""Declared stacks load for every registry role."""

from __future__ import annotations

import pytest

from core.identity import local_user
from core.roles import list_roles
from core.stacks import StackNotFoundError, declared_tool_names
from core.tool_catalog import load_tool


def test_every_role_has_a_declared_stack() -> None:
    roles = list_roles()
    assert {role.id for role in roles} >= {
        "support",
        "customer_success",
        "marketing",
        "devrel",
    }
    user = local_user()
    for role in roles:
        names = declared_tool_names(role.id)
        assert names, role.id
        for name in names:
            assert load_tool(user, name) is not None, f"{role.id} tool {name}"


def test_unknown_role_raises() -> None:
    with pytest.raises(KeyError):
        declared_tool_names("not_a_role")


def test_devrel_stack_is_docs_and_community() -> None:
    names = declared_tool_names("devrel")
    assert "discord" in names
    assert "google_docs" in names
    assert "discourse" not in names
    assert "docs" not in names
    user = local_user()
    for name in names:
        assert load_tool(user, name) is not None


def test_customer_success_stack_is_not_the_support_stack() -> None:
    support = set(declared_tool_names("support"))
    success = set(declared_tool_names("customer_success"))
    assert "gainsight" in success
    assert "intercom" not in success
    assert support != success


def test_missing_stack_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        "core.stacks.stack_path_for_role",
        lambda _role_id: tmp_path / "missing.yaml",
    )
    with pytest.raises(StackNotFoundError):
        declared_tool_names("support")
