"""Recommendation-run events stay quiet unless live mode has an SDK key."""

from __future__ import annotations

import pytest

from core.telemetry import reset_client_for_tests, track_workflow_run


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_client_for_tests()


def test_demo_mode_does_not_open_a_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AI_DEMO_MODE", "true")
    monkeypatch.setenv("LAUNCHDARKLY_SDK_KEY", "sdk-test")

    def _boom(sdk_key: str) -> object:
        raise AssertionError(f"client opened for {sdk_key}")

    monkeypatch.setattr("core.telemetry._shared_client", _boom)
    track_workflow_run(
        role_id="support",
        recommendation_id="R-001",
        status="ok",
        sdk_key="sdk-test",
    )


def test_missing_key_does_not_open_a_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AI_DEMO_MODE", "false")
    monkeypatch.delenv("LAUNCHDARKLY_SDK_KEY", raising=False)

    def _boom(sdk_key: str) -> object:
        raise AssertionError(sdk_key)

    monkeypatch.setattr("core.telemetry._shared_client", _boom)
    track_workflow_run(
        role_id="support",
        recommendation_id="R-001",
        status="failed",
        sdk_key=None,
    )


def test_live_mode_tracks_success_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AI_DEMO_MODE", "false")
    events: list[tuple[str, int | None]] = []

    class _Client:
        def track(self, name: str, context: object, metric_value: int) -> None:
            events.append((name, metric_value))

        def flush(self) -> None:
            events.append(("flush", None))

    monkeypatch.setattr("core.telemetry._shared_client", lambda sdk_key: _Client())
    track_workflow_run(
        role_id="marketing",
        recommendation_id="R-002",
        status="ok",
        sdk_key="sdk-test",
    )
    assert ("enablement.workflow_run", 1) in events
    assert ("enablement.workflow_error", 0) in events
    assert ("flush", None) in events
