"""Copy-paste Grok Bot handoff. The gateway writer is not the step 7 path."""

from __future__ import annotations

import pytest

from core.grokbot import (
    GrokbotHandoff,
    HandoffCredentials,
    apply_recommendation,
    assignment_text,
    build_handoff,
)


class _Creds:
    def __init__(self, data: dict[str, str]) -> None:
        self._d = data

    def get(self, key: str) -> str | None:
        return self._d.get(key)


class _Response:
    def __init__(self, body: object) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._body


class _Client:
    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def post(self, url: str, headers: dict, json: dict) -> _Response:
        self.calls.append((url, json))
        name = url.rsplit("/", 1)[-1]
        return _Response(self.routes[name])


def _patch(monkeypatch: pytest.MonkeyPatch, routes: dict[str, object], decision: dict) -> _Client:
    client = _Client(routes)
    monkeypatch.setattr("core.grokbot._client", lambda: client)
    monkeypatch.setattr("core.grokbot.decide", lambda *args, **kwargs: decision)
    return client


def _sample_handoff(**overrides: object) -> GrokbotHandoff:
    payload = {
        "recommendation_id": "R-003",
        "kind": "orchestrate",
        "description": "Turn Discord messages into content ideas.",
        "notes": "Use the community themes.",
        "role_name": "Developer Relations",
        "tools": ["discord", "google_docs"],
    }
    payload.update(overrides)
    return build_handoff(**payload)  # type: ignore[arg-type]


def _body() -> str:
    return assignment_text(
        recommendation_id="R-003",
        kind="orchestrate",
        description="Turn Discord messages into content ideas.",
        notes="Use the community themes.",
        role_name="Developer Relations",
        tools=["discord", "google_docs"],
    )


def test_handoff_text_assigns_the_work_and_lists_the_tools() -> None:
    handoff = _sample_handoff()
    parsed = GrokbotHandoff.model_validate(handoff.model_dump())
    assert parsed.description.endswith(_body())
    assert "Enable AI does not call these tools" in parsed.description
    assert "discord, google_docs" in parsed.description
    assert "Use the community themes." in parsed.description
    assert parsed.name == "R-003 Developer Relations"
    assert parsed.title == "Developer Relations"


def test_missing_jev_key_says_so_and_defaults_to_a_new_bot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("step 7 must not open the Grok Bot gateway without credentials")

    monkeypatch.setattr("core.grokbot._client", _boom)
    handoff = _sample_handoff(creds=_Creds({}))
    assert handoff.action == "create_fallback"
    assert handoff.placement.startswith("Jev did not choose a bot")
    assert "JEV_API_KEY" in handoff.placement
    assert "Create a new bot named R-003 Developer Relations." in handoff.placement
    assert "Jev recommends:" not in handoff.description
    assert handoff.description.startswith(handoff.placement)
    assert _body() in handoff.description


def test_low_confidence_is_not_labeled_as_a_jev_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "core.grokbot.decide",
        lambda *args, **kwargs: {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": "new_bot", "confidence": 0.2}},
        },
    )
    handoff = _sample_handoff(creds=_Creds({"JEV_API_KEY": "jv_test"}))
    assert handoff.action == "create_fallback"
    assert "low confidence" in handoff.placement
    assert "Jev recommends:" not in handoff.description
    assert "Create a new bot named R-003 Developer Relations." in handoff.placement
    assert _body() in handoff.description


def test_jev_recommendation_for_a_new_bot_is_in_the_assignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("no gateway credentials, so listAgents must not run")

    monkeypatch.setattr("core.grokbot._client", _boom)
    monkeypatch.setattr(
        "core.grokbot.decide",
        lambda *args, **kwargs: {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": "new_bot", "confidence": 0.9}},
        },
    )
    handoff = _sample_handoff(creds=_Creds({"JEV_API_KEY": "jv_test"}))
    assert handoff.action == "create"
    assert handoff.existing_bot_name is None
    assert handoff.placement == (
        "Jev recommends: create a new bot named R-003 Developer Relations."
    )
    assert handoff.description.startswith(handoff.placement)
    assert _body() in handoff.description


def test_jev_names_an_existing_bot_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _patch(
        monkeypatch,
        {
            "listAgents": [
                {
                    "id": "ada",
                    "name": "Ada",
                    "title": "Writer",
                    "description": "existing",
                    "isGroup": False,
                }
            ]
        },
        {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": "ada", "confidence": 0.9}},
        },
    )
    handoff = _sample_handoff(
        creds=_Creds(
            {
                "JEV_API_KEY": "jv_test",
                "GROKBOT_GATEWAY_URL": "http://127.0.0.1:1340",
                "SAND_GATEWAY_TOKEN": "token",
            }
        )
    )
    assert handoff.action == "update"
    assert handoff.existing_bot_name == "Ada"
    assert handoff.name == "Ada"
    assert handoff.placement == "Jev recommends: add this to existing bot Ada."
    assert handoff.description.startswith(handoff.placement)
    assert _body() in handoff.description
    assert [url.rsplit("/", 1)[-1] for url, _body in client.calls] == ["listAgents"]


def test_confident_new_bot_reads_the_roster_and_does_not_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _patch(
        monkeypatch,
        {"listAgents": []},
        {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": "new_bot", "confidence": 0.95}},
        },
    )
    handoff = _sample_handoff(
        creds=_Creds(
            {
                "JEV_API_KEY": "jv_test",
                "GROKBOT_GATEWAY_URL": "http://127.0.0.1:1340",
                "SAND_GATEWAY_TOKEN": "token",
            }
        )
    )
    assert handoff.action == "create"
    assert handoff.placement.startswith("Jev recommends: create a new bot named")
    assert [url.rsplit("/", 1)[-1] for url, _body in client.calls] == ["listAgents"]


def test_without_a_roster_jev_can_say_add_to_an_existing_bot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "core.grokbot.decide",
        lambda *args, **kwargs: {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": "existing_bot", "confidence": 0.8}},
        },
    )
    handoff = _sample_handoff(creds=_Creds({"JEV_API_KEY": "jv_test"}))
    assert handoff.action == "update"
    assert handoff.existing_bot_name is None
    assert "Jev recommends: add this to an existing bot." in handoff.placement
    assert "Pick which bot in Grok Bot." in handoff.placement
    assert _body() in handoff.description


def test_unreadable_roster_still_embeds_a_jev_recommendation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Down:
        def __enter__(self) -> _Down:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def post(self, url: str, headers: dict, json: dict) -> _Response:
            raise RuntimeError(f"down: {url}")

    monkeypatch.setattr("core.grokbot._client", lambda: _Down())
    monkeypatch.setattr(
        "core.grokbot.decide",
        lambda *args, **kwargs: {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": "new_bot", "confidence": 0.91}},
        },
    )
    handoff = _sample_handoff(
        creds=_Creds(
            {
                "JEV_API_KEY": "jv_test",
                "GROKBOT_GATEWAY_URL": "http://127.0.0.1:1340",
                "SAND_GATEWAY_TOKEN": "token",
            }
        )
    )
    assert handoff.action == "create"
    assert handoff.placement.startswith("Jev recommends: create a new bot named")


def test_handoff_credentials_prefer_settings_then_env_then_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JEV_API_KEY", "from-env")
    monkeypatch.setattr(
        "core.grokbot._file_env",
        lambda: {"JEV_API_KEY": "from-file", "GROKBOT_GATEWAY_URL": "http://gw"},
    )
    assert HandoffCredentials(_Creds({"JEV_API_KEY": "from-settings"})).get("JEV_API_KEY") == (
        "from-settings"
    )
    assert HandoffCredentials(_Creds({})).get("JEV_API_KEY") == "from-env"
    monkeypatch.delenv("JEV_API_KEY")
    layered = HandoffCredentials(_Creds({}))
    assert layered.get("JEV_API_KEY") == "from-file"
    assert layered.get("GROKBOT_GATEWAY_URL") == "http://gw"


def test_handoff_name_and_title_use_the_same_limits_as_the_gateway_writer() -> None:
    role = "R" * 100
    handoff = build_handoff(
        recommendation_id="R-003",
        kind="orchestrate",
        description="Do the work.",
        notes=None,
        role_name=role,
        tools=["slack"],
    )
    assert handoff.name == f"R-003 {role}"[:80]
    assert handoff.title == role[:80]
    assert len(handoff.name) == 80
    assert len(handoff.title) == 80


def test_missing_gateway_does_not_write() -> None:
    out = apply_recommendation(
        {"id": "R-003", "kind": "orchestrate", "description": "Turn Discord into posts."},
        "Developer Relations",
        ["discord", "google_docs"],
        _Creds({}),
    )
    assert out["mode"] == "stub"
    assert out["action"] == "none"


def test_jev_creates_a_bot_that_owns_the_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _patch(
        monkeypatch,
        {
            "listAgents": [],
            "createAgent": {
                "agent": {
                    "id": "bot-1",
                    "name": "R-003 Developer Relations",
                    "title": "Developer Relations",
                    "description": "assigned",
                }
            },
        },
        {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": "new_bot", "confidence": 0.9}},
        },
    )
    recommendation = {
        "id": "R-003",
        "kind": "orchestrate",
        "description": "Turn Discord messages into content ideas.",
        "notes": "Use the community themes.",
    }
    out = apply_recommendation(
        recommendation,
        "Developer Relations",
        ["discord", "google_docs"],
        _Creds(
            {
                "GROKBOT_GATEWAY_URL": "http://127.0.0.1:1340",
                "SAND_GATEWAY_TOKEN": "token",
            }
        ),
    )
    assert out["action"] == "created"
    assert out["source"] == "jev"
    assert out["bot"]["name"] == "R-003 Developer Relations"
    create = next(body for url, body in client.calls if url.endswith("/createAgent"))
    assert create["description"] == assignment_text(
        recommendation_id="R-003",
        kind="orchestrate",
        description="Turn Discord messages into content ideas.",
        notes="Use the community themes.",
        role_name="Developer Relations",
        tools=["discord", "google_docs"],
    )
    assert "Enable AI does not call these tools" in create["description"]
    assert "discord, google_docs" in create["description"]


def test_uncertain_jev_does_not_edit_a_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _patch(
        monkeypatch,
        {"listAgents": [{"id": "ada", "name": "Ada", "description": "existing", "isGroup": False}]},
        {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": "new_bot", "confidence": 0.2}},
        },
    )
    out = apply_recommendation(
        {"id": "R-003", "kind": "orchestrate", "description": "Turn Discord into posts."},
        "Developer Relations",
        ["discord"],
        _Creds(
            {
                "GROKBOT_GATEWAY_URL": "http://127.0.0.1:1340",
                "SAND_GATEWAY_TOKEN": "token",
            }
        ),
    )
    assert out["action"] == "none"
    assert out["source"] == "heuristic"
    assert all(not url.endswith("/createAgent") for url, _body in client.calls)
    assert all(not url.endswith("/updateAgent") for url, _body in client.calls)
