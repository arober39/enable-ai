---
paths: ["**/*.py"]
---

# Observability

## OpenTelemetry instrumentation

All non-trivial code paths produce OTel spans via `opentelemetry-sdk`. Use `openinference-instrumentation` semantic conventions where they apply (LLM calls, tool calls).

## What to instrument

At minimum:

- **LLM calls** — model name, prompt size, completion size, latency, stop reason, cache hits.
- **Tool calls** — tool name, input shape, output shape, isError flag, latency.
- **Decision points** — the Coordinator's routing decision (which subagent), the agent's classification (intent, capability finding, recommendation kind).
- **Orchestrator runtime steps** — intent classification → knowledge base search → response drafting → final output (per Phase 5.2).

## Span naming

- Format: `<component>.<action>` — `coordinator.route_request`, `support_agent.produce_plan`, `support_orchestrator.classify_intent`.
- Kebab is allowed for sub-actions: `support_orchestrator.knowledge_base.search`.
- Avoid PII in span names. Customer IDs and ticket IDs go in span **attributes**, not names.

## Resource attributes

Every span sets `service.name` from `OTEL_SERVICE_NAME` (default `enable-ai`). Per-component services override with their own name (`service.name=support-orchestrator` for runtime spans emitted from the generated orchestrator).

## Exporter

If `OTEL_EXPORTER_ENDPOINT` is set, configure the OTLP exporter to that URL. If unset, fall back to the no-op exporter — instrumentation must not crash the app when there's nowhere to send traces.

## What NOT to log in spans

- Full prompt bodies (size-only is fine)
- Full completion bodies
- API keys, tokens, customer PII (email, name, etc.)
