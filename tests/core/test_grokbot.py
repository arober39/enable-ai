"""Copy-paste Grok Bot handoff. The gateway writer is not the step 7 path."""

from __future__ import annotations

import pytest

from core.grokbot import (
    GrokbotHandoff,
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


def test_handoff_text_assigns_the_work_and_lists_the_tools() -> None:
    handoff = build_handoff(
        recommendation_id="R-003",
        kind="orchestrate",
        description="Turn Discord messages into content ideas.",
        notes="Use the community themes.",
        role_name="Developer Relations",
        tools=["discord", "google_docs"],
    )
    parsed = GrokbotHandoff.model_validate(handoff.model_dump())
    expected = assignment_text(
        recommendation_id="R-003",
        kind="orchestrate",
        description="Turn Discord messages into content ideas.",
        notes="Use the community themes.",
        role_name="Developer Relations",
        tools=["discord", "google_docs"],
    )
    assert parsed.description == expected
    assert parsed.description == "\n\n".join(
        [
            "You are the Developer Relations bot for Enable AI recommendation R-003 (orchestrate).",
            "Do this work yourself in Grok Bot. Enable AI does not call these tools.",
            "Tools you should use: discord, google_docs",
            "Turn Discord messages into content ideas.",
            "Use the community themes.",
        ]
    )
    assert parsed.name == "R-003 Developer Relations"
    assert parsed.title == "Developer Relations"


def test_handoff_needs_no_gateway_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("step 7 must not open the Grok Bot gateway or ask Jev")

    monkeypatch.setattr("core.grokbot._client", _boom)
    monkeypatch.setattr("core.grokbot.decide", _boom)
    handoff = build_handoff(
        recommendation_id="R-001",
        kind="use_native_ai",
        description="Turn on the vendor assistant.",
        notes=None,
        role_name="Support",
        tools=[],
    )
    assert "Tools you should use: the tools named in the task" in handoff.description
    assert "Enable AI does not call these tools" in handoff.description
    assert handoff.name == "R-001 Support"
    assert handoff.title == "Support"


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
