"""Grok Bot handoff webhook: payload shape, skip when unset, post when set."""

from __future__ import annotations

import json

import httpx
import pytest

from core.grokbot import WEBHOOK_KEY_ENV, WEBHOOK_URL_ENV, HandoffCredentials
from core.grokbot_webhook import (
    WEBHOOK_FAILED,
    WEBHOOK_SENT,
    WEBHOOK_TIMEOUT_SECONDS,
    GrokbotWebhookPayload,
    _client,
    build_webhook_payload,
    deliver_handoff_webhook,
)


class _Creds:
    def __init__(self, data: dict[str, str]) -> None:
        self._d = data

    def get(self, key: str) -> str | None:
        return self._d.get(key)


@pytest.fixture(autouse=True)
def _isolate_webhook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not read a developer `.env` or a live webhook during tests."""
    monkeypatch.delenv(WEBHOOK_URL_ENV, raising=False)
    monkeypatch.delenv(WEBHOOK_KEY_ENV, raising=False)
    monkeypatch.setattr("core.grokbot._file_env", lambda: {})


def _args(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Developer Relations",
        "title": "Developer Relations",
        "description": (
            "Jev did not choose a bot.\n\n"
            "You are the Developer Relations bot.\n\n"
            "Tools you should use: discord, google_docs"
        ),
        "placement": "Jev did not choose a bot.",
        "action": "create_fallback",
        "recommendation_id": "R-003",
        "role_name": "Developer Relations",
        "role_id": "devrel",
        "tools": ["discord", "google_docs"],
        "existing_bot_name": None,
    }
    payload.update(overrides)
    return payload


def _deliver(creds: object, **overrides: object):
    return deliver_handoff_webhook(creds, **_args(**overrides))  # type: ignore[arg-type]


def _capture(
    monkeypatch: pytest.MonkeyPatch,
    handler,
) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(wrapped))

    monkeypatch.setattr("core.grokbot_webhook._client", factory)
    return seen


def test_payload_shape_includes_the_copyable_assignment() -> None:
    payload = build_webhook_payload(**_args())  # type: ignore[arg-type]
    dumped = payload.model_dump(mode="json")
    parsed = GrokbotWebhookPayload.model_validate(dumped)
    assert set(dumped) == set(GrokbotWebhookPayload.model_fields)
    assert parsed.source == "enable-ai"
    assert parsed.bot_name == parsed.name == "Developer Relations"
    assert parsed.title == "Developer Relations"
    assert parsed.description.startswith("Jev did not choose a bot.")
    assert "Tools you should use: discord, google_docs" in parsed.description
    assert parsed.placement == "Jev did not choose a bot."
    assert parsed.action == "create_fallback"
    assert parsed.recommendation_id == "R-003"
    assert parsed.role_name == "Developer Relations"
    assert parsed.role_id == "devrel"
    assert parsed.tools == ["discord", "google_docs"]
    assert parsed.existing_bot_name is None


def test_payload_includes_role_and_existing_bot_when_present() -> None:
    payload = build_webhook_payload(
        **_args(action="update", existing_bot_name="Developer Relations")  # type: ignore[arg-type]
    )
    parsed = GrokbotWebhookPayload.model_validate(payload.model_dump(mode="json"))
    assert parsed.action == "update"
    assert parsed.existing_bot_name == "Developer Relations"
    assert parsed.role_id == "devrel"


def test_payload_omits_blank_role_id_and_existing_bot_as_null() -> None:
    payload = build_webhook_payload(
        **_args(role_id="  ", existing_bot_name="")  # type: ignore[arg-type]
    )
    parsed = GrokbotWebhookPayload.model_validate(payload.model_dump(mode="json"))
    assert parsed.role_id is None
    assert parsed.existing_bot_name is None


def test_skips_when_env_unset_and_does_not_open_a_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def factory() -> httpx.Client:
        raise AssertionError("webhook client should not be opened")

    monkeypatch.setattr("core.grokbot_webhook._client", factory)
    result = _deliver(None)
    parsed = type(result).model_validate(result.model_dump())
    assert parsed.status == "skipped"
    assert parsed.message is None


def test_skips_when_only_one_setting_is_present(monkeypatch: pytest.MonkeyPatch) -> None:
    def factory() -> httpx.Client:
        raise AssertionError("webhook client should not be opened")

    monkeypatch.setattr("core.grokbot_webhook._client", factory)
    url_only = _deliver(_Creds({WEBHOOK_URL_ENV: "https://hooks.example/grok"}))
    key_only = _deliver(_Creds({WEBHOOK_KEY_ENV: "sender-key"}))
    blank = _deliver(
        _Creds({WEBHOOK_URL_ENV: "  ", WEBHOOK_KEY_ENV: "sender-key"}),
    )
    assert url_only.status == key_only.status == blank.status == "skipped"
    assert url_only.message is None


def test_posts_when_credentials_are_set(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture(
        monkeypatch,
        lambda _request: httpx.Response(204),
    )
    result = _deliver(
        _Creds(
            {
                WEBHOOK_URL_ENV: "https://hooks.example/grok",
                WEBHOOK_KEY_ENV: "sender-key",
            }
        )
    )
    assert result.status == "sent"
    assert result.message == WEBHOOK_SENT
    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == "https://hooks.example/grok"
    assert request.headers["authorization"] == "Bearer sender-key"
    assert request.headers["content-type"].startswith("application/json")
    body = json.loads(request.content)
    parsed = GrokbotWebhookPayload.model_validate(body)
    assert parsed.source == "enable-ai"
    assert parsed.bot_name == "Developer Relations"
    assert parsed.name == "Developer Relations"
    assert parsed.recommendation_id == "R-003"
    assert parsed.role_id == "devrel"
    assert parsed.tools == ["discord", "google_docs"]
    assert "sender-key" not in request.content.decode()


def test_posts_when_process_env_is_set_and_creds_are_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(WEBHOOK_URL_ENV, "https://hooks.example/from-env")
    monkeypatch.setenv(WEBHOOK_KEY_ENV, "env-key")
    seen = _capture(monkeypatch, lambda _request: httpx.Response(200, json={"ok": True}))
    result = _deliver(None)
    assert result.status == "sent"
    assert str(seen[0].url) == "https://hooks.example/from-env"
    assert seen[0].headers["authorization"] == "Bearer env-key"


def test_posts_when_dotenv_file_is_set_and_creds_are_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "core.grokbot._file_env",
        lambda: {
            WEBHOOK_URL_ENV: "https://hooks.example/from-file",
            WEBHOOK_KEY_ENV: "file-key",
        },
    )
    seen = _capture(monkeypatch, lambda _request: httpx.Response(200, json={"ok": True}))
    result = _deliver(None)
    assert result.status == "sent"
    assert str(seen[0].url) == "https://hooks.example/from-file"
    assert seen[0].headers["authorization"] == "Bearer file-key"


def test_webhook_settings_are_not_read_from_the_credential_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "core.grokbot._file_env",
        lambda: {
            WEBHOOK_URL_ENV: "https://hooks.example/from-file",
            WEBHOOK_KEY_ENV: "file-key",
        },
    )
    creds = HandoffCredentials(
        _Creds(
            {
                WEBHOOK_URL_ENV: "https://hooks.example/settings",
                WEBHOOK_KEY_ENV: "settings-key",
            }
        )
    )
    assert creds.get(WEBHOOK_URL_ENV) == "https://hooks.example/from-file"
    assert creds.get(WEBHOOK_KEY_ENV) == "file-key"
    monkeypatch.setattr("core.grokbot._file_env", lambda: {})
    assert creds.get(WEBHOOK_URL_ENV) is None
    assert creds.get(WEBHOOK_KEY_ENV) is None


def test_http_error_is_non_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture(monkeypatch, lambda _request: httpx.Response(502, text="bad gateway"))
    result = _deliver(
        _Creds(
            {
                WEBHOOK_URL_ENV: "https://hooks.example/grok",
                WEBHOOK_KEY_ENV: "sender-key",
            }
        )
    )
    assert result.status == "failed"
    assert result.message == WEBHOOK_FAILED


def test_timeout_is_non_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    _capture(monkeypatch, handler)
    result = _deliver(
        _Creds(
            {
                WEBHOOK_URL_ENV: "https://hooks.example/grok",
                WEBHOOK_KEY_ENV: "sender-key",
            }
        )
    )
    assert result.status == "failed"
    assert result.message == WEBHOOK_FAILED


def test_redirect_is_not_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture(
        monkeypatch,
        lambda _request: httpx.Response(
            302,
            headers={"location": "https://evil.example/steal"},
        ),
    )
    result = _deliver(
        _Creds(
            {
                WEBHOOK_URL_ENV: "https://hooks.example/grok",
                WEBHOOK_KEY_ENV: "sender-key",
            }
        )
    )
    assert result.status == "failed"
    assert result.message == WEBHOOK_FAILED
    assert len(seen) == 1
    assert seen[0].url.host == "hooks.example"


def test_unusable_url_does_not_open_a_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def factory() -> httpx.Client:
        raise AssertionError("webhook client should not be opened")

    monkeypatch.setattr("core.grokbot_webhook._client", factory)
    result = _deliver(
        _Creds({WEBHOOK_URL_ENV: "not a url", WEBHOOK_KEY_ENV: "sender-key"})
    )
    assert result.status == "failed"
    assert result.message == WEBHOOK_FAILED


def test_webhook_client_uses_a_short_timeout() -> None:
    client = _client()
    try:
        timeout = client.timeout
        assert timeout.connect == WEBHOOK_TIMEOUT_SECONDS
        assert timeout.read == WEBHOOK_TIMEOUT_SECONDS
        assert timeout.write == WEBHOOK_TIMEOUT_SECONDS
        assert timeout.pool == WEBHOOK_TIMEOUT_SECONDS
        assert WEBHOOK_TIMEOUT_SECONDS <= 10
    finally:
        client.close()
