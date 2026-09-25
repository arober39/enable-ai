"""HTTP checks for declared stacks and recommendation rollback."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.identity import UserContext, local_user
from core.roles import load_role
from core.stacks import declared_tool_names
from core.workflow import WorkflowDefinition, WorkflowStep
from core.workflow_storage import save_workflow
from ui.api.server import app
from ui.api.synthetic import build_synthetic_plan


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    def _state_path(user: UserContext, *parts: str) -> Path:
        return tmp_path.joinpath(user.user_id, *parts)

    monkeypatch.setattr("core.outcomes.state_path", _state_path)
    monkeypatch.setattr("core.workflow_storage.state_path", _state_path)
    return TestClient(app)


def test_declared_stack_for_each_role(client: TestClient) -> None:
    expected = {
        "support": {"intercom", "zendesk", "slack", "hubspot"},
        "customer_success": {"hubspot", "slack", "gainsight", "gong", "vitally"},
        "marketing": {"hubspot", "slack", "klaviyo", "marketo"},
        "devrel": {"slack", "github", "discord", "google_docs"},
    }
    for role_id, tools in expected.items():
        response = client.get(f"/api/stacks/{role_id}")
        assert response.status_code == 200, response.text
        assert set(response.json()["tools"]) == tools


def test_unknown_role_stack_is_404(client: TestClient) -> None:
    response = client.get("/api/stacks/not_a_role")
    assert response.status_code == 404
    deve = client.get("/api/stacks/deve")
    assert deve.status_code == 404


def test_prefix_role_research_is_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Anthropic client was constructed")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("enablement_agents.role_research.AsyncAnthropic", _boom)

    response = client.post("/api/roles/research", json={"name": "deve"})

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Developer Relations" in detail
    assert "full title" in detail


def test_demo_install_runs_and_is_measured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENABLE_AI_DEMO_MODE", "true")
    role = load_role("customer_success")
    tools = declared_tool_names(role.id)
    plan = build_synthetic_plan(tools, role, local_user())
    runtime = next(
        rec
        for rec in plan.recommendations
        if rec.kind in ("orchestrate", "augment_with_custom_ai")
    )
    built = client.post(
        "/api/build-workflow",
        json={
            "plan": plan.model_dump(mode="json"),
            "selected_recommendation_id": runtime.id,
            "tools": tools,
            "role": role.id,
        },
    )
    assert built.status_code == 200, built.text
    body = built.json()
    assert body["ok"] is True
    assert body["artifact_kind"] == "workflow"
    assert "model-authored" in body["explanation"]

    ran = client.post(
        "/api/run-workflow",
        json={"role": role.id, "payload": {"inquiry": "demo"}},
    )
    assert ran.status_code == 200, ran.text
    assert ran.json()["ok"] is True

    summary = client.get("/api/outcomes/summary")
    rows = [row for row in summary.json() if row["recommendation_id"] == runtime.id]
    assert rows[0]["runs"] == 1
    assert rows[0]["successes"] == 1
    assert rows[0]["real_call_rate"] == 0.0
    assert rows[0]["installed"] is True


def test_rollback_uninstalls_over_http(client: TestClient) -> None:
    user = UserContext(user_id="local")
    save_workflow(
        user,
        WorkflowDefinition(
            name="health",
            description="installed runtime",
            role_id="customer_success",
            recommendation_id="R-001",
            steps=[
                WorkflowStep(
                    id="health",
                    tool="gainsight",
                    action="get_account_health",
                )
            ],
        ),
    )
    summary = client.get("/api/outcomes/summary")
    assert summary.status_code == 200
    rows = [row for row in summary.json() if row["recommendation_id"] == "R-001"]
    assert rows[0]["installed"] is True

    rolled = client.post(
        "/api/rollback",
        json={"role": "customer_success", "recommendation_id": "R-001"},
    )
    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["status"] == "rolled_back"

    after = client.get("/api/outcomes/summary")
    rows = [row for row in after.json() if row["recommendation_id"] == "R-001"]
    assert rows[0]["installed"] is False
    assert rows[0]["rollbacks"] == 1
