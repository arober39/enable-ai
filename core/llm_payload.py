"""Parse stringified lists that tool-use models sometimes return.

Tool calls are supposed to send JSON arrays. Models occasionally send the
same list as a string: fenced JSON, a Python literal, or a JSON array wrapped
in XML/parameter tags. `coerce_string_list` recovers a `list[str]` from those
shapes so one bad field does not have to reject the whole record. Callers
still apply their own length and item rules.
"""

from __future__ import annotations

import ast
import html
import json
import re
from typing import Any

# Tool-use JSON is untyped until we narrow it. `Any` stays on this boundary.
UNPARSED = object()

_FENCE_RE = re.compile(r"^\s*```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]*>")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_ ./+-]+$")


def strip_fence(text: str) -> str:
    """Remove one surrounding ``` / ```json fence."""
    stripped = text.strip()
    match = _FENCE_RE.match(stripped)
    if match is None:
        return stripped
    return match.group(1).strip()


def _strip_markup(text: str) -> str:
    """Drop HTML/XML tags and unescape entities around an embedded JSON value."""
    return _TAG_RE.sub(" ", html.unescape(text)).strip()


def text_candidates(text: str) -> list[str]:
    """The raw text, plus a copy with XML/parameter tags removed when they differ."""
    stripped = strip_fence(text)
    candidates = [stripped]
    messy = _strip_markup(stripped)
    if messy != stripped:
        candidates.append(messy)
    return candidates


def parse_structured(text: str) -> Any:
    """Parse JSON, including one layer of double-encoding, then a Python literal.

    Returns `UNPARSED` when `text` is not a structured value. JSON `null`
    returns None.
    """
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = UNPARSED
    else:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{\"'":
        return UNPARSED
    try:
        return ast.literal_eval(stripped)
    except (SyntaxError, ValueError, MemoryError):
        return UNPARSED


def extract_balanced(text: str, open_ch: str, close_ch: str) -> str | None:
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
    for candidate in text_candidates(text):
        parsed = parse_structured(candidate)
        if parsed is not UNPARSED:
            as_list = _string_list_from_parsed(parsed)
            if as_list is not None:
                return as_list
        array_text = extract_balanced(candidate, "[", "]")
        if array_text is None or array_text == candidate:
            continue
        parsed_array = parse_structured(array_text)
        if parsed_array is UNPARSED:
            continue
        as_list = _string_list_from_parsed(parsed_array)
        if as_list is not None:
            return as_list
    for candidate in text_candidates(text):
        tokens = _plain_tokens(candidate)
        if tokens is not None:
            return tokens
    return []


def coerce_string_list(value: Any) -> Any:
    """Coerce a stringified list into `list[str]`.

    Lists pass through unchanged. None and blank strings become []. A string
    is parsed as JSON (fences and XML/parameter tags stripped), then as a
    Python literal, then as a balanced `[...]` slice. Unreadable list-shaped
    text becomes [] so the caller can apply its own validation.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        if not value.strip():
            return []
        return _recover_string_list(value)
    return value
