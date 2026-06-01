"""Shared pytest configuration for the Enable AI test suite.

Two responsibilities:

  1. Auto-skip ``@pytest.mark.live`` tests when ``ANTHROPIC_API_KEY`` is
     unset. The live marker is for tests that hit a real LLM; running them
     without a key just produces ugly auth failures. Skipping is cleaner.

  2. Provide a session-scoped fixture that regenerates the support
     orchestrator tree if it's missing. Phase 7.3 runtime tests import
     from ``orchestrators.support.orchestrator`` — if Phase 5's generated
     output was wiped, those tests would ImportError. The fixture
     re-renders templates into the canonical location and creates the
     ``__init__.py`` markers Python's import system needs.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Suppress OTel ConsoleSpanExporter output during tests. The exporter writes
# to stderr, which pytest captures and may close between tests; the
# BatchSpanProcessor's background flush then raises an "I/O on closed file"
# noise. Setting this env var BEFORE the observability module imports
# disables the console exporter entirely (spans still record internally).
os.environ.setdefault("OTEL_DISABLE_CONSOLE", "true")

import pytest  # noqa: E402 — env var must be set first

REPO_ROOT = Path(__file__).resolve().parent.parent

# Make repo importable so tests can `from orchestrators.support.orchestrator import ...`
sys.path.insert(0, str(REPO_ROOT))


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Auto-skip ``@pytest.mark.live`` tests when ``ANTHROPIC_API_KEY`` is unset.

    ``make test`` already filters with ``-m "not live"``, so this guard is
    mostly belt-and-suspenders for ``make test-live`` or direct ``pytest``
    invocations. It prevents the suite from failing loudly when the key
    isn't present — the live tests skip with a clear reason.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    skip_live = pytest.mark.skip(
        reason="ANTHROPIC_API_KEY not set; @pytest.mark.live tests skipped"
    )
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(scope="session", autouse=True)
def _ensure_support_orchestrator_generated() -> None:
    """Regenerate the support orchestrator tree if Phase 5 output is missing.

    Tests in tests/orchestrators/ import from orchestrators.support.* —
    that requires the generator's output to exist on disk. Phase 5
    normally produces it; this fixture is a safety net for fresh clones,
    cleaned working directories, or sequencing accidents.
    """
    out = REPO_ROOT / "orchestrators" / "support"
    marker = out / "orchestrator.py"

    needs_regen = not marker.exists()
    if needs_regen:
        from coordinator.schemas import (
            CapabilityFinding,
            EnablementPlan,
            OrchestratorPRPlan,
            PlanMetadata,
            Recommendation,
        )
        from enablement_agents.support.agent import SupportEnablementAgent

        # Build a minimal-but-valid EnablementPlan to feed the generator.
        # Tests don't care about the plan content beyond its structural
        # validity — what we need on disk is the generator's *output*.
        stack_path = REPO_ROOT / "stacks" / "support.yaml"
        plan = EnablementPlan(
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
                mcp_servers_used=["intercom", "zendesk", "slack"],
                mcp_servers_to_generate=["hubspot"],
                ai_configs_to_create=["support-orchestrator-config"],
                env_vars_required=["ANTHROPIC_API_KEY", "LAUNCHDARKLY_SDK_KEY"],
            ),
            metadata=PlanMetadata(
                generated_at=datetime.now(UTC),
                agent_name="support_enablement_agent",
                agent_version="0.1.0",
                stack_file_hash=hashlib.sha256(
                    stack_path.read_bytes()
                ).hexdigest(),
                coordinator_session_id="sess-fixture-test",
            ),
        )
        agent = SupportEnablementAgent.default()
        asyncio.run(agent.generate_orchestrator(plan))

    # Ensure __init__.py markers exist so Python sees the directories as packages.
    for sub in [
        out,
        REPO_ROOT / "orchestrators",
        out / "mcp_servers",
    ]:
        init = sub / "__init__.py"
        if sub.exists() and not init.exists():
            init.touch()
