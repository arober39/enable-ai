"""Enablement and build jobs keep running after the HTTP request returns."""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from ui.api.server import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("ui.api.server._demo_mode", lambda: True)
    return TestClient(app)


def _wait(client: TestClient, job_id: str) -> dict:
    last = {}
    for _ in range(20):
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] != "running":
            return last
        time.sleep(0.05)
    return last


def test_enablement_job_finishes_after_the_request_returns(client: TestClient) -> None:
    started = client.post(
        "/api/jobs/enablement",
        json={"tools": ["slack"], "role": "support"},
    )
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["kind"] == "enablement"
    assert body["started_at"]
    finished = _wait(client, body["id"])
    assert finished["status"] == "done"
    assert finished["result"]["mode"] == "demo"
    assert finished["result"]["plan"]["recommendations"]


def test_missing_job_is_404(client: TestClient) -> None:
    response = client.get("/api/jobs/does-not-exist")
    assert response.status_code == 404


def test_cancel_stops_a_running_job() -> None:
    from ui.api.jobs import cancel_job, get_job, spawn, start_job

    async def scenario() -> None:
        job = start_job("enablement")

        async def hang() -> dict[str, str]:
            await asyncio.sleep(30)
            return {"ok": "yes"}

        spawn(job.id, hang())
        await asyncio.sleep(0)
        cancelled = cancel_job(job.id)
        assert cancelled is not None
        await asyncio.sleep(0)
        stored = get_job(job.id)
        assert stored is not None
        assert stored.status == "cancelled"

    asyncio.run(scenario())
