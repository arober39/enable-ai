"""Adapter registry — single source of truth for what each tool/action does."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from core.credentials import Credentials

#: An adapter is an async function taking (action, params, credentials)
#: and returning a JSON-serializable dict. The convention is to include
#: a `mode: "real" | "stub"` key in the response when the adapter has
#: both real and stub paths, so the UI's trace can show which ran.
Adapter = Callable[[str, dict[str, Any], Credentials], Awaitable[dict[str, Any]]]

#: tool_name -> action_name -> description, for prompt-context only.
#: Listing an action here does NOT register it; you still need to call
#: `register(...)`. This is so the workflow generator's prompt can be
#: built from a flat dict without crawling adapters.
ACTION_CATALOG: dict[str, dict[str, str]] = {}

_REGISTRY: dict[str, Adapter] = {}


def register(tool_name: str, adapter: Adapter) -> None:
    """Register an adapter for a tool. Last writer wins.

    Adapters must be async. `tool_name` matches `WorkflowStep.tool`.
    """
    if not inspect.iscoroutinefunction(adapter):
        raise TypeError(f"adapter for {tool_name!r} must be `async def`")
    _REGISTRY[tool_name] = adapter


def get_adapter(tool_name: str) -> Adapter | None:
    return _REGISTRY.get(tool_name)


def list_tools() -> list[str]:
    return sorted(_REGISTRY.keys())


def describe_actions() -> dict[str, dict[str, str]]:
    """Return the {tool: {action: description}} catalog for prompt context."""
    return {tool: dict(actions) for tool, actions in ACTION_CATALOG.items()}
