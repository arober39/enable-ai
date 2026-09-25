"""Vault keys do not survive a server boot."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.credentials import LocalFileCredentialStore
from core.identity import UserContext


def test_clear_removes_stored_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _state_path(user: UserContext, *parts: str) -> Path:
        return tmp_path.joinpath(user.user_id, *parts)

    monkeypatch.setattr("core.credentials.state_path", _state_path)
    store = LocalFileCredentialStore(UserContext(user_id="local"))
    store.set("LAUNCHDARKLY_SDK_KEY", "sdk-from-last-run")
    store.set("ANTHROPIC_API_KEY", "anthropic-from-last-run")

    store.clear()

    assert store.list_keys() == []
    assert store.get("LAUNCHDARKLY_SDK_KEY") is None
