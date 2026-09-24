"""Natural speech for a plan, via OpenAI when a key is available."""

from __future__ import annotations

import os

import httpx

from core.credentials import CredentialStore

_SPEECH_URL = "https://api.openai.com/v1/audio/speech"
_MODEL = "gpt-4o-mini-tts"
_VOICE = "coral"
_MAX_CHARS = 4000


class SpeechUnavailable(Exception):
    """No speech key, or the speech service rejected the request."""


def resolve_speech_key(store: CredentialStore) -> str | None:
    """Vault key wins. The process environment is the local fallback."""
    vault = (store.get("OPENAI_API_KEY") or "").strip()
    if vault:
        return vault
    env = (os.environ.get("OPENAI_API_KEY") or "").strip()
    return env or None


def synthesize(text: str, api_key: str, client: httpx.Client | None = None) -> bytes:
    """Return MP3 bytes for `text`. Raises SpeechUnavailable on failure."""
    spoken = text.strip()
    if not spoken:
        raise SpeechUnavailable("nothing to read")
    if len(spoken) > _MAX_CHARS:
        raise SpeechUnavailable(f"text is longer than {_MAX_CHARS} characters")
    own_client = client is None
    http = client or httpx.Client(timeout=60.0)
    try:
        response = http.post(
            _SPEECH_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": _MODEL,
                "voice": _VOICE,
                "input": spoken,
                "response_format": "mp3",
            },
        )
    except httpx.HTTPError as exc:
        raise SpeechUnavailable(f"speech request failed: {exc}") from exc
    finally:
        if own_client:
            http.close()
    if response.status_code >= 400:
        raise SpeechUnavailable(f"speech service returned {response.status_code}")
    if not response.content:
        raise SpeechUnavailable("speech service returned empty audio")
    return response.content
