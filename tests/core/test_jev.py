"""Jev decisions: real when the key works, heuristic otherwise."""

from __future__ import annotations

import httpx
import pytest

from core.jev import classify_coverage, label_escalation, should_escalate
from core.workflow import WorkflowDefinition, WorkflowStep
from enablement_agents.workflow_interpreter import run_workflow


class _Creds:
    def __init__(self, data: dict[str, str] | None = None) -> None:
        self._d = data or {}

    def get(self, key: str) -> str | None:
        return self._d.get(key)

    def require(self, key: str) -> str:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value


def test_coverage_without_key_is_heuristic() -> None:
    out = classify_coverage(
        tool_name="zendesk",
        categories=["knowledge_base"],
        capability=None,
        other_tools=["intercom"],
        creds=_Creds(),
    )
    assert out["mode"] == "stub"
    assert out["source"] == "heuristic"
    assert out["status"] == "covered"
    assert out["abstained"] is False


def test_coverage_uses_jev_when_confident(monkeypatch: pytest.MonkeyPatch) -> None:
    def _client() -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/v1/decide")
            return httpx.Response(
                200,
                json={
                    "model": "jev-latest",
                    "answers": {
                        "coverage": {
                            "type": "choice",
                            "choice": "gap",
                            "confidence": 0.91,
                            "probabilities": {"gap": 0.91, "covered": 0.09},
                        }
                    },
                },
            )

        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr("core.jev._make_client", _client)
    out = classify_coverage(
        tool_name="slack",
        categories=["internal_messaging"],
        capability="escalation_routing",
        other_tools=[],
        creds=_Creds({"JEV_API_KEY": "jv_live_test"}),
    )
    assert out["mode"] == "real"
    assert out["source"] == "jev"
    assert out["status"] == "gap"
    assert out["abstained"] is False


def test_low_confidence_does_not_claim_jev(monkeypatch: pytest.MonkeyPatch) -> None:
    def _client() -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "answers": {
                        "coverage": {
                            "type": "choice",
                            "choice": "redundant",
                            "confidence": 0.2,
                            "probabilities": {},
                        }
                    }
                },
            )

        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr("core.jev._make_client", _client)
    out = classify_coverage(
        tool_name="zendesk",
        categories=["knowledge_base"],
        capability=None,
        other_tools=[],
        creds=_Creds({"JEV_API_KEY": "jv_live_test"}),
    )
    assert out["source"] == "heuristic"
    assert out["abstained"] is True
    assert out["status"] == "covered"
    assert out["reason"] == "low_confidence"


def test_escalate_stub_uses_keywords() -> None:
    quiet = should_escalate({"inquiry": "where is my invoice"}, _Creds())
    hot = should_escalate({"inquiry": "I want a lawyer"}, _Creds())
    assert quiet["escalate"] is False
    assert quiet["source"] == "heuristic"
    assert hot["escalate"] is True
    assert hot["mode"] == "stub"


def test_uncertain_noul_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    def _client() -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"answers": {"escalate": {"type": "noul", "noul": 0.5}}},
            )

        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr("core.jev._make_client", _client)
    out = should_escalate({"inquiry": "hello"}, _Creds({"JEV_API_KEY": "jv_live_test"}))
    assert out["source"] == "heuristic"
    assert out["abstained"] is True
    assert out["escalate"] is False


async def test_interpreter_stops_before_tools_on_escalation() -> None:
    definition = WorkflowDefinition(
        name="gate",
        description="stop before tools",
        role_id="support",
        recommendation_id="R-001",
        steps=[
            WorkflowStep(id="health", tool="gainsight", action="get_account_health"),
        ],
    )
    result = await run_workflow(
        definition,
        {"inquiry": "This is a legal complaint"},
        _Creds(),  # type: ignore[arg-type]
    )
    assert result.ok
    assert result.output["escalated"] is True
    assert result.output["source"] == "heuristic"
    assert result.trace == []


def test_label_escalation_reads_output() -> None:
    scored = label_escalation(
        {"inquiry": "thanks"},
        {"text": "please escalate to a manager"},
        _Creds(),
    )
    assert scored["escalate"] is True
    assert isinstance(scored, dict)

