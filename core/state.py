"""Per-user state path helpers.

Locked phase 1 commitment (#3): all on-disk state lives under a
per-user directory, even locally. With `user_id="local"` the layout
looks flat, but it is multi-user-ready from day one. Do not hand-build
state paths — route every read/write through these helpers so the
layout can evolve in one place.
"""

from __future__ import annotations

from pathlib import Path

from core.identity import UserContext

#: Resolved at import time. This file is at <repo>/core/state.py.
_REPO_ROOT: Path = Path(__file__).resolve().parents[1]


def repo_root() -> Path:
    """Repo root. Exposed for callers that need anchor paths outside per-user state."""
    return _REPO_ROOT


def state_path(user: UserContext, *parts: str) -> Path:
    """Build a per-user state path under `agent-state/<user_id>/...`.

    Does not create the directory. Callers writing to the returned path
    are responsible for `parent.mkdir(parents=True, exist_ok=True)`.
    """
    base = _REPO_ROOT / "agent-state" / user.user_id
    return base.joinpath(*parts) if parts else base


def orchestrator_path(user: UserContext, role: str, *parts: str) -> Path:
    """Build a per-user, per-role orchestrator path.

    Phase 1 note: the legacy committed orchestrator at
    `orchestrators/support/` does NOT use this layout yet — it predates
    the abstraction. The migration to `orchestrators/<user_id>/<role>/`
    happens when the LLM-driven generator lands in phase 1.4. New
    generated orchestrators must use this helper.
    """
    base = _REPO_ROOT / "orchestrators" / user.user_id / role
    return base.joinpath(*parts) if parts else base
