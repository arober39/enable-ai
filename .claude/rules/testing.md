---
paths: ["tests/**/*.py", "**/*.test.py"]
---

# Testing conventions

## Framework

- `pytest` is the test runner.
- `pytest-asyncio` is enabled with `asyncio_mode = "auto"` (see `pyproject.toml`). Async tests do not need an `@pytest.mark.asyncio` decorator.

## Deterministic tests are the default

The default test suite — what runs in `make test` — must be **fully deterministic**. That means:

- **No external API calls.** No HTTP, no SaaS APIs, no LaunchDarkly REST.
- **No live LLM calls.** No `anthropic.Anthropic().messages.create(...)`. Use stubs.
- **No network access.** Tests must pass with the machine offline.
- **No filesystem writes outside `tmp_path`.** Use pytest's `tmp_path` fixture for any test that needs to write.

The Phase 3 hooks (`enforce_credentials`, `enforce_writes`) provide a backstop, but the test code itself must not attempt these things in the first place.

## Live-LLM tests are gated

End-to-end tests that exercise a real LLM are marked with `@pytest.mark.live` and only run when `ANTHROPIC_API_KEY` is set in the environment.

```python
@pytest.mark.live
async def test_full_coordinator_flow():
    ...
```

`make test` excludes these. `make test-live` includes them. They cost money to run and are not required for any phase checkpoint to close.

## Fixtures over hardcoded data

Prefer pytest fixtures (or the Phase 2 data files in `data/support/`) over hardcoded inline values. If a test needs a sample support ticket, load it from `data/support/tickets.json` or define a fixture that does.

## Schema validation

When testing structured outputs, validate against the Pydantic model — do not assert on individual keys. A passing test must imply the output conforms to the schema, not just that one field happens to look right.
