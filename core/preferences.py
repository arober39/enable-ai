"""Per-user preferences — selected role and other persistent settings.

Phase 1 single-user-local: backed by a JSON file at
`agent-state/<user_id>/preferences.json`. Phase 2+ swaps to a per-user
DB row with the same interface.

Routes every read/write through `state_path(user, ...)` per locked
commitment #3, so the multi-user transition is a backend swap, not a
caller refactor.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from core.identity import UserContext
from core.roles import default_role
from core.state import state_path

_PREFERENCES_FILE = "preferences.json"


class Preferences(BaseModel):
    """User's persistent preferences across sessions."""

    model_config = ConfigDict(extra="forbid")

    selected_role: str = Field(min_length=1)


def _path_for(user: UserContext):
    return state_path(user, _PREFERENCES_FILE)


def get_preferences(user: UserContext) -> Preferences:
    """Return the user's preferences. Falls back to defaults if absent."""
    path = _path_for(user)
    if not path.exists():
        return Preferences(selected_role=default_role().id)
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    if not isinstance(raw, dict) or not raw:
        return Preferences(selected_role=default_role().id)
    return Preferences.model_validate(raw)


def set_selected_role(user: UserContext, role_id: str) -> Preferences:
    """Persist the user's selected role and return updated preferences."""
    prefs = get_preferences(user).model_copy(update={"selected_role": role_id})
    path = _path_for(user)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(prefs.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    return prefs
