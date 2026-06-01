"""Deterministic tests for the three Coordinator hooks.

Phase 7.1 — these tests are the contract for `enforce_credentials`,
`enforce_writes`, and `normalize_responses`. They run synchronously
through the hooks' async functions and assert on the returned
HookJSONOutput structure.

None of these tests make real API calls or hit the network. They exercise
the hook logic against constructed `PreToolUseHookInput` / `PostToolUseHookInput`
payloads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coordinator.hooks.enforce_credentials import enforce_credentials
from coordinator.hooks.enforce_writes import enforce_writes
from coordinator.hooks.normalize_responses import normalize_responses

REPO_ROOT = Path(__file__).resolve().parents[2]


class _StubContext:
    """Minimal stand-in for HookContext — only `signal` is read by hooks."""

    signal: Any = None


def _pre_input(
    tool_name: str,
    tool_input: dict[str, Any],
    cwd: str | None = None,
) -> dict[str, Any]:
    """Build a PreToolUseHookInput payload (TypedDicts are dicts at runtime)."""
    return {
        "session_id": "test-session",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": cwd or str(REPO_ROOT),
        "agent_id": "test-agent",
        "agent_type": "coordinator",
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": "tu-test",
    }


def _post_input(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_response: Any,
) -> dict[str, Any]:
    """Build a PostToolUseHookInput payload."""
    return {
        "session_id": "test-session",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": str(REPO_ROOT),
        "agent_id": "test-agent",
        "agent_type": "coordinator",
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": tool_response,
        "tool_use_id": "tu-test",
    }


def _permission_decision(out: dict[str, Any]) -> str | None:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision")


# ---------------------------------------------------------------------------
# enforce_credentials
# ---------------------------------------------------------------------------


@pytest.fixture
def demo_mode_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AI_DEMO_MODE", "true")


@pytest.fixture
def demo_mode_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_AI_DEMO_MODE", "false")


async def test_enforce_credentials_blocks_launchdarkly_curl(demo_mode_on: None) -> None:
    out = await enforce_credentials(
        _pre_input("Bash", {"command": "curl https://app.launchdarkly.com/api/v2/flags"}),
        "tu",
        _StubContext(),
    )
    assert _permission_decision(out) == "deny"
    reason = (out.get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")
    assert "Demo mode" in reason
    assert "launchdarkly.com" in reason.lower()


async def test_enforce_credentials_blocks_intercom_url_in_nested_input(
    demo_mode_on: None,
) -> None:
    out = await enforce_credentials(
        _pre_input(
            "Read",
            {"file_path": "harmless.txt", "extra": "https://api.intercom.io/conversations"},
        ),
        "tu",
        _StubContext(),
    )
    assert _permission_decision(out) == "deny"


async def test_enforce_credentials_allows_innocuous_bash(demo_mode_on: None) -> None:
    out = await enforce_credentials(
        _pre_input("Bash", {"command": "ls -la"}),
        "tu",
        _StubContext(),
    )
    assert out == {}


async def test_enforce_credentials_allows_real_calls_when_demo_off(
    demo_mode_off: None,
) -> None:
    out = await enforce_credentials(
        _pre_input("Bash", {"command": "curl https://app.launchdarkly.com"}),
        "tu",
        _StubContext(),
    )
    assert out == {}


# ---------------------------------------------------------------------------
# enforce_writes
# ---------------------------------------------------------------------------


async def test_enforce_writes_blocks_writes_outside_repo() -> None:
    out = await enforce_writes(
        _pre_input("Write", {"file_path": "/etc/passwd", "content": "x"}),
        "tu",
        _StubContext(),
    )
    assert _permission_decision(out) == "deny"


async def test_enforce_writes_blocks_dotenv_writes() -> None:
    out = await enforce_writes(
        _pre_input(
            "Write",
            {"file_path": str(REPO_ROOT / ".env"), "content": "x"},
        ),
        "tu",
        _StubContext(),
    )
    assert _permission_decision(out) == "deny"
    reason = (out.get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")
    assert ".env" in reason


async def test_enforce_writes_blocks_claudemd_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_CLAUDEMD_WRITES", "false")
    out = await enforce_writes(
        _pre_input(
            "Write",
            {"file_path": str(REPO_ROOT / "CLAUDE.md"), "content": "x"},
        ),
        "tu",
        _StubContext(),
    )
    assert _permission_decision(out) == "deny"


async def test_enforce_writes_allows_claudemd_with_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_CLAUDEMD_WRITES", "true")
    out = await enforce_writes(
        _pre_input(
            "Write",
            {"file_path": str(REPO_ROOT / "CLAUDE.md"), "content": "x"},
        ),
        "tu",
        _StubContext(),
    )
    assert out == {}


async def test_enforce_writes_blocks_writes_under_data_dir() -> None:
    out = await enforce_writes(
        _pre_input(
            "Write",
            {
                "file_path": str(REPO_ROOT / "data" / "support" / "x.json"),
                "content": "x",
            },
        ),
        "tu",
        _StubContext(),
    )
    assert _permission_decision(out) == "deny"


async def test_enforce_writes_allows_orchestrator_writes() -> None:
    out = await enforce_writes(
        _pre_input(
            "Write",
            {
                "file_path": str(
                    REPO_ROOT / "orchestrators" / "support" / "orchestrator.py"
                ),
                "content": "x",
            },
        ),
        "tu",
        _StubContext(),
    )
    assert out == {}


async def test_enforce_writes_ignores_read_tool() -> None:
    """The hook only fires on Write/Edit/NotebookEdit; Read passes through."""
    out = await enforce_writes(
        _pre_input("Read", {"file_path": str(REPO_ROOT / ".env")}),
        "tu",
        _StubContext(),
    )
    assert out == {}


# ---------------------------------------------------------------------------
# normalize_responses
# ---------------------------------------------------------------------------


async def test_normalize_wraps_loose_mcp_error() -> None:
    out = await normalize_responses(
        _post_input(
            "mcp__support__lookup_tool_capability",
            {"tool_name": "intercom"},
            {"isError": True, "message": "boom"},
        ),
        "tu",
        _StubContext(),
    )
    wrapped = (out.get("hookSpecificOutput") or {}).get("updatedMCPToolOutput")
    assert wrapped is not None
    assert wrapped["isError"] is True
    assert wrapped["errorCategory"] == "internal"
    assert wrapped["isRetryable"] is False
    assert isinstance(wrapped["message"], str)


async def test_normalize_passes_through_structured_mcp_error() -> None:
    structured = {
        "isError": True,
        "errorCategory": "not_found",
        "isRetryable": False,
        "message": "tool not found",
    }
    out = await normalize_responses(
        _post_input(
            "mcp__support__lookup_tool_capability",
            {"tool_name": "freshdesk"},
            structured,
        ),
        "tu",
        _StubContext(),
    )
    assert out == {}


async def test_normalize_passes_through_successful_mcp_response() -> None:
    success = {"content": [{"type": "text", "text": "ok"}]}
    out = await normalize_responses(
        _post_input("mcp__support__lookup_tool_capability", {}, success),
        "tu",
        _StubContext(),
    )
    assert out == {}


async def test_normalize_ignores_non_mcp_errors() -> None:
    """Only MCP tools (`mcp__*`) get normalized; Bash errors flow through."""
    out = await normalize_responses(
        _post_input("Bash", {}, {"isError": True, "message": "boom"}),
        "tu",
        _StubContext(),
    )
    assert out == {}
