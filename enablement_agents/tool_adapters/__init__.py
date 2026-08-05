"""Tool adapters for the workflow interpreter.

Each adapter is reviewed Python — NOT LLM-authored. The interpreter
dispatches `(tool, action, params)` calls to the registered adapter for
that tool. Adapters receive the user's `Credentials` provider and
return a JSON-serializable dict.

Phase 2.1 ships stub adapters for the seed catalog (intercom, zendesk,
slack, hubspot) plus the special `llm`/`return`/`set` adapters. Real
MCP wiring lands one tool at a time in phase 2.2+.
"""
