"""The handoff endpoint returns paste text and does not call Grok Bot."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.grokbot import GrokbotHandoff, assignment_text
from ui.api.server import app


def test_handoff_endpoint_needs_no_gateway_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom() -> None:
        raise AssertionError("step 7 must not open the Grok Bot gateway")

    monkeypatch.setattr("core.grokbot._client", _boom)
    monkeypatch.setattr("core.grokbot.decide", _boom)
    monkeypatch.setattr("core.grokbot.apply_recommendation", _boom)

    response = TestClient(app).post(
        "/api/grokbot/handoff",
        json={
            "recommendation_id": "R-003",
            "kind": "orchestrate",
            "description": "Turn Discord messages into content ideas.",
            "notes": "Use the community themes.",
            "role_name": "Developer Relations",
            "tools": ["discord", "google_docs"],
        },
    )
    assert response.status_code == 200, response.text
    handoff = GrokbotHandoff.model_validate(response.json())
    assert handoff.description == assignment_text(
        recommendation_id="R-003",
        kind="orchestrate",
        description="Turn Discord messages into content ideas.",
        notes="Use the community themes.",
        role_name="Developer Relations",
        tools=["discord", "google_docs"],
    )
    assert handoff.name == "R-003 Developer Relations"
    assert handoff.title == "Developer Relations"
    assert "JEV_API_KEY" not in response.text
    assert "GROKBOT_GATEWAY_URL" not in response.text
    assert "SAND_GATEWAY_TOKEN" not in response.text
