"""Bots remembered from copy-paste Grok Bot handoffs.

The handoff does not create bots. It does remember the bot each successful
handoff named, so a later handoff in the same process can ask Jev to add
work to that bot when the Grok Bot gateway is unset.

File: `agent-state/<user_id>/grokbot_roster.json`. Same per-user layout
as workflows and credentials. One row per bot name. Repeating a
recommendation that was handed off as a new bot updates that row.

The API server deletes every user's roster file on startup. A fresh
process starts with an empty remembered list.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.identity import UserContext
from core.state import repo_root, state_path

logger = logging.getLogger(__name__)

_ROSTER_FILE = "grokbot_roster.json"
#: Newest rows win once the file reaches this size.
_ROSTER_LIMIT = 40

RosterAction = Literal["create", "update", "create_fallback"]
_NEW_BOT_ACTIONS = frozenset({"create", "create_fallback"})


class RememberedBot(BaseModel):
    """One bot named by a previous step-7 handoff."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    title: str = ""
    description: str = ""
    role_name: str = ""
    role_id: str | None = None
    recommendation_id: str = Field(min_length=1)
    action: RosterAction
    remembered_at: datetime


def local_bot_id(name: str) -> str:
    """Stable id for a bot that exists only in handoff memory."""
    normalized = normalized_bot_name(name)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return f"local:{slug or 'bot'}"


def normalized_bot_name(name: str) -> str:
    """Compare bot names without case or extra whitespace."""
    return " ".join(name.strip().lower().split())


def _path_for(user: UserContext) -> Path:
    return state_path(user, _ROSTER_FILE)


def _read(user: UserContext) -> list[RememberedBot]:
    path = _path_for(user)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "[]")
    except json.JSONDecodeError:
        logger.warning("grokbot roster file is not valid JSON; ignoring it")
        return []
    if not isinstance(raw, list):
        logger.warning("grokbot roster file is not a list; ignoring it")
        return []
    bots: list[RememberedBot] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            bots.append(RememberedBot.model_validate(item))
        except Exception:  # noqa: BLE001 — skip one bad row, keep the rest
            logger.warning("skipping malformed grokbot roster entry")
            continue
    return bots


@contextmanager
def _exclusive(user: UserContext) -> Iterator[None]:
    """One writer at a time. Two step-7 fetches must not share a temp file."""
    path = _path_for(user)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write(user: UserContext, bots: list[RememberedBot]) -> None:
    path = _path_for(user)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [bot.model_dump(mode="json") for bot in bots]
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def clear_remembered_rosters(root: Path | None = None) -> int:
    """Delete remembered Grok Bot rosters so a new process starts empty.

    `root` is the agent-state directory (default: `<repo>/agent-state`).
    Every `*/grokbot_roster.json` under it is removed, including the local
    single-user file and any other user directory. Other files in those
    directories are left in place. Returns how many roster files were deleted.
    """
    base = repo_root() / "agent-state" if root is None else root
    if not base.is_dir():
        return 0
    removed = 0
    for path in base.glob(f"*/{_ROSTER_FILE}"):
        if not path.is_file():
            continue
        path.unlink()
        removed += 1
        logger.info("cleared grokbot roster at %s", path)
    return removed


def load_remembered_bots(user: UserContext) -> list[RememberedBot]:
    """Remembered bots, newest handoff first."""
    return sorted(_read(user), key=lambda bot: bot.remembered_at, reverse=True)


def _dedupe_names(bots: list[RememberedBot]) -> list[RememberedBot]:
    best: dict[str, RememberedBot] = {}
    order: list[str] = []
    for bot in bots:
        key = normalized_bot_name(bot.name)
        if key not in best:
            order.append(key)
            best[key] = bot
            continue
        if bot.remembered_at >= best[key].remembered_at:
            best[key] = bot
    return [best[key] for key in order]


def _cap(bots: list[RememberedBot]) -> list[RememberedBot]:
    # Later rows win when two timestamps are equal, so a burst of writes
    # drops the oldest entries rather than the ones just appended.
    indexed = list(enumerate(bots))
    newest = sorted(
        indexed,
        key=lambda pair: (pair[1].remembered_at, pair[0]),
        reverse=True,
    )[:_ROSTER_LIMIT]
    kept = [bot for _index, bot in newest]
    return sorted(kept, key=lambda bot: bot.remembered_at)


def remember_bot(user: UserContext, bot: RememberedBot) -> list[RememberedBot]:
    """Insert or update one remembered bot. Returns the stored roster, newest first."""
    display = bot.name.strip()
    stored = bot.model_copy(update={"id": local_bot_id(display), "name": display})
    with _exclusive(user):
        items = _read(user)
        name_key = normalized_bot_name(display)
        name_idx = next(
            (i for i, item in enumerate(items) if normalized_bot_name(item.name) == name_key),
            None,
        )
        rec_idx = next(
            (
                i
                for i, item in enumerate(items)
                if item.recommendation_id == stored.recommendation_id
            ),
            None,
        )
        if name_idx is not None:
            items[name_idx] = stored
        elif (
            rec_idx is not None
            and items[rec_idx].action in _NEW_BOT_ACTIONS
            and stored.action in _NEW_BOT_ACTIONS
        ):
            # Same recommendation handed off again as a new bot (role rename included).
            items[rec_idx] = stored
        else:
            items.append(stored)
        _write(user, _cap(_dedupe_names(items)))
    logger.info(
        "remembered grokbot handoff bot=%s recommendation=%s action=%s",
        stored.name,
        stored.recommendation_id,
        stored.action,
    )
    return load_remembered_bots(user)
