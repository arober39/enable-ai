"""User identity threaded through every API endpoint and state read.

Locked phase 1 commitment (#2): every API endpoint constructs or receives
a `UserContext`, even though `user_id` is hardcoded to `"local"` for now.
Phase 2 populates it from auth. Do not bypass this by assuming
single-user — retrofit cost later is the painful part of the transition.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

LOCAL_USER_ID = "local"


class UserContext(BaseModel):
    """Identity context for the calling user.

    In phase 1, `user_id` is always `"local"`. In phase 2+, it comes
    from authenticated sessions. Code must not branch on the value of
    `user_id`; it should be treated as opaque.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str = Field(default=LOCAL_USER_ID, min_length=1)


def local_user() -> UserContext:
    """Phase 1 convenience — the single-user-local user context."""
    return UserContext(user_id=LOCAL_USER_ID)
