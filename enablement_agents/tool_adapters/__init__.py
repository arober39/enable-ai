"""Tool adapters for the workflow interpreter.

Each adapter is reviewed Python — NOT LLM-authored. The interpreter
dispatches `(tool, action, params)` calls to the registered adapter for
that tool. Adapters receive the user's `Credentials` provider and
return a JSON-serializable dict.

Phase 2.1 ships adapters for the seed catalog (intercom, zendesk,
slack, hubspot) plus the special `llm`/`return`/`set` adapters.
Slack / HubSpot / Zendesk / Intercom call the real API when credentials
are present and return `mode: "stub"` otherwise. Stub-first adapters
(gainsight, gong, vitally, github) register so workflows can name those
tools without an unknown-tool error; they never report `mode: "real"`
until HTTP is implemented.
"""
