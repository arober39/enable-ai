---
paths: ["orchestrators/**/mcp_servers/**/*.py", "mcp_registry/**/*.yaml"]
---

# MCP server conventions

These rules apply to MCP server code generated under `orchestrators/<department>/mcp_servers/` and to the MCP registry YAML files.

## Tool descriptions

Every MCP tool exposed to an agent must have a description that explicitly states:

1. **What it does** — one sentence.
2. **Input format** — referenced via a strict JSON Schema (`input_schema`).
3. **Expected output** — what the agent should expect on success, including the shape.
4. **Edge cases** — what happens when the input is malformed, the resource is missing, or the upstream service is down.
5. **When to use vs. when not to** — disambiguate from similar tools (e.g. `search_conversations` vs. `get_conversation`).

A tool description that is just "Gets the conversation." is incomplete. Reject it in code review.

## Structured `isError` responses

When an MCP tool fails, it must return a structured error object — never a free-text string. The schema:

```json
{
  "isError": true,
  "errorCategory": "permission" | "not_found" | "rate_limit" | "upstream_unavailable" | "validation" | "internal",
  "isRetryable": true | false,
  "message": "Human-readable summary",
  "partial_results": <optional, tool-specific>
}
```

The `normalize_responses` PostToolUse hook in the Coordinator wraps any MCP error that doesn't conform.

## JSON Schema requirements

- `input_schema` is required on every tool.
- Use `additionalProperties: false` to catch hallucinated keys.
- Use enums or `Literal[...]` for closed sets.
- Mark every required field in the `required` array — do not rely on defaults to communicate requiredness.

## Registry YAML files

`mcp_registry/<tool>.yaml` files declare whether an MCP server is available for a given tool. If `available: false`, the orchestrator generates a custom MCP server stub. If `available: true`, the orchestrator references the existing server via `.mcp.json` and does not generate a duplicate.
