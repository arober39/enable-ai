---
paths: ["**/*.py"]
---

# Python coding style

These rules apply to every `*.py` file in the repo.

## Formatting and lint

- Conform to PEP 8. Line length 100 (set in `pyproject.toml` under `[tool.ruff]`).
- Run `ruff check` clean before committing.
- Imports sorted by `ruff`'s `I` rule (isort).

## Typing

- **Type hints are required** on every function signature, including private ones.
- `mypy --strict` must pass on `coordinator/` and `enablement_agents/`.
- Prefer `X | None` over `Optional[X]`. Prefer `list[X]` over `List[X]`.
- Avoid `Any`; if you must use it, leave a one-line comment explaining why.

## I/O and async

- All I/O goes through `async`/`await`. Use `httpx.AsyncClient` for HTTP.
- Do not call blocking I/O from inside an `async` function. Wrap with `asyncio.to_thread` if you have no choice.

## Logging

- Never use `print()`. Use the project logger (`logging.getLogger(__name__)`).
- Log at `INFO` for lifecycle events, `DEBUG` for tool-call traces, `WARNING` for recoverable issues, `ERROR` for failures.
- No secrets, no full prompt bodies, no full LLM completions in logs at `INFO` or above.

## Data models

- All structured data — agent inputs, agent outputs, tool inputs, tool outputs, schemas — is defined as a `pydantic.BaseModel`.
- No bare `dict[str, Any]` for structured data crossing a boundary.
- Enums get a `Literal[...]` type, with `"unclear"` or `"other"` plus a free-text `detail` field where extensibility matters (per the architectural principles).

## Errors

- Raise typed exceptions, not strings. Define a small exception hierarchy per module where useful.
- At system boundaries (tool returns, MCP returns), produce a structured error object (`isError: true`, `errorCategory`, `isRetryable`, `message`) — see `@./mcp-server-conventions.md`.
