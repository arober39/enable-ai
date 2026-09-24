"""The handoff endpoint returns paste text and does not write a Grok Bot."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.credentials import LocalFileCredentialStore
from core.grokbot import GrokbotHandoff, assignment_text
from core.identity import local_user
from ui.api.server import app

_BODY = {
    "recommendation_id": "R-003",
    "kind": "orchestrate",
    "description": "Turn Discord messages into content ideas.",
    "notes": "Use the community themes.",
    "role_name": "Developer Relations",
    "tools": ["discord", "google_docs"],
}


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("core.grokbot._file_env", lambda: {})
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("GROKBOT_GATEWAY_URL", raising=False)
    monkeypatch.delenv("SAND_GATEWAY_TOKEN", raising=False)

    def _state_path(user: object, *parts: str) -> Path:
        user_id = getattr(user, "user_id", "user")
        return tmp_path.joinpath(str(user_id), *parts)

    monkeypatch.setattr("core.credentials.state_path", _state_path)


def _assignment() -> str:
    return assignment_text(
        recommendation_id="R-003",
        kind="orchestrate",
        description="Turn Discord messages into content ideas.",
        notes="Use the community themes.",
        role_name="Developer Relations",
        tools=["discord", "google_docs"],
    )


def test_handoff_endpoint_missing_jev_key_still_returns_copy_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("gateway writes and listAgents are not required")

    monkeypatch.setattr("core.grokbot._client", _boom)
    response = TestClient(app).post("/api/grokbot/handoff", json=_BODY)
    assert response.status_code == 200, response.text
    handoff = GrokbotHandoff.model_validate(response.json())
    assert handoff.action == "create_fallback"
    assert "JEV_API_KEY" in handoff.placement
    assert "Jev recommends:" not in handoff.description
    assert "Create a new bot named R-003 Developer Relations." in handoff.description
    assert _assignment() in handoff.description
    assert "GROKBOT_GATEWAY_URL" not in response.text
    assert "SAND_GATEWAY_TOKEN" not in response.text


def test_handoff_endpoint_reads_jev_key_from_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)
    LocalFileCredentialStore(local_user()).set("JEV_API_KEY", "from-settings")
    seen: dict[str, str | None] = {}

    def _decide(state: object, questions: object, creds: object) -> dict[str, object]:
        seen["key"] = creds.get("JEV_API_KEY")  # type: ignore[attr-defined]
        return {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": "new_bot", "confidence": 0.9}},
        }

    monkeypatch.setattr("core.grokbot.decide", _decide)
    response = TestClient(app).post("/api/grokbot/handoff", json=_BODY)
    assert response.status_code == 200, response.text
    handoff = GrokbotHandoff.model_validate(response.json())
    assert seen["key"] == "from-settings"
    assert handoff.placement == (
        "Jev recommends: create a new bot named R-003 Developer Relations."
    )
    assert handoff.action == "create"
    assert _assignment() in handoff.description


def test_handoff_endpoint_reads_jev_key_from_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("JEV_API_KEY", "from-env")
    seen: dict[str, str | None] = {}

    def _decide(state: object, questions: object, creds: object) -> dict[str, object]:
        seen["key"] = creds.get("JEV_API_KEY")  # type: ignore[attr-defined]
        return {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": "existing_bot", "confidence": 0.8}},
        }

    monkeypatch.setattr("core.grokbot.decide", _decide)
    response = TestClient(app).post("/api/grokbot/handoff", json=_BODY)
    assert response.status_code == 200, response.text
    handoff = GrokbotHandoff.model_validate(response.json())
    assert seen["key"] == "from-env"
    assert "Jev recommends: add this to an existing bot." in handoff.placement
    assert "Pick which bot in Grok Bot." in handoff.description
    assert handoff.action == "update"
