"""LLM-driven orchestrator generator (Phase 1.4).

Replaces the static template-based generator in
`enablement_agents/support/_orchestrator_generator.py`. Given a selected
recommendation, the user's tool stack, and their role, this package
produces a single-file orchestrator (`orchestrator.py`) under
`orchestrators/<user_id>/<role>/` that implements that specific
recommendation against those specific tools.

Four stages:
  1. research — enrich each selected tool's catalog data with the
     specific endpoints / MCP tools this recommendation needs
  2. plan    — propose the code structure: entry function, helpers,
     env vars consumed
  3. generate — produce the actual Python source as a single string
  4. verify  — write the file, import-check it, confirm `handle_request`
     exists and is async

The pipeline is fully sequential — each stage feeds the next. The
result includes per-stage timings + outputs so the UI can show the user
where their tokens went.
"""
