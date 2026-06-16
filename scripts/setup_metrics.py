"""Provision the LaunchDarkly custom metrics for the multi-signal guardrails tutorial.

Creates two metrics on the configured LD project:

  - support.errors.count       — tracks the `support.error` event
  - support.escalation_rate    — tracks the `support.escalation` event

Both are event-kind, lower-is-better, randomized on `request` context.

Idempotent: if a metric already exists, the script logs and continues.

Demo mode (`ENABLE_AI_DEMO_MODE=true`, the default) and the explicit
`--dry-run` flag both suppress real API calls — the script prints what it
*would* do instead. This is how the Phase 6 checkpoint exercises the
script without burning API quota.

Reads:
  - LAUNCHDARKLY_API_KEY        (required for real-mode)
  - LAUNCHDARKLY_PROJECT_KEY    (required)
  - ENABLE_AI_DEMO_MODE         (optional; default true)

Exit codes:
  0  success (or demo-mode dry run)
  1  validation error
  2  upstream LD API error
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass

import httpx

logger = logging.getLogger("setup_metrics")

_LD_API_BASE = "https://app.launchdarkly.com/api/v2"


@dataclass(frozen=True)
class MetricSpec:
    """One LaunchDarkly metric the tutorial requires."""

    key: str
    name: str
    description: str
    event_key: str


_METRICS: list[MetricSpec] = [
    MetricSpec(
        key="support.errors.count",
        name="Support: error count",
        description=(
            "Count of errors emitted by the support orchestrator's request handler. "
            "Lower-is-better. Tracked by the `support.error` event."
        ),
        event_key="support.error",
    ),
    MetricSpec(
        key="support.escalation_rate",
        name="Support: escalation rate",
        description=(
            "Rate of inquiries the support orchestrator escalated to a human team lead. "
            "Lower-is-better. Tracked by the `support.escalation` event."
        ),
        event_key="support.escalation",
    ),
]


def _demo_mode() -> bool:
    return os.environ.get("ENABLE_AI_DEMO_MODE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _metric_payload(spec: MetricSpec) -> dict[str, object]:
    """Build the REST API payload for a single metric.

    Matches the documented shape for LaunchDarkly event-kind metrics:
    https://launchdarkly.com/docs/home/observability/metrics
    """
    return {
        "key": spec.key,
        "name": spec.name,
        "description": spec.description,
        "kind": "custom",
        "eventKey": spec.event_key,
        "isNumeric": True,
        "unit": "events",
        "successCriteria": "LowerThanBaseline",
        "randomizationUnits": ["request"],
    }


def _api_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": api_key,
        "Content-Type": "application/json",
        "LD-API-Version": "beta",
    }


def _metric_exists(
    client: httpx.Client, project_key: str, metric_key: str, api_key: str
) -> bool:
    """Return True if the metric is already provisioned in the project."""
    resp = client.get(
        f"{_LD_API_BASE}/metrics/{project_key}/{metric_key}",
        headers=_api_headers(api_key),
    )
    if resp.status_code == 404:
        return False
    if resp.status_code == 200:
        return True
    raise RuntimeError(
        f"Unexpected status {resp.status_code} checking metric '{metric_key}': "
        f"{resp.text[:300]}"
    )


def _create_metric(
    client: httpx.Client, project_key: str, spec: MetricSpec, api_key: str
) -> None:
    """Create one metric. Raises on non-success."""
    payload = _metric_payload(spec)
    resp = client.post(
        f"{_LD_API_BASE}/metrics/{project_key}",
        headers=_api_headers(api_key),
        json=payload,
    )
    if resp.status_code in (200, 201):
        return
    raise RuntimeError(
        f"Failed to create metric '{spec.key}': status={resp.status_code} "
        f"body={resp.text[:500]}"
    )


def _print_would_do(spec: MetricSpec, project_key: str) -> None:
    payload = _metric_payload(spec)
    logger.info(
        "WOULD provision metric on project=%s: %s",
        project_key,
        json.dumps(payload, indent=2),
    )


def run(*, dry_run: bool) -> int:
    """Provision the two metrics. Return exit code."""
    project_key = os.environ.get("LAUNCHDARKLY_PROJECT_KEY", "").strip()
    if not project_key:
        logger.error(
            "LAUNCHDARKLY_PROJECT_KEY is not set. Add it to your .env (see "
            "root .env.example) and re-run."
        )
        return 1

    in_demo = _demo_mode() or dry_run
    if in_demo:
        logger.info(
            "Demo mode active (ENABLE_AI_DEMO_MODE=%s, --dry-run=%s). "
            "No real API calls will be made. Listing what would happen:",
            os.environ.get("ENABLE_AI_DEMO_MODE", "true"),
            dry_run,
        )
        for spec in _METRICS:
            _print_would_do(spec, project_key)
        logger.info("Dry-run complete. %d metric(s) would be provisioned.", len(_METRICS))
        return 0

    api_key = os.environ.get("LAUNCHDARKLY_API_KEY", "").strip()
    if not api_key:
        logger.error(
            "LAUNCHDARKLY_API_KEY is not set. Add it to your .env (see root "
            ".env.example) and re-run, or set ENABLE_AI_DEMO_MODE=true to "
            "preview without provisioning."
        )
        return 1

    created = 0
    skipped = 0
    try:
        with httpx.Client(timeout=15.0) as client:
            for spec in _METRICS:
                if _metric_exists(client, project_key, spec.key, api_key):
                    logger.info("metric '%s' already exists; skipping.", spec.key)
                    skipped += 1
                    continue
                _create_metric(client, project_key, spec, api_key)
                logger.info("metric '%s' created.", spec.key)
                created += 1
    except RuntimeError as exc:
        logger.error("LD API error: %s", exc)
        return 2
    except httpx.HTTPError as exc:
        logger.error("HTTP error talking to LaunchDarkly: %s", exc)
        return 2

    logger.info(
        "Done. created=%d skipped=%d total=%d", created, skipped, len(_METRICS)
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be provisioned without calling the LD API.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    sys.exit(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
