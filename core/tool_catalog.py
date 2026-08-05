"""Unified tool catalog: seed entries + per-user researched cache.

Single source of truth for "give me data for tool X for user Y" across
the live runner, synthetic planner, and UI catalog endpoint. Two backends
under the hood:

- Seed entries — the static `tools/<name>.yaml` + `mcp_registry/<name>.yaml`
  pair shipped with the repo. Read-only ground truth.
- Researched cache — `agent-state/<user_id>/tool_cache/<name>.json`,
  written by `enablement_agents.tool_research.research_tool`. User-scoped
  per locked phase 1 commitment #3.

The merge is "user cache wins if both exist." That way users can override
seed data with an LLM-researched replacement if a vendor's AI surface has
changed since the seed YAML was written. Read-write the same shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from core.identity import UserContext
from core.state import repo_root, state_path

_SEED_TOOLS_DIR = "tools"
_SEED_MCP_DIR = "mcp_registry"
_CACHE_SUBDIR = "tool_cache"

#: Canonical name pattern. Lowercase + digits + underscores. Used both for
#: validating user input and for filename slugs.
_CANONICAL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class NativeAIFeature(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    description: str
    maturity: str = Field(
        description="ga / beta / preview / deprecated / unknown"
    )
    coverage: str = Field(
        description="low / medium / high / unknown — how much of the capability surface this feature covers"
    )


class APISurface(BaseModel):
    model_config = ConfigDict(extra="allow")

    has_rest_api: bool
    has_webhooks: bool
    rate_limits: str = Field(
        description="standard / strict / generous / unknown"
    )


class MCPServerInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool
    origin: str | None = Field(
        default=None,
        description="official / community / reference / null when not available",
    )
    maintained_by: str | None = None
    url: str | None = None
    install: str | None = None
    tools_exposed: list[str] = Field(default_factory=list)


class ToolCapability(BaseModel):
    """Combined tool + MCP capability record. The single shape carrier."""

    model_config = ConfigDict(extra="allow")

    canonical_name: str = Field(pattern=_CANONICAL_NAME_RE.pattern)
    vendor: str = Field(min_length=1, description="Human display name")
    categories: list[str] = Field(default_factory=list)
    native_ai_features: list[NativeAIFeature] = Field(default_factory=list)
    api_surface: APISurface
    integration_patterns: list[str] = Field(default_factory=list)
    notes: str | None = None
    mcp_server: MCPServerInfo
    fallback_if_unavailable: str | None = None

    #: Populated by the loader, not stored in seed files. UI uses this to
    #: badge cards (e.g., "researched" vs. "seed catalog").
    source: Literal["seed", "researched"] = "seed"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def normalize_name(raw: str) -> str:
    """Coerce a user-typed tool name into canonical form.

    Lowercases, replaces spaces/dashes with underscores, strips non-allowed
    characters. Raises ValueError if the result is empty or starts with a
    digit (would fail the canonical name pattern).
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", raw.strip()).strip("_").lower()
    if not slug or slug[0].isdigit():
        raise ValueError(f"could not derive a canonical tool name from {raw!r}")
    if not _CANONICAL_NAME_RE.match(slug):
        raise ValueError(f"derived name {slug!r} fails canonical pattern")
    return slug


# ---------------------------------------------------------------------------
# Seed catalog (read-only)
# ---------------------------------------------------------------------------


def _seed_yaml(path: Path) -> dict | None:
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def _seed_names() -> list[str]:
    base = repo_root() / _SEED_TOOLS_DIR
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob("*.yaml"))


def _load_seed(name: str) -> ToolCapability | None:
    tool_data = _seed_yaml(repo_root() / _SEED_TOOLS_DIR / f"{name}.yaml")
    if tool_data is None:
        return None
    mcp_data = _seed_yaml(repo_root() / _SEED_MCP_DIR / f"{name}.yaml") or {}
    merged = {
        "canonical_name": tool_data.get("canonical_name", name),
        "vendor": tool_data.get("vendor", name),
        "categories": tool_data.get("categories") or [],
        "native_ai_features": tool_data.get("native_ai_features") or [],
        "api_surface": tool_data.get("api_surface")
        or {"has_rest_api": False, "has_webhooks": False, "rate_limits": "unknown"},
        "integration_patterns": tool_data.get("integration_patterns") or [],
        "notes": tool_data.get("notes"),
        "mcp_server": mcp_data.get("mcp_server")
        or {"available": False, "tools_exposed": []},
        "fallback_if_unavailable": mcp_data.get("fallback_if_unavailable"),
        "source": "seed",
    }
    return ToolCapability.model_validate(merged)


# ---------------------------------------------------------------------------
# User cache (read/write, per-user)
# ---------------------------------------------------------------------------


def _cache_path(user: UserContext, name: str) -> Path:
    return state_path(user, _CACHE_SUBDIR, f"{name}.json")


def _cache_dir(user: UserContext) -> Path:
    return state_path(user, _CACHE_SUBDIR)


def _load_cached(user: UserContext, name: str) -> ToolCapability | None:
    path = _cache_path(user, name)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    if not isinstance(raw, dict) or not raw:
        return None
    raw["source"] = "researched"
    return ToolCapability.model_validate(raw)


def _cached_names(user: UserContext) -> list[str]:
    d = _cache_dir(user)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def cache_tool(user: UserContext, capability: ToolCapability) -> None:
    """Persist a researched capability to the user's cache."""
    path = _cache_path(user, capability.canonical_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Strip the `source` marker before writing — it's populated on load.
    payload = capability.model_dump(mode="json", exclude={"source"})
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def delete_cached_tool(user: UserContext, name: str) -> bool:
    """Remove a researched tool from the user's cache. Returns True if removed."""
    path = _cache_path(user, name)
    if not path.exists():
        return False
    path.unlink()
    return True


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def load_tool(user: UserContext, name: str) -> ToolCapability | None:
    """Return the capability for `name`, user cache winning over seed.

    Returns None if the tool exists in neither. Callers that need to
    distinguish "missing" from "research it" should use `is_known()`.
    """
    cached = _load_cached(user, name)
    if cached is not None:
        return cached
    return _load_seed(name)


def is_known(user: UserContext, name: str) -> bool:
    """True if the tool exists in the user's cache or the seed catalog."""
    return load_tool(user, name) is not None


def list_tools(user: UserContext) -> list[ToolCapability]:
    """Return every tool available to `user`, deduplicated, sorted by vendor.

    User cache wins on conflict — if a seed tool was overridden by a
    researched entry, the researched version is returned.
    """
    names = set(_seed_names()) | set(_cached_names(user))
    out: list[ToolCapability] = []
    for name in sorted(names):
        cap = load_tool(user, name)
        if cap is not None:
            out.append(cap)
    out.sort(key=lambda c: c.vendor.lower())
    return out
