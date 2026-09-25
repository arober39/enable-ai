"""UI live plan model follows the shared enablement planner default."""

from __future__ import annotations

import pytest

from enablement_agents.role_agent import ENABLEMENT_AGENT_MODEL_ENV
from ui.api.live_runner import resolve_live_plan_model


def test_live_plan_defaults_to_opus(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UI_LIVE_MODEL", raising=False)
    monkeypatch.delenv(ENABLEMENT_AGENT_MODEL_ENV, raising=False)
    assert resolve_live_plan_model() == "claude-opus-5-5"


def test_live_plan_honors_enablement_agent_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UI_LIVE_MODEL", raising=False)
    monkeypatch.setenv(ENABLEMENT_AGENT_MODEL_ENV, "claude-sonnet-4-6")
    assert resolve_live_plan_model() == "claude-sonnet-4-6"


def test_ui_live_model_overrides_shared_planner_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing UI-only knob still wins when both are set."""
    monkeypatch.setenv(ENABLEMENT_AGENT_MODEL_ENV, "claude-sonnet-4-6")
    monkeypatch.setenv("UI_LIVE_MODEL", "claude-haiku-4-5-20251001")
    assert resolve_live_plan_model() == "claude-haiku-4-5-20251001"
