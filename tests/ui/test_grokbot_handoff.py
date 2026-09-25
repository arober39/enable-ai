"""The handoff endpoint returns paste text and does not write a Grok Bot."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.credentials import LocalFileCredentialStore
from core.grokbot import GrokbotHandoff, assignment_text
from core.grokbot_roster import load_remembered_bots
from core.identity import local_user
from ui.api.server import _lifespan, app

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
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("GROKBOT_GATEWAY_URL", raising=False)
    monkeypatch.delenv("SAND_GATEWAY_TOKEN", raising=False)

    def _state_path(user: object, *parts: str) -> Path:
        user_id = getattr(user, "user_id", "user")
        return tmp_path.joinpath(str(user_id), *parts)

    monkeypatch.setattr("core.credentials.state_path", _state_path)
    monkeypatch.setattr("core.grokbot_roster.state_path", _state_path)


def _assignment() -> str:
    return assignment_text(
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
    assert "TYPESAFE_API_KEY" in handoff.placement
    assert "Jev recommends:" not in handoff.description
    assert "Create a new bot named Developer Relations." in handoff.description
    assert _assignment() in handoff.description
    assert "GROKBOT_GATEWAY_URL" not in response.text
    assert "SAND_GATEWAY_TOKEN" not in response.text


def test_handoff_endpoint_ignores_jev_key_in_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)
    LocalFileCredentialStore(local_user()).set("JEV_API_KEY", "from-settings")
    seen: dict[str, str | None] = {}

    def _decide(state: object, questions: object, creds: object) -> dict[str, object]:
        seen["key"] = creds.get("JEV_API_KEY")  # type: ignore[attr-defined]
        return {
            "mode": "stub",
            "reason": "missing credential: JEV_API_KEY",
            "answers": None,
        }

    monkeypatch.setattr("core.grokbot.decide", _decide)
    response = TestClient(app).post("/api/grokbot/handoff", json=_BODY)
    assert response.status_code == 200, response.text
    handoff = GrokbotHandoff.model_validate(response.json())
    assert seen["key"] is None
    assert "add it to .env" in handoff.placement
    assert handoff.action == "create_fallback"


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


def test_handoff_endpoint_remembers_a_bot_and_offers_it_next_time(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate(monkeypatch, tmp_path)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("gateway writes and listAgents are not required")

    monkeypatch.setattr("core.grokbot._client", _boom)
    client = TestClient(app)
    first = client.post("/api/grokbot/handoff", json={**_BODY, "role_id": "devrel"})
    assert first.status_code == 200, first.text
    opened = GrokbotHandoff.model_validate(first.json())
    assert opened.used_remembered_roster is False
    assert opened.action == "create_fallback"
    stored = load_remembered_bots(local_user())
    assert len(stored) == 1
    assert stored[0].name == "Developer Relations"
    assert stored[0].role_id == "devrel"
    assert (tmp_path / "local" / "grokbot_roster.json").is_file()

    seen: dict[str, object] = {}

    def _decide(state: dict, questions: object, creds: object) -> dict[str, object]:
        seen["bots"] = state["existing_bots"]
        return {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": stored[0].id, "confidence": 0.93}},
        }

    monkeypatch.setattr("core.grokbot.decide", _decide)
    monkeypatch.setenv("JEV_API_KEY", "from-env")
    second_body = {
        **_BODY,
        "recommendation_id": "R-010",
        "description": "Draft a conference talk from Discord threads.",
    }
    second = client.post("/api/grokbot/handoff", json=second_body)
    assert second.status_code == 200, second.text
    handoff = GrokbotHandoff.model_validate(second.json())
    assert handoff.used_remembered_roster is True
    assert handoff.action == "update"
    assert handoff.existing_bot_name == "Developer Relations"
    bots = seen["bots"]
    assert isinstance(bots, list)
    assert bots[0]["name"] == "Developer Relations"
    assert "GROKBOT_GATEWAY_URL" not in second.text
    assert "SAND_GATEWAY_TOKEN" not in second.text
    assert [bot.recommendation_id for bot in load_remembered_bots(local_user())] == ["R-010"]


async def test_server_startup_deletes_every_remembered_roster(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    agent_state = tmp_path / "agent-state"
    for user_id in ("local", "ada"):
        roster = agent_state / user_id / "grokbot_roster.json"
        roster.parent.mkdir(parents=True)
        roster.write_text('[{"name": "R-006 Developer Relations"}]', encoding="utf-8")
    kept = agent_state / "local" / "credentials.json"
    kept.write_text('{"ANTHROPIC_API_KEY": "from-last-process"}', encoding="utf-8")

    monkeypatch.setattr("core.grokbot_roster.repo_root", lambda: tmp_path)

    def _cred_path(user: object, *parts: str) -> Path:
        user_id = getattr(user, "user_id", "local")
        return tmp_path.joinpath("vault", str(user_id), *parts)

    monkeypatch.setattr("core.credentials.state_path", _cred_path)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    async with _lifespan(app):
        assert not (agent_state / "local" / "grokbot_roster.json").exists()
        assert not (agent_state / "ada" / "grokbot_roster.json").exists()
        assert kept.read_text(encoding="utf-8") == '{"ANTHROPIC_API_KEY": "from-last-process"}'
