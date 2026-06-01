"""OpenTelemetry setup for the Support Orchestrator runtime.

Per .claude/rules/observability.md, the runtime emits spans for:
  - support_orchestrator.handle_inquiry           (root span per request)
  - support_orchestrator.fetch_ai_config          (LD AI Config fetch)
  - support_orchestrator.classify_intent          (intent classification)
  - support_orchestrator.knowledge_base.search    (FAQ-class)
  - support_orchestrator.draft_response           (refund-class)
  - support_orchestrator.build_handoff            (escalation-class)
  - support_orchestrator.emit_events              (track support.escalation / support.error)

The OTLP exporter is enabled when OTEL_EXPORTER_ENDPOINT is set; otherwise
the SDK runs with a no-op exporter so missing observability never crashes
the runtime.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

logger = logging.getLogger(__name__)


_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "support-orchestrator")


def _build_provider() -> TracerProvider:
    """Configure a TracerProvider, optionally with an OTLP exporter."""
    resource = Resource.create({"service.name": _SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    # Tests and other unattended contexts can suppress all console output
    # by setting OTEL_DISABLE_CONSOLE=true. Spans still record internally;
    # they just don't get printed.
    disable_console = os.environ.get(
        "OTEL_DISABLE_CONSOLE", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}

    endpoint = os.environ.get("OTEL_EXPORTER_ENDPOINT")
    if disable_console and not endpoint:
        return provider

    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
                OTLPSpanExporter,
            )

            exporter: Any = OTLPSpanExporter(endpoint=endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OTel exporter configured: endpoint=%s", endpoint)
        except ImportError:
            logger.warning(
                "OTEL_EXPORTER_ENDPOINT is set but opentelemetry-exporter-otlp "
                "is not installed. Spans will print to stderr only."
            )
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter(out=sys.stderr)))
    elif os.environ.get("ENABLE_AI_DEMO_MODE", "true").lower() in {"1", "true", "yes", "on"}:
        # Demo mode with no exporter — keep spans available but silent on
        # stdout so structured orchestrator output is clean. Routing to
        # stderr keeps them visible without contaminating piped output.
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter(out=sys.stderr)))
    else:
        # No exporter configured outside demo mode — emit to stderr.
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter(out=sys.stderr)))

    return provider


_provider = _build_provider()
trace.set_tracer_provider(_provider)
tracer = trace.get_tracer(_SERVICE_NAME)


# Canonical span names emitted by this runtime. Listed here so tests can
# assert on the contract from Phase 5.2.
EXPECTED_SPAN_NAMES = (
    "support_orchestrator.handle_inquiry",
    "support_orchestrator.fetch_ai_config",
    "support_orchestrator.classify_intent",
    "support_orchestrator.knowledge_base.search",
    "support_orchestrator.draft_response",
    "support_orchestrator.build_handoff",
    "support_orchestrator.emit_events",
)


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    """Start a span with attributes; yields the span for further attribute setting."""
    with tracer.start_as_current_span(name) as s:
        for key, value in attributes.items():
            s.set_attribute(key, value)
        yield s
