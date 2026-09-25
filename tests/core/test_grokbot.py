"""Copy-paste Grok Bot handoff. The gateway writer is not the step 7 path."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import core.grokbot_roster as roster
from core.grokbot import (
    GrokbotHandoff,
    HandoffCredentials,
    apply_recommendation,
    assignment_text,
    build_handoff,
)
from core.grokbot_roster import (
    RememberedBot,
    clear_remembered_rosters,
    load_remembered_bots,
    remember_bot,
)
from core.identity import local_user


@pytest.fixture(autouse=True)
def _isolate_remembered_roster(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep handoff memory under tmp_path. Tests must not write agent-state/."""

    def _state_path(user: object, *parts: str) -> Path:
        user_id = getattr(user, "user_id", "local")
        return tmp_path.joinpath(str(user_id), *parts)

    monkeypatch.setattr("core.grokbot_roster.state_path", _state_path)


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
        description="Turn Discord messages into content ideas.",
        notes="Use the community themes.",
        role_name="Developer Relations",
        tools=["discord", "google_docs"],
    )


def test_handoff_text_assigns_the_work_and_lists_the_tools() -> None:
    handoff = _sample_handoff()
    parsed = GrokbotHandoff.model_validate(handoff.model_dump())
    assert parsed.description.endswith(_body())
    assert "You are the Developer Relations bot." in parsed.description
    assert "for Enable AI recommendation" not in parsed.description
    assert "Do this work yourself in Grok Bot" not in parsed.description
    assert "Enable AI does not call these tools" not in parsed.description
    assert "Tools you should use: discord, google_docs" in parsed.description
    assert "Use the community themes." in parsed.description
    assert parsed.name == "Developer Relations"
    assert parsed.title == "Developer Relations"
    assert parsed.webhook_status is None
    assert parsed.webhook_message is None


def test_missing_jev_key_says_so_and_defaults_to_a_new_bot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("step 7 must not open the Grok Bot gateway without credentials")

    monkeypatch.setattr("core.grokbot._client", _boom)
    handoff = _sample_handoff(creds=_Creds({}))
    assert handoff.action == "create_fallback"
    assert handoff.placement.startswith("Jev did not choose a bot")
    assert "TYPESAFE_API_KEY" in handoff.placement
    assert "Create a new bot named Developer Relations." in handoff.placement
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
    assert "Create a new bot named Developer Relations." in handoff.placement
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
        "Jev recommends: create a new bot named Developer Relations."
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


def test_jev_key_comes_from_env_or_file_not_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JEV_API_KEY", "from-env")
    monkeypatch.setattr(
        "core.grokbot._file_env",
        lambda: {"JEV_API_KEY": "from-file", "GROKBOT_GATEWAY_URL": "http://gw"},
    )
    assert HandoffCredentials(_Creds({"JEV_API_KEY": "from-settings"})).get("JEV_API_KEY") == (
        "from-env"
    )
    monkeypatch.delenv("JEV_API_KEY")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    layered = HandoffCredentials(
        _Creds({"JEV_API_KEY": "from-settings", "TYPESAFE_API_KEY": "settings-typesafe"})
    )
    assert layered.get("JEV_API_KEY") == "from-file"
    assert layered.get("TYPESAFE_API_KEY") is None
    assert layered.get("GROKBOT_GATEWAY_URL") == "http://gw"
    monkeypatch.setattr(
        "core.grokbot._file_env",
        lambda: {"TYPESAFE_API_KEY": "from-typesafe-file"},
    )
    assert layered.get("TYPESAFE_API_KEY") == "from-typesafe-file"


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
    assert handoff.name == role[:80]
    assert handoff.title == role[:80]
    assert len(handoff.name) == 80
    assert len(handoff.title) == 80


def test_handoff_remembers_the_bot_without_gateway_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("step 7 must not open the Grok Bot gateway without credentials")

    monkeypatch.setattr("core.grokbot._client", _boom)
    handoff = _sample_handoff(creds=_Creds({}), role_id="devrel")
    assert handoff.action == "create_fallback"
    assert handoff.used_remembered_roster is False
    stored = load_remembered_bots(local_user())
    assert len(stored) == 1
    bot = stored[0]
    assert bot.name == "Developer Relations"
    assert bot.recommendation_id not in bot.name
    assert bot.title == "Developer Relations"
    assert bot.role_name == "Developer Relations"
    assert bot.role_id == "devrel"
    assert bot.recommendation_id == "R-003"
    assert bot.action == "create_fallback"
    assert bot.id == "local:developer-relations"
    assert "Turn Discord messages into content ideas." in bot.description
    assert "Jev did not choose" not in bot.description
    assert bot.remembered_at.tzinfo is not None


def test_later_handoff_offers_the_remembered_bot_without_a_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("remembered bots must not require the gateway")

    monkeypatch.setattr("core.grokbot._client", _boom)
    _sample_handoff(creds=_Creds({}))
    remembered = load_remembered_bots(local_user())[0]
    seen: dict[str, object] = {}

    def _decide(state: dict, questions: dict, creds: object) -> dict:
        seen["bots"] = state["existing_bots"]
        seen["criteria"] = questions["placement"]["criteria"]
        return {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": remembered.id, "confidence": 0.91}},
        }

    monkeypatch.setattr("core.grokbot.decide", _decide)
    handoff = build_handoff(
        recommendation_id="R-010",
        kind="orchestrate",
        description="Draft a conference talk from Discord threads.",
        notes=None,
        role_name="Developer Relations",
        tools=["discord"],
        creds=_Creds({"JEV_API_KEY": "jv_test"}),
    )
    assert handoff.used_remembered_roster is True
    assert handoff.action == "update"
    assert handoff.existing_bot_name == "Developer Relations"
    assert handoff.name == "Developer Relations"
    assert handoff.placement == (
        "Jev recommends: add this to existing bot Developer Relations."
    )
    bots = seen["bots"]
    assert isinstance(bots, list)
    assert bots[0]["id"] == remembered.id
    assert bots[0]["name"] == "Developer Relations"
    criteria = seen["criteria"]
    assert isinstance(criteria, dict)
    assert remembered.id in criteria
    assert "existing_bot" not in criteria
    assert "Developer Relations" in criteria[remembered.id]


def test_repeat_handoff_updates_the_remembered_bot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "core.grokbot.decide",
        lambda *args, **kwargs: {
            "mode": "stub",
            "reason": "missing credential: JEV_API_KEY",
            "answers": None,
        },
    )
    _sample_handoff(creds=_Creds({}))
    first = load_remembered_bots(local_user())[0]
    _sample_handoff(
        creds=_Creds({}),
        description="Refresh the Discord digest and publish the notes.",
    )
    stored = load_remembered_bots(local_user())
    assert len(stored) == 1
    assert stored[0].id == first.id
    assert stored[0].name == first.name
    assert stored[0].recommendation_id == "R-003"
    assert "Refresh the Discord digest" in stored[0].description
    assert stored[0].remembered_at >= first.remembered_at


def test_same_role_updates_one_bot_across_recommendations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("step 7 must not open the Grok Bot gateway without credentials")

    monkeypatch.setattr("core.grokbot._client", _boom)
    _sample_handoff(creds=_Creds({}))
    _sample_handoff(
        creds=_Creds({}),
        recommendation_id="R-006",
        description="Recommend talks from Discord trends.",
    )
    _sample_handoff(creds=_Creds({}), role_name="Community", recommendation_id="R-003")
    stored = load_remembered_bots(local_user())
    by_name = {bot.name: bot for bot in stored}
    assert set(by_name) == {"Developer Relations", "Community"}
    role_bot = by_name["Developer Relations"]
    assert role_bot.id == "local:developer-relations"
    assert role_bot.recommendation_id == "R-006"
    assert "Recommend talks from Discord trends." in role_bot.description
    assert "R-003" not in role_bot.name
    assert "R-006" not in role_bot.name


def test_legacy_recommendation_names_collapse_to_one_role_bot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = roster.state_path(local_user(), "grokbot_roster.json")
    path.parent.mkdir(parents=True)
    rows = []
    for index, rec in enumerate(("R-003", "R-005", "R-006"), start=1):
        rows.append(
            {
                "id": f"local:{rec.lower()}-developer-relations",
                "name": f"{rec} Developer Relations",
                "title": "Developer Relations",
                "description": f"work {rec}",
                "role_name": "Developer Relations",
                "role_id": "devrel",
                "recommendation_id": rec,
                "action": "create_fallback" if index < 3 else "update",
                "remembered_at": f"2026-09-25T00:00:0{index}+00:00",
            }
        )
    path.write_text(json.dumps(rows), encoding="utf-8")

    stored = load_remembered_bots(local_user())
    assert len(stored) == 1
    assert stored[0].name == "Developer Relations"
    assert stored[0].id == "local:developer-relations"
    assert stored[0].recommendation_id == "R-006"
    assert stored[0].description == "work R-006"

    seen: dict[str, object] = {}

    def _decide(state: dict, questions: dict, creds: object) -> dict:
        seen["bots"] = state["existing_bots"]
        return {
            "mode": "stub",
            "reason": "missing credential: TYPESAFE_API_KEY",
            "answers": None,
        }

    monkeypatch.setattr("core.grokbot.decide", _decide)
    handoff = build_handoff(
        recommendation_id="R-010",
        kind="orchestrate",
        description="Weekly content recommendations.",
        notes=None,
        role_name="Developer Relations",
        tools=["discord"],
        creds=_Creds({}),
    )
    bots = seen["bots"]
    assert isinstance(bots, list)
    assert [bot["name"] for bot in bots] == ["Developer Relations"]
    assert handoff.name == "Developer Relations"
    assert "R-006" not in handoff.name
    assert "add this to existing bot R-" not in handoff.placement
    written = json.loads(path.read_text(encoding="utf-8"))
    assert len(written) == 1
    assert written[0]["name"] == "Developer Relations"
    assert written[0]["recommendation_id"] == "R-010"


def test_missing_jev_key_fallback_stays_a_new_bot_after_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("step 7 must not open the Grok Bot gateway without credentials")

    monkeypatch.setattr("core.grokbot._client", _boom)
    first = build_handoff(
        recommendation_id="R-010",
        kind="orchestrate",
        description="Draft a conference talk from Discord threads.",
        notes=None,
        role_name="Developer Relations",
        tools=["discord"],
        creds=_Creds({}),
    )
    assert first.action == "create_fallback"
    assert first.used_remembered_roster is False
    second = _sample_handoff(creds=_Creds({}))
    assert second.used_remembered_roster is True
    assert second.action == "create_fallback"
    assert second.placement.startswith("Jev did not choose a bot")
    assert "TYPESAFE_API_KEY" in second.placement
    assert "Create a new bot named Developer Relations." in second.placement
    assert "Jev recommends:" not in second.description
    assert _body() in second.description


def test_unnamed_existing_choice_does_not_invent_a_bot(
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
    assert load_remembered_bots(local_user()) == []


def test_gateway_roster_keeps_local_only_bots(monkeypatch: pytest.MonkeyPatch) -> None:
    _sample_handoff(creds=_Creds({}))
    seen: dict[str, object] = {}

    def _decide(state: dict, questions: dict, creds: object) -> dict:
        seen["bots"] = state["existing_bots"]
        return {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": "new_bot", "confidence": 0.9}},
        }

    client = _patch(
        monkeypatch,
        {
            "listAgents": [
                {
                    "id": "ada",
                    "name": "Ada",
                    "title": "Writer",
                    "description": "",
                    "isGroup": False,
                }
            ]
        },
        {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": "new_bot", "confidence": 0.9}},
        },
    )
    monkeypatch.setattr("core.grokbot.decide", _decide)
    handoff = build_handoff(
        recommendation_id="R-010",
        kind="orchestrate",
        description="Draft a conference talk.",
        notes=None,
        role_name="Developer Relations",
        tools=["discord"],
        creds=_Creds(
            {
                "JEV_API_KEY": "jv_test",
                "GROKBOT_GATEWAY_URL": "http://127.0.0.1:1340",
                "SAND_GATEWAY_TOKEN": "token",
            }
        ),
    )
    assert handoff.used_remembered_roster is True
    assert handoff.action == "create"
    bots = seen["bots"]
    assert isinstance(bots, list)
    names = [bot["name"] for bot in bots]
    assert names == ["Developer Relations", "Ada"]
    assert [url.rsplit("/", 1)[-1] for url, _payload in client.calls] == ["listAgents"]


def test_gateway_id_wins_when_the_name_matches_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _patch(
        monkeypatch,
        {
            "listAgents": [
                {
                    "id": "ada",
                    "name": "Ada",
                    "title": "",
                    "description": "",
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
    _sample_handoff(
        creds=_Creds(
            {
                "JEV_API_KEY": "jv_test",
                "GROKBOT_GATEWAY_URL": "http://127.0.0.1:1340",
                "SAND_GATEWAY_TOKEN": "token",
            }
        )
    )
    stored = load_remembered_bots(local_user())
    assert len(stored) == 1
    assert stored[0].name == "Ada"
    assert "Turn Discord messages into content ideas." in stored[0].description

    seen: dict[str, object] = {}

    def _decide(state: dict, questions: dict, creds: object) -> dict:
        seen["bots"] = state["existing_bots"]
        return {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": "ada", "confidence": 0.9}},
        }

    monkeypatch.setattr("core.grokbot.decide", _decide)
    handoff = _sample_handoff(
        recommendation_id="R-010",
        creds=_Creds(
            {
                "JEV_API_KEY": "jv_test",
                "GROKBOT_GATEWAY_URL": "http://127.0.0.1:1340",
                "SAND_GATEWAY_TOKEN": "token",
            }
        ),
    )
    bots = seen["bots"]
    assert isinstance(bots, list)
    assert len(bots) == 1
    assert bots[0]["id"] == "ada"
    assert bots[0]["name"] == "Ada"
    assert "Turn Discord messages into content ideas." in bots[0]["description"]
    assert handoff.existing_bot_name == "Ada"
    assert len(load_remembered_bots(local_user())) == 1
    assert [url.rsplit("/", 1)[-1] for url, _payload in client.calls] == [
        "listAgents",
        "listAgents",
    ]


def test_overlapping_handoffs_keep_every_bot() -> None:
    errors: list[BaseException] = []

    def remember(index: int) -> None:
        try:
            remember_bot(
                local_user(),
                RememberedBot(
                    id="local:tmp",
                    name=f"Bot {index}",
                    title="Bot",
                    description="work",
                    role_name="Developer Relations",
                    role_id="devrel",
                    recommendation_id=f"R-{index:03d}",
                    action="create",
                    remembered_at=datetime(2026, 9, 25, tzinfo=UTC) + timedelta(seconds=index),
                ),
            )
        except BaseException as exc:  # noqa: BLE001 — the thread must report it
            errors.append(exc)

    threads = [threading.Thread(target=remember, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    stored = load_remembered_bots(local_user())
    assert {bot.name for bot in stored} == {f"Bot {index}" for index in range(8)}


def test_remembered_roster_stays_bounded() -> None:
    start = datetime(2026, 9, 25, tzinfo=UTC)
    for index in range(45):
        remember_bot(
            local_user(),
            RememberedBot(
                id="local:tmp",
                name=f"Bot {index:02d}",
                title="Bot",
                description="work",
                role_name="Developer Relations",
                role_id="devrel",
                recommendation_id=f"R-{index:03d}",
                action="create",
                remembered_at=start + timedelta(seconds=index),
            ),
        )
    stored = load_remembered_bots(local_user())
    assert len(stored) == 40
    names = {bot.name for bot in stored}
    assert "Bot 00" not in names
    assert "Bot 04" not in names
    assert "Bot 05" in names
    assert "Bot 44" in names


def test_corrupt_roster_file_does_not_block_a_handoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    roster = tmp_path / "local" / "grokbot_roster.json"
    roster.parent.mkdir(parents=True)
    roster.write_text("{not json", encoding="utf-8")
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
    assert handoff.used_remembered_roster is False
    assert load_remembered_bots(local_user())[0].name == "Developer Relations"


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
                    "name": "Developer Relations",
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
    assert out["bot"]["name"] == "Developer Relations"
    create = next(body for url, body in client.calls if url.endswith("/createAgent"))
    assert create["name"] == "Developer Relations"
    assert create["title"] == "Developer Relations"
    assert create["description"] == assignment_text(
        description="Turn Discord messages into content ideas.",
        notes="Use the community themes.",
        role_name="Developer Relations",
        tools=["discord", "google_docs"],
    )
    assert "You are the Developer Relations bot." in create["description"]
    assert "for Enable AI recommendation" not in create["description"]
    assert "Do this work yourself in Grok Bot" not in create["description"]
    assert "Enable AI does not call these tools" not in create["description"]
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


def test_cleared_roster_is_invisible_until_this_process_writes_again(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("remembered bots must not require the gateway")

    monkeypatch.setattr("core.grokbot._client", _boom)
    assert clear_remembered_rosters(tmp_path / "missing") == 0
    first = _sample_handoff(creds=_Creds({}))
    assert first.used_remembered_roster is False
    assert load_remembered_bots(local_user())[0].name == "Developer Relations"

    other = tmp_path / "ada" / "grokbot_roster.json"
    other.parent.mkdir()
    other.write_text("[]", encoding="utf-8")
    unrelated = tmp_path / "local" / "credentials.json"
    unrelated.write_text("{}", encoding="utf-8")

    assert clear_remembered_rosters(tmp_path) == 2
    assert load_remembered_bots(local_user()) == []
    assert unrelated.is_file()
    assert not other.exists()

    seen: dict[str, object] = {}

    def _decide(state: dict, questions: dict, creds: object) -> dict:
        seen["bots"] = state["existing_bots"]
        return {
            "mode": "real",
            "reason": None,
            "answers": {
                "placement": {"choice": "local:developer-relations", "confidence": 0.95}
            },
        }

    monkeypatch.setattr("core.grokbot.decide", _decide)
    fresh = build_handoff(
        recommendation_id="R-006",
        kind="orchestrate",
        description="Recommend talks from Discord trends.",
        notes=None,
        role_name="Developer Relations",
        tools=["discord"],
        creds=_Creds({"JEV_API_KEY": "jv_test"}),
    )
    assert seen["bots"] == []
    assert fresh.used_remembered_roster is False
    assert fresh.action == "create_fallback"
    assert fresh.name == "Developer Relations"
    assert "R-006" not in fresh.name
    assert "add this to existing bot" not in fresh.placement
    remembered = load_remembered_bots(local_user())
    assert len(remembered) == 1
    assert remembered[0].name == "Developer Relations"
    assert remembered[0].recommendation_id == "R-006"

    def _again(state: dict, questions: dict, creds: object) -> dict:
        bots = state["existing_bots"]
        assert isinstance(bots, list)
        assert len(bots) == 1
        assert bots[0]["name"] == "Developer Relations"
        return {
            "mode": "real",
            "reason": None,
            "answers": {"placement": {"choice": bots[0]["id"], "confidence": 0.93}},
        }

    monkeypatch.setattr("core.grokbot.decide", _again)
    follow = build_handoff(
        recommendation_id="R-010",
        kind="orchestrate",
        description="Draft a conference talk.",
        notes=None,
        role_name="Developer Relations",
        tools=["discord"],
        creds=_Creds({"JEV_API_KEY": "jv_test"}),
    )
    assert follow.used_remembered_roster is True
    assert follow.existing_bot_name == "Developer Relations"
    assert follow.placement == (
        "Jev recommends: add this to existing bot Developer Relations."
    )
