"""Agent blueprint classifies confirmed work and stays a supervisor's plan."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.agent_architect import (
    AUTONOMY_FLAGS,
    TaskSelection,
    compile_blueprint,
    tasks_for_role,
)
from core.identity import local_user
from core.roles import load_role
from core.tool_catalog import load_tool
from ui.api.server import app


def _tools(*names: str):
    loaded = []
    user = local_user()
    for name in names:
        capability = load_tool(user, name)
        assert capability is not None, name
        loaded.append(capability)
    return loaded


def test_devrel_tasks_classify_across_github_and_discord() -> None:
    role = load_role("devrel")
    blueprint = compile_blueprint(
        role=role,
        capabilities=_tools("github", "discord"),
        selected_tasks=None,
        friction="I retype the same thread into the issue tracker.",
    )
    by_id = {item.task_id: item for item in blueprint.assessments}
    assert by_id["content_research"].classification == "AGENTIC"
    assert by_id["content_research"].hitl == "review"
    assert by_id["community_intelligence"].classification == "AGENTIC"
    assert by_id["sample_verification"].classification == "AUTOMATE"
    assert by_id["sample_verification"].deterministic_preferred is True
    assert by_id["demo_creation"].classification == "ASSIST"
    assert by_id["demo_creation"].hitl == "approve"
    assert by_id["demo_creation"].deterministic_preferred is True
    assert by_id["release_enablement"].classification == "AGENTIC"
    assert by_id["release_enablement"].hitl == "approve"
    assert by_id["event_prep"].classification == "ASSIST"
    assert by_id["event_prep"].hitl == "direct"
    assert by_id["public_reply"].classification == "HUMAN"
    assert by_id["public_reply"].hitl == "exception"

    shift = blueprint.supervision_shift
    assert "Supervision potential" in shift
    assert "higher-leverage work" in shift
    assert "worker to operator to supervisor" in shift
    assert "%" not in shift
    assert "delet" not in shift.lower()

    combined = " ".join(blueprint.agent_responsibilities)
    assert "GitHub" in combined
    assert "Discord" in combined
    assert "Pass the output of each tool into the next." in combined
    assert any("deterministic workflow" in line for line in blueprint.agent_responsibilities)
    assert blueprint.pain_points[0] == "I retype the same thread into the issue tracker."

    assert [target.id for target in blueprint.build_targets] == [
        "openai_agents",
        "claude",
        "langgraph",
        "n8n",
        "copilot_studio",
        "zapier",
        "custom_mcp",
    ]
    by_target = {target.id: target for target in blueprint.build_targets}
    assert by_target["openai_agents"].recommended is True
    assert by_target["n8n"].recommended is True
    assert by_target["copilot_studio"].recommended is False
    assert blueprint.autonomy_flags == list(AUTONOMY_FLAGS)
    assert "not wired" in blueprint.autonomy_note


def test_confirmed_tasks_outrank_the_baseline() -> None:
    role = load_role("devrel")
    blueprint = compile_blueprint(
        role=role,
        capabilities=_tools("github"),
        selected_tasks=[
            TaskSelection(id="content_research", label="Content research", source="occupational"),
            TaskSelection(id="office-hours", label="Office hours", source="actual"),
        ],
    )
    assert [item.task_id for item in blueprint.assessments] == [
        "content_research",
        "office-hours",
    ]
    assert blueprint.assessments[1].source == "actual"
    assert blueprint.assessments[1].label == "Office hours"


def test_empty_confirmation_keeps_no_baseline_tasks() -> None:
    role = load_role("devrel")
    blueprint = compile_blueprint(
        role=role,
        capabilities=_tools("discord"),
        selected_tasks=[],
    )
    assert blueprint.assessments == []
    assert "No tasks are confirmed" in blueprint.supervision_shift


def test_other_roles_use_capability_phrases() -> None:
    role = load_role("support")
    tasks = tasks_for_role(role)
    assert tasks
    assert len(tasks) <= 5
    assert all(task.source == "job_description" for task in tasks)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("ui.api.server._demo_mode", lambda: True)
    return TestClient(app)


def test_enablement_response_includes_the_blueprint(client: TestClient) -> None:
    listed = client.get("/api/work-tasks", params={"role": "devrel"})
    assert listed.status_code == 200, listed.text
    ids = {task["id"] for task in listed.json()}
    assert "content_research" in ids
    assert "public_reply" in ids

    response = client.post(
        "/api/enablement",
        json={
            "tools": ["github", "discord"],
            "role": "devrel",
            "friction": "Release notes are copied by hand.",
            "tasks": [
                {
                    "id": "sample_verification",
                    "label": "Verify a demo still runs",
                    "source": "occupational",
                },
                {
                    "id": "public_reply",
                    "label": "Send the public reply",
                    "source": "job_description",
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan"]["recommendations"]
    assessments = {item["task_id"]: item for item in body["blueprint"]["assessments"]}
    assert set(assessments) == {"sample_verification", "public_reply"}
    assert assessments["sample_verification"]["classification"] == "AUTOMATE"
    assert assessments["public_reply"]["classification"] == "HUMAN"
    assert "Release notes are copied by hand." in body["blueprint"]["pain_points"]
    relationship = " ".join(body["blueprint"]["agent_responsibilities"])
    assert "GitHub" in relationship and "Discord" in relationship


def test_demo_mode_skips_live_runner(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("live runner should not run in demo mode")

    monkeypatch.setattr("ui.api.server.run_live_plan", _boom)
    response = client.post(
        "/api/enablement",
        json={
            "tools": ["github", "discord"],
            "role": "devrel",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "demo"
