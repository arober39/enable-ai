"""Optional LaunchDarkly events for recommendation runs.

Demo mode and a missing SDK key are no-ops. A failed send never changes
the workflow's HTTP result. This is the control-plane signal next to the
local outcome log: `enablement.workflow_run` is 1 on success and 0 on
failure; `enablement.workflow_error` is the inverse.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

EVENT_WORKFLOW_RUN = "enablement.workflow_run"
EVENT_WORKFLOW_ERROR = "enablement.workflow_error"

_client: Any = None


def _demo_mode() -> bool:
    return os.environ.get("ENABLE_AI_DEMO_MODE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _sdk_key() -> str | None:
    key = os.environ.get("LAUNCHDARKLY_SDK_KEY", "").strip()
    return key or None


def reset_client_for_tests() -> None:
    """Drop the cached SDK client. Tests only."""
    global _client
    _client = None


def _shared_client(sdk_key: str) -> Any:
    global _client
    if _client is None:
        from ldclient import Config, LDClient

        _client = LDClient(Config(sdk_key))
    return _client


def track_workflow_run(
    *,
    role_id: str,
    recommendation_id: str | None,
    status: str,
    sdk_key: str | None = None,
) -> None:
    """Send run success and error events. No-op in demo mode or without a key."""
    if _demo_mode() or status == "rolled_back":
        return
    sdk_key = (sdk_key or "").strip() or _sdk_key()
    if not sdk_key:
        logger.debug("track_workflow_run skipped: no LAUNCHDARKLY_SDK_KEY")
        return
    success = 1 if status == "ok" else 0
    context_key = recommendation_id or role_id
    try:
        from ldclient import Context

        client = _shared_client(sdk_key)
        context = Context.builder(f"{role_id}:{context_key}").kind("recommendation").build()
        client.track(EVENT_WORKFLOW_RUN, context, metric_value=success)
        client.track(EVENT_WORKFLOW_ERROR, context, metric_value=1 - success)
        client.flush()
    except Exception:  # noqa: BLE001 — measure must not fail the run
        logger.exception("track_workflow_run failed")
