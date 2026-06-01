"""PreToolUse hook: deterministic write boundaries.

Blocks Write and Edit tool calls that would:
  - touch a path outside the repo root,
  - touch any `.env` file,
  - touch any `CLAUDE.md` file (unless `ALLOW_CLAUDEMD_WRITES=true`),
  - touch anything under `data/` at runtime.

The repo root is determined by walking up from the cwd looking for
`pyproject.toml`. The hook denies any write whose resolved absolute path
falls outside that root.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from claude_agent_sdk import HookContext, HookInput
from claude_agent_sdk.types import SyncHookJSONOutput

logger = logging.getLogger(__name__)

_WRITING_TOOLS = {"Write", "Edit", "NotebookEdit"}


def _repo_root_from(start: Path) -> Path:
    """Walk up from `start` until we find pyproject.toml; that's the repo root.

    Falls back to `start` if no marker found. Used to decide what counts as
    "outside the repo."
    """
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return cur


def _allow_claudemd_writes() -> bool:
    raw = os.environ.get("ALLOW_CLAUDEMD_WRITES", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_target_path(tool_name: str, tool_input: dict[str, Any]) -> Path | None:
    """Extract the target filesystem path from a Write/Edit/NotebookEdit input.

    Returns None if no path key found (the SDK should always include one, but
    we don't want to crash if the contract drifts).
    """
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return Path(value)
    return None


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


async def enforce_writes(
    input_data: HookInput,
    tool_use_id: str | None,
    context: HookContext,  # noqa: ARG001 — required by SDK signature
) -> SyncHookJSONOutput:
    """PreToolUse hook implementation for Write/Edit/NotebookEdit."""
    tool_name = str(input_data.get("tool_name", ""))
    if tool_name not in _WRITING_TOOLS:
        return {}

    tool_input_raw = input_data.get("tool_input") or {}
    if not isinstance(tool_input_raw, dict):
        return {}
    tool_input: dict[str, Any] = tool_input_raw

    target = _resolve_target_path(tool_name, tool_input)
    if target is None:
        return {}

    cwd_str = input_data.get("cwd")
    cwd = Path(cwd_str) if isinstance(cwd_str, str) and cwd_str else Path.cwd()
    repo_root = _repo_root_from(cwd)
    target_abs = target if target.is_absolute() else (cwd / target).resolve()

    def deny(reason: str) -> SyncHookJSONOutput:
        logger.info(
            "enforce_writes denied tool=%s target=%s tool_use_id=%s reason=%s",
            tool_name,
            target_abs,
            tool_use_id,
            reason,
        )
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            },
        }

    # Outside repo root
    if not _is_under(target_abs, repo_root):
        return deny(
            f"Write boundary: {target_abs} is outside the repo root ({repo_root}). "
            f"All writes must stay inside the project."
        )

    # .env files
    if target_abs.name == ".env":
        return deny(
            f"Write boundary: {target_abs} is a .env file. .env files are managed "
            f"by humans, never by agents. Update .env.example instead if you need "
            f"to declare a new variable."
        )

    # CLAUDE.md files
    if target_abs.name == "CLAUDE.md":
        if _allow_claudemd_writes():
            return {}
        return deny(
            f"Write boundary: {target_abs} is a CLAUDE.md file. CLAUDE.md files are "
            f"managed by humans. Set ALLOW_CLAUDEMD_WRITES=true to override "
            f"(generally only the build-time author should do this)."
        )

    # data/ directory at runtime
    data_dir = (repo_root / "data").resolve()
    if _is_under(target_abs, data_dir):
        return deny(
            f"Write boundary: {target_abs} is under data/. Runtime agents must not "
            f"mutate synthetic data — that's the Phase 2 build's job. If you need "
            f"to store generated artifacts, write them under orchestrators/ or "
            f"agent-state/ instead."
        )

    return {}
