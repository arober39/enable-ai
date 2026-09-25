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

import ast
import html
import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.identity import UserContext
from core.state import repo_root, state_path

logger = logging.getLogger(__name__)

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
        description=(
            "low / medium / high / unknown — how much of the capability "
            "surface this feature covers"
        )
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

    @model_validator(mode="before")
    @classmethod
    def _normalize_stringified_lists(cls, data: Any) -> Any:
        """Parse tools_exposed when a model returns it as a JSON string."""
        if not isinstance(data, dict) or "tools_exposed" not in data:
            return data
        original = data["tools_exposed"]
        coerced = _coerce_string_list(original)
        if coerced is original:
            return data
        _log_normalization("mcp_server.tools_exposed", original)
        return {**data, "tools_exposed": coerced}


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

    @model_validator(mode="before")
    @classmethod
    def _normalize_stringified_fields(cls, data: Any) -> Any:
        """Repair tool-use payloads that stringify lists and nested objects.

        The JSON schema still requires real arrays. This only runs at parse
        time: a JSON string (or a string with markup after the JSON) becomes
        a list before field validation. A list string we cannot read becomes
        an empty list so one bad field does not reject the whole record.
        """
        if not isinstance(data, dict):
            return data
        updates: dict[str, Any] = {}
        for key in ("categories", "integration_patterns"):
            if key not in data:
                continue
            original = data[key]
            coerced = _coerce_string_list(original)
            if coerced is not original:
                _log_normalization(key, original)
                updates[key] = coerced
        if "native_ai_features" in data:
            original = data["native_ai_features"]
            coerced = _coerce_native_ai_features(original)
            if coerced is not original:
                _log_normalization("native_ai_features", original)
                updates["native_ai_features"] = coerced
        for key in ("api_surface", "mcp_server"):
            if key not in data:
                continue
            original = data[key]
            coerced = _coerce_json_object(original)
            if coerced is not original:
                _log_normalization(key, original)
                updates[key] = coerced
        if not updates:
            return data
        return {**data, **updates}


# ---------------------------------------------------------------------------
# LLM payload normalization
# ---------------------------------------------------------------------------

# Tool-use JSON is untyped until we narrow it. `Any` stays on this boundary.
_UNPARSED = object()

_FENCE_RE = re.compile(r"^\s*```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]*>")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_ ./+-]+$")


def _log_normalization(field: str, original: object) -> None:
    if original is None:
        logger.debug("tool capability: coerced null %s to an empty list", field)
        return
    logger.warning("tool capability: normalized %s from %s", field, type(original).__name__)


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    match = _FENCE_RE.match(stripped)
    if match is None:
        return stripped
    return match.group(1).strip()


def _strip_markup(text: str) -> str:
    """Drop HTML/XML tags and unescape entities around an embedded JSON value."""
    return _TAG_RE.sub(" ", html.unescape(text)).strip()


def _text_candidates(text: str) -> list[str]:
    stripped = _strip_fence(text)
    candidates = [stripped]
    messy = _strip_markup(stripped)
    if messy != stripped:
        candidates.append(messy)
    return candidates


def _parse_structured(text: str) -> Any:
    """Parse JSON, including one layer of double-encoding, then a Python literal.

    Returns `_UNPARSED` when `text` is not a structured value. JSON `null`
    returns None.
    """
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = _UNPARSED
    else:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{\"'":
        return _UNPARSED
    try:
        return ast.literal_eval(stripped)
    except (SyntaxError, ValueError, MemoryError):
        return _UNPARSED


def _extract_balanced(text: str, open_ch: str, close_ch: str) -> str | None:
    """Return the first balanced bracket/brace slice, respecting JSON strings."""
    start = text.find(open_ch)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == open_ch:
            depth += 1
        elif char == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _extract_json_objects(text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(text):
        start = text.find("{", cursor)
        if start < 0:
            break
        snippet = _extract_balanced(text[start:], "{", "}")
        if snippet is None:
            cursor = start + 1
            continue
        parsed = _parse_structured(snippet)
        if isinstance(parsed, dict):
            found.append(parsed)
            cursor = start + len(snippet)
        else:
            cursor = start + 1
    return found


def _plain_tokens(text: str) -> list[str] | None:
    """Split a comma-separated token list. Reject prose and markup."""
    stripped = text.strip()
    if not stripped:
        return None
    parts = [part.strip() for part in stripped.split(",") if part.strip()]
    if not parts or any(not _TOKEN_RE.fullmatch(part) for part in parts):
        return None
    return parts


def _strings_from_items(items: list[Any]) -> list[str]:
    values: list[str] = []
    for item in items:
        if isinstance(item, str):
            token = item.strip()
            if token:
                values.append(token)
    return values


def _string_list_from_parsed(parsed: Any) -> list[str] | None:
    if isinstance(parsed, list):
        return _strings_from_items(parsed)
    if isinstance(parsed, str):
        token = parsed.strip()
        return [token] if token else []
    return None


def _recover_string_list(text: str) -> list[str]:
    for candidate in _text_candidates(text):
        parsed = _parse_structured(candidate)
        if parsed is not _UNPARSED:
            as_list = _string_list_from_parsed(parsed)
            if as_list is not None:
                return as_list
        array_text = _extract_balanced(candidate, "[", "]")
        if array_text is None or array_text == candidate:
            continue
        parsed_array = _parse_structured(array_text)
        if parsed_array is _UNPARSED:
            continue
        as_list = _string_list_from_parsed(parsed_array)
        if as_list is not None:
            return as_list
    for candidate in _text_candidates(text):
        tokens = _plain_tokens(candidate)
        if tokens is not None:
            return tokens
    return []


def _coerce_string_list(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        if not value.strip():
            return []
        return _recover_string_list(value)
    return value


def _sanitize_feature(raw: dict[str, Any]) -> dict[str, Any] | None:
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    description = raw.get("description")
    maturity = raw.get("maturity")
    coverage = raw.get("coverage")
    cleaned = dict(raw)
    cleaned["name"] = name.strip()
    cleaned["description"] = description.strip() if isinstance(description, str) else ""
    if isinstance(maturity, str) and maturity.strip():
        cleaned["maturity"] = maturity.strip()
    else:
        cleaned["maturity"] = "unknown"
    if isinstance(coverage, str) and coverage.strip():
        cleaned["coverage"] = coverage.strip()
    else:
        cleaned["coverage"] = "unknown"
    return cleaned


def _clean_feature_items(items: list[Any]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            parsed = _parse_structured(_strip_fence(item))
            if isinstance(parsed, dict):
                feature = _sanitize_feature(parsed)
                if feature is not None:
                    cleaned.append(feature)
                continue
            for obj in _extract_json_objects(item):
                feature = _sanitize_feature(obj)
                if feature is not None:
                    cleaned.append(feature)
                    break
            continue
        if isinstance(item, dict):
            feature = _sanitize_feature(item)
            if feature is not None:
                cleaned.append(feature)
    return cleaned


def _features_from_parsed(parsed: Any) -> list[dict[str, Any]] | None:
    if isinstance(parsed, list):
        return _clean_feature_items(parsed)
    if isinstance(parsed, dict):
        nested = parsed.get("native_ai_features")
        if isinstance(nested, list):
            return _clean_feature_items(nested)
        if isinstance(nested, str):
            return None
        feature = _sanitize_feature(parsed)
        if feature is not None:
            return [feature]
    return None


def _recover_features(text: str) -> list[dict[str, Any]]:
    for candidate in _text_candidates(text):
        parsed = _parse_structured(candidate)
        if parsed is not _UNPARSED:
            features = _features_from_parsed(parsed)
            if features is not None:
                return features
        array_text = _extract_balanced(candidate, "[", "]")
        if array_text is not None and array_text != candidate:
            parsed_array = _parse_structured(array_text)
            if parsed_array is not _UNPARSED:
                features = _features_from_parsed(parsed_array)
                if features is not None:
                    return features
        objects = _extract_json_objects(candidate)
        if objects:
            cleaned = _clean_feature_items(objects)
            if cleaned:
                return cleaned
    return []


def _coerce_native_ai_features(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, list):
        if not any(isinstance(item, str) for item in value):
            return value
        return _clean_feature_items(value)
    if isinstance(value, dict):
        feature = _sanitize_feature(value)
        return [feature] if feature is not None else []
    if isinstance(value, str):
        if not value.strip():
            return []
        return _recover_features(value)
    return value


def _coerce_json_object(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    for candidate in _text_candidates(value):
        parsed = _parse_structured(candidate)
        if isinstance(parsed, dict):
            return parsed
        extracted = _extract_balanced(candidate, "{", "}")
        if extracted is None or extracted == candidate:
            continue
        parsed_obj = _parse_structured(extracted)
        if isinstance(parsed_obj, dict):
            return parsed_obj
    return value


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


def list_researched_tools(user: UserContext) -> list[ToolCapability]:
    """Return only this user's researched tools, sorted by vendor.

    Seed files stay on disk for the factory. The picker does not list them.
    """
    out: list[ToolCapability] = []
    for name in _cached_names(user):
        cap = _load_cached(user, name)
        if cap is not None:
            out.append(cap)
    out.sort(key=lambda c: c.vendor.lower())
    return out


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
