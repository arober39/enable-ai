"""Per-user workflow persistence.

Phase 2.1 single-user-local: one JSON file per `(user, role)`. Storing
by role means picking a different recommendation for the same role
overwrites the prior workflow — same UX as 1.4. Saved-for-later still
holds the OTHER recommendations from the original plan.

`agent-state/<user_id>/workflows/<role_id>.json`
"""

from __future__ import annotations

from pathlib import Path

from core.identity import UserContext
from core.state import state_path
from core.workflow import WorkflowDefinition

_WORKFLOWS_SUBDIR = "workflows"


def _path_for(user: UserContext, role_id: str) -> Path:
    return state_path(user, _WORKFLOWS_SUBDIR, f"{role_id}.json")


def save_workflow(user: UserContext, definition: WorkflowDefinition) -> None:
    """Persist `definition` under the user/role pair."""
    path = _path_for(user, definition.role_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(definition.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)


def load_workflow(user: UserContext, role_id: str) -> WorkflowDefinition | None:
    """Return the user's workflow for `role_id`, or None if absent / malformed."""
    path = _path_for(user, role_id)
    if not path.exists():
        return None
    try:
        return WorkflowDefinition.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — corrupt or schema-evolved file
        return None


def list_workflows(user: UserContext) -> list[WorkflowDefinition]:
    """List every persisted workflow for `user`."""
    base = state_path(user, _WORKFLOWS_SUBDIR)
    if not base.exists():
        return []
    out: list[WorkflowDefinition] = []
    for child in sorted(base.glob("*.json")):
        try:
            out.append(WorkflowDefinition.model_validate_json(child.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return out


def delete_workflow(user: UserContext, role_id: str) -> bool:
    """Remove the workflow for `role_id`. Returns True if removed."""
    path = _path_for(user, role_id)
    if not path.exists():
        return False
    path.unlink()
    return True
