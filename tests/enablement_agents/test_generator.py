"""Tests for the Phase 5 orchestrator generator.

Generates the support orchestrator into ``tmp_path`` and validates:
  - the file tree matches the Phase 5.1 spec
  - the generated ``.env.example`` is a strict subset of root ``.env.example``
  - the ai_configs.manifest.yaml pins tutorial-critical constants
  - v1_baseline.md vs v2_detailed_responses.md differ by exactly the
    over-volunteering instruction the tutorial demonstrates
  - the .mcp.json content reflects the plan's ``mcp_servers_used``
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coordinator.schemas import (
    CapabilityFinding,
    EnablementPlan,
    OrchestratorPRPlan,
    PlanMetadata,
    Recommendation,
)
from enablement_agents.support._orchestrator_generator import (
    generate_orchestrator_files,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _canonical_plan(
    *,
    mcp_used: list[str] | None = None,
    mcp_to_generate: list[str] | None = None,
) -> EnablementPlan:
    return EnablementPlan(
        department="support",
        summary="Test fixture plan.",
        capability_coverage=[
            CapabilityFinding(
                capability="intent_classification",
                status="covered",
                tools_involved=["intercom"],
                notes=None,
            )
        ],
        recommendations=[
            Recommendation(
                id="R-001",
                kind="orchestrate",
                description="Compose the stack.",
                tools_affected=["intercom", "zendesk", "slack", "hubspot"],
                effort="medium",
                notes=None,
            )
        ],
        orchestrator_pr_plan=OrchestratorPRPlan(
            branch="enable-ai/support",
            files_to_create=[],
            mcp_servers_used=mcp_used
            if mcp_used is not None
            else ["intercom", "zendesk", "slack"],
            mcp_servers_to_generate=mcp_to_generate
            if mcp_to_generate is not None
            else ["hubspot"],
            ai_configs_to_create=["support-orchestrator-config"],
            env_vars_required=["ANTHROPIC_API_KEY", "LAUNCHDARKLY_SDK_KEY"],
        ),
        metadata=PlanMetadata(
            generated_at=datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC),
            agent_name="support_enablement_agent",
            agent_version="0.1.0",
            stack_file_hash=hashlib.sha256(
                (REPO_ROOT / "stacks" / "support.yaml").read_bytes()
            ).hexdigest(),
            coordinator_session_id="sess-test",
        ),
    )


def _parse_env_vars(path: Path) -> set[str]:
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"([A-Z_][A-Z0-9_]*)\s*=", s)
        if m:
            names.add(m.group(1))
    return names


# ---------------------------------------------------------------------------
# File tree
# ---------------------------------------------------------------------------


_EXPECTED_FILES: list[str] = [
    "orchestrator.py",
    "agent_definition.py",
    "prompts/v1_baseline.md",
    "prompts/v2_detailed_responses.md",
    "judges/factual_accuracy.md",
    ".mcp.json",
    "mcp_servers/hubspot/__init__.py",
    "mcp_servers/hubspot/server.py",
    "observability.py",
    ".env.example",
    "Makefile",
    "README.md",
    "ai_configs.manifest.yaml",
]


def test_generator_writes_full_file_tree(tmp_path: Path) -> None:
    plan = _canonical_plan()
    result = generate_orchestrator_files(plan, tmp_path / "support")

    for rel in _EXPECTED_FILES:
        assert (tmp_path / "support" / rel).exists(), f"missing: {rel}"

    # The result also enumerates the files written.
    assert result.department == "support"
    assert "hubspot" in result.mcp_servers_generated


def test_generator_deterministic(tmp_path: Path) -> None:
    """Two consecutive runs from the same plan produce identical bytes."""
    plan = _canonical_plan()
    generate_orchestrator_files(plan, tmp_path / "run1")
    generate_orchestrator_files(plan, tmp_path / "run2")

    for rel in _EXPECTED_FILES:
        h1 = hashlib.sha256((tmp_path / "run1" / rel).read_bytes()).hexdigest()
        h2 = hashlib.sha256((tmp_path / "run2" / rel).read_bytes()).hexdigest()
        # README.md hash differs because it embeds generated_at; skip it.
        if rel == "README.md":
            continue
        assert h1 == h2, f"non-deterministic file: {rel}"


# ---------------------------------------------------------------------------
# .env.example is a strict subset of root .env.example
# ---------------------------------------------------------------------------


def test_generated_env_example_is_strict_subset_of_root(tmp_path: Path) -> None:
    plan = _canonical_plan()
    generate_orchestrator_files(plan, tmp_path / "support")
    root_vars = _parse_env_vars(REPO_ROOT / ".env.example")
    generated_vars = _parse_env_vars(tmp_path / "support" / ".env.example")
    extras = generated_vars - root_vars
    assert not extras, f"generated .env.example introduces new vars: {extras}"


# ---------------------------------------------------------------------------
# Tutorial-critical content: variation prompts and judge
# ---------------------------------------------------------------------------


def test_v1_vs_v2_differs_only_by_over_volunteering_instruction(
    tmp_path: Path,
) -> None:
    plan = _canonical_plan()
    generate_orchestrator_files(plan, tmp_path / "support")
    v1 = (tmp_path / "support/prompts/v1_baseline.md").read_text(encoding="utf-8")
    v2 = (tmp_path / "support/prompts/v2_detailed_responses.md").read_text(
        encoding="utf-8"
    )
    # v2 must be v1 plus one additional paragraph
    assert v2.startswith(v1)
    delta = v2[len(v1):]
    assert "explain related policies that may apply" in delta
    assert "user didn't ask about them" in delta


def test_judge_prompt_contains_tutorial_anchors(tmp_path: Path) -> None:
    plan = _canonical_plan()
    generate_orchestrator_files(plan, tmp_path / "support")
    judge = (tmp_path / "support/judges/factual_accuracy.md").read_text(
        encoding="utf-8"
    )
    anchors = [
        "grading a customer support response for factual accuracy",
        "Policy documentation: {policy_context}",
        "Customer question: {question}",
        "Agent response: {response}",
        "Return only the score as a decimal",
    ]
    for anchor in anchors:
        assert anchor in judge


def test_ai_configs_manifest_pins_tutorial_constants(tmp_path: Path) -> None:
    plan = _canonical_plan()
    generate_orchestrator_files(plan, tmp_path / "support")
    manifest = (tmp_path / "support/ai_configs.manifest.yaml").read_text(
        encoding="utf-8"
    )
    for needle in [
        "support-orchestrator-config",
        "claude-sonnet-4-7",
        "mode: completion",
        "v1-baseline",
        "v2-detailed-responses",
    ]:
        assert needle in manifest, f"manifest missing: {needle}"


def test_orchestrator_py_contains_runtime_constants(tmp_path: Path) -> None:
    plan = _canonical_plan()
    generate_orchestrator_files(plan, tmp_path / "support")
    orch = (tmp_path / "support/orchestrator.py").read_text(encoding="utf-8")
    for needle in [
        '"support.escalation"',
        '"support.error"',
        '"support-orchestrator-config"',
        '"claude-sonnet-4-7"',
    ]:
        assert needle in orch, f"orchestrator.py missing constant: {needle}"


# ---------------------------------------------------------------------------
# .mcp.json reflects the plan
# ---------------------------------------------------------------------------


def test_mcp_json_reflects_plan_servers(tmp_path: Path) -> None:
    plan = _canonical_plan(
        mcp_used=["intercom", "slack"], mcp_to_generate=["hubspot"]
    )
    generate_orchestrator_files(plan, tmp_path / "support")
    mcp = json.loads((tmp_path / "support/.mcp.json").read_text(encoding="utf-8"))
    assert set(mcp["mcpServers"].keys()) == {"intercom", "slack"}


def test_generator_rejects_plan_without_orchestrator_pr_plan(tmp_path: Path) -> None:
    plan = _canonical_plan()
    plan_no_pr = plan.model_copy(update={"orchestrator_pr_plan": None})
    with pytest.raises(ValueError, match="orchestrator_pr_plan"):
        generate_orchestrator_files(plan_no_pr, tmp_path / "support")
