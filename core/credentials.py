"""Credential providers — read-only access for runtime, full CRUD for management.

Locked phase 1 commitments:
- #1: Orchestrators must never read `os.environ` directly for credentials.
  They go through a `Credentials` provider. Phase 1 backs it with
  `EnvCredentials` (the spawner populates env vars from the store); phase 2
  swaps in an encrypted per-user backend without touching call sites.
- #4: The UI must never write directly to `.env`. It writes to a
  `CredentialStore` (a per-user JSON file in phase 1; an encrypted DB
  later). At orchestrator spawn time, the API reads the store and
  injects env vars into the subprocess.

Two interfaces:
- `Credentials` — read-only. What the orchestrator runtime uses.
- `CredentialStore` — full CRUD. What the UI uses to manage stored creds.

Two phase-1 implementations:
- `EnvCredentials` (read-only over `os.environ`) — for the orchestrator
  subprocess. The spawner is responsible for populating env.
- `LocalFileCredentialStore` — for the UI Settings page. Per-user JSON
  file under `agent-state/<user_id>/credentials.json`.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from core.identity import UserContext
from core.state import state_path

_CREDENTIALS_FILE = "credentials.json"


class Credentials(ABC):
    """Read-only credential access for runtime code (orchestrators)."""

    @abstractmethod
    def get(self, key: str) -> str | None:
        """Return the credential value, or None if unset."""

    def require(self, key: str) -> str:
        """Like get() but raises if the credential is missing."""
        value = self.get(key)
        if value is None:
            raise KeyError(f"required credential is not set: {key}")
        return value


class CredentialStore(Credentials):
    """Management interface — full CRUD. Used by the UI Settings page."""

    @abstractmethod
    def set(self, key: str, value: str) -> None:
        """Set or overwrite a credential value."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a credential. No-op if the key doesn't exist."""

    @abstractmethod
    def list_keys(self) -> list[str]:
        """Return all credential keys stored (sorted). Values are not returned."""

    @abstractmethod
    def export_env(self, keys: list[str] | None = None) -> dict[str, str]:
        """Return a {key: value} dict suitable for passing as `env=` to subprocess.

        If `keys` is None, returns all stored credentials. The spawner uses
        this to populate the orchestrator subprocess env without ever
        writing the values to disk in a separate location.
        """


class EnvCredentials(Credentials):
    """Read credentials from `os.environ`. Used by orchestrator runtime.

    The orchestrator subprocess is spawned with env vars populated by the
    UI's run-orchestrator endpoint (from `CredentialStore.export_env()`).
    From the orchestrator's view, credentials look like env vars, but the
    abstraction means future backends (Vault, AWS Secrets Manager, etc.)
    can replace this without touching orchestrator code.
    """

    def get(self, key: str) -> str | None:
        return os.environ.get(key)


class LocalFileCredentialStore(CredentialStore):
    """Per-user JSON-backed credential store.

    File layout: `agent-state/<user_id>/credentials.json` containing a
    flat `{key: value}` object. Values are stored in plaintext — this is
    a single-user-local phase 1 implementation. Phase 2+ swaps in an
    encrypted backend with the same interface.

    Thread-safe-enough for the single-user-local case: every operation
    reads the file, mutates in memory, writes it back atomically (write
    to temp + rename). Not safe under multi-process concurrent writes;
    if/when that matters, swap the backend.
    """

    def __init__(self, user: UserContext) -> None:
        self._path: Path = state_path(user, _CREDENTIALS_FILE)

    @property
    def path(self) -> Path:
        """The on-disk file backing this store. Exposed for debugging/tests."""
        return self._path

    def get(self, key: str) -> str | None:
        return self._read().get(key)

    def set(self, key: str, value: str) -> None:
        data = self._read()
        data[key] = value
        self._write(data)

    def delete(self, key: str) -> None:
        data = self._read()
        if key in data:
            del data[key]
            self._write(data)

    def list_keys(self) -> list[str]:
        return sorted(self._read().keys())

    def export_env(self, keys: list[str] | None = None) -> dict[str, str]:
        data = self._read()
        if keys is None:
            return dict(data)
        return {k: data[k] for k in keys if k in data}

    def _read(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        raw = self._path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError(
                f"credentials store at {self._path} is not a JSON object"
            )
        # Coerce to str/str — JSON allows nulls and numbers; we don't.
        return {str(k): str(v) for k, v in parsed.items()}

    def _write(self, data: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self._path)


def runtime_credentials() -> Credentials:
    """Factory: the credential provider an orchestrator should use at runtime.

    Returns an `EnvCredentials` backed by `os.environ`. The spawner (UI
    `/api/run-orchestrator`) is responsible for populating env vars from
    the user's `CredentialStore` before invoking the orchestrator.
    """
    return EnvCredentials()


@contextmanager
def credentials_in_env(
    store: CredentialStore,
    keys: list[str] | None = None,
) -> Iterator[None]:
    """Temporarily inject credentials from `store` into `os.environ`.

    Phase 1 single-user-local: the UI calls the orchestrator in-process,
    and this context manager bridges the gap between the JSON-backed
    store and the orchestrator's `EnvCredentials`. Snapshots any
    existing values and restores them on exit so requests don't leak
    state into each other.

    Phase 2 multi-user-hosted: this context manager is replaced at the
    call site by `subprocess.Popen(env=store.export_env(keys))`. The
    orchestrator code itself does not change — it still reads via
    `EnvCredentials`. Only the spawn boundary swaps.
    """
    overrides = store.export_env(keys)
    saved: dict[str, str | None] = {k: os.environ.get(k) for k in overrides}
    try:
        os.environ.update(overrides)
        yield
    finally:
        for k, original in saved.items():
            if original is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = original
