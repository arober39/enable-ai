"""Natural-voice speech uses OpenAI only when a key is present."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from ui.api.server import app
from ui.api.speech import SpeechUnavailable, synthesize


class _Response:
    def __init__(self, status_code: int, content: bytes) -> None:
        self.status_code = status_code
        self.content = content


class _Client:
    def __init__(self) -> None:
        self.payload: dict | None = None
        self.headers: dict | None = None

    def post(self, url: str, headers: dict, json: dict) -> _Response:
        assert url.endswith("/audio/speech")
        self.headers = headers
        self.payload = json
        return _Response(200, b"mp3-bytes")


def test_synthesize_sends_a_conversational_voice() -> None:
    client = _Client()
    audio = synthesize("Route tickets faster.", "test-key", client=client)  # type: ignore[arg-type]
    assert audio == b"mp3-bytes"
    assert client.headers is not None
    assert client.headers["Authorization"] == "Bearer test-key"
    assert client.payload is not None
    assert client.payload["model"] == "gpt-4o-mini-tts"
    assert client.payload["voice"] == "coral"
    assert "instructions" not in client.payload
    assert client.payload["input"] == "Route tickets faster."


def test_synthesize_rejects_an_error_status() -> None:
    class _Fail:
        def post(self, url: str, headers: dict, json: dict) -> _Response:
            return _Response(401, b"")

    with pytest.raises(SpeechUnavailable, match="401"):
        synthesize("Hello.", "bad", client=_Fail())  # type: ignore[arg-type]


def test_speech_endpoint_without_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "ui.api.server.resolve_speech_key",
        lambda store: None,
    )
    response = TestClient(app).post("/api/speech", json={"text": "Hello."})
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_speech_endpoint_returns_mp3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ui.api.server.resolve_speech_key", lambda store: "k")
    monkeypatch.setattr("ui.api.server.synthesize", lambda text, key: b"audio")
    response = TestClient(app).post("/api/speech", json={"text": "Hello."})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"audio"


def test_synthesize_reports_http_errors() -> None:
    class _Boom:
        def post(self, url: str, headers: dict, json: dict) -> _Response:
            raise httpx.ConnectError("offline")

    with pytest.raises(SpeechUnavailable, match="offline"):
        synthesize("Hello.", "k", client=_Boom())  # type: ignore[arg-type]
