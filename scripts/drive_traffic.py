"""Send synthetic support conversations through the support orchestrator.

Reads scenarios from `data/support/replay_scenarios.json` and runs each one
through `orchestrators.support.orchestrator.handle_inquiry`. Logs the
variation served, the orchestrator's structured response, and per-call
latency. Useful for:

  - smoke-testing the orchestrator runtime contract end-to-end
  - generating the LD event traffic the multi-signal guardrails tutorial
    measures against (run with `--variation v2-detailed-responses` to
    force the regression-prone variation)
  - reproducing realistic load patterns in a deterministic order

By default, runs ALL 30 scenarios once with a 30-second pace (one inquiry
every 30 seconds — matches the build plan's "1/30s for replay realism"
default). For faster local testing, set `--rate-seconds 0`.

Demo-mode (`ENABLE_AI_DEMO_MODE=true`, default) routes through the
orchestrator's stub paths — no real LD or Anthropic calls. Useful for
exercising the runtime contract in tests.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("drive_traffic")

_REPO_ROOT: Path = Path(__file__).resolve().parent.parent
_DEFAULT_SCENARIOS_PATH: Path = (
    _REPO_ROOT / "data" / "support" / "replay_scenarios.json"
)


@dataclass
class Scenario:
    id: str
    inquiry_text: str
    expected_skill_invoked: str
    tags: list[str]


def _load_scenarios(path: Path) -> list[Scenario]:
    if not path.exists():
        raise FileNotFoundError(
            f"Scenarios file not found at {path}. Phase 6.2 creates this; "
            "see BUILD_PLAN.md."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Scenarios file {path} must contain a JSON array.")
    return [
        Scenario(
            id=item["id"],
            inquiry_text=item["inquiry_text"],
            expected_skill_invoked=item["expected_skill_invoked"],
            tags=list(item.get("tags", [])),
        )
        for item in raw
    ]


def _ensure_orchestrator_importable() -> None:
    """Add the repo root to sys.path and create stub __init__ files if missing.

    The generated orchestrator package needs __init__.py files in each
    directory. Phase 5 generates the directory tree but not always the
    __init__ markers; this helper is idempotent.
    """
    sys.path.insert(0, str(_REPO_ROOT))
    for d in [
        _REPO_ROOT / "orchestrators",
        _REPO_ROOT / "orchestrators" / "support",
        _REPO_ROOT / "orchestrators" / "support" / "mcp_servers",
    ]:
        init = d / "__init__.py"
        if d.exists() and not init.exists():
            init.touch()


@dataclass
class CallLog:
    scenario_id: str
    variation_served: str
    intent_returned: str
    action_taken: str
    escalated: bool
    error: str | None
    latency_ms: float
    expected_skill_invoked: str
    skill_matched: bool


async def _drive_one(
    scenario: Scenario,
    *,
    variation_override: str | None,
    customer_id: str,
) -> CallLog:
    """Run one scenario through handle_inquiry; capture timing + result."""
    from orchestrators.support.orchestrator import Inquiry, handle_inquiry

    inquiry = Inquiry(
        subject=scenario.inquiry_text.split(".")[0][:120],
        body=scenario.inquiry_text,
        customer_id=customer_id,
    )
    t0 = time.perf_counter()
    response = await handle_inquiry(inquiry, request_id=scenario.id)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # variation_served — in demo mode the orchestrator always serves v1-baseline.
    # If the caller asked for a different variation (production replay), we
    # record the intent; the actual LD-served variation is logged inside the
    # orchestrator via OTel.
    variation_served = variation_override or "v1-baseline"

    return CallLog(
        scenario_id=scenario.id,
        variation_served=variation_served,
        intent_returned=response.intent,
        action_taken=response.action_taken,
        escalated=response.escalated,
        error=response.error,
        latency_ms=elapsed_ms,
        expected_skill_invoked=scenario.expected_skill_invoked,
        skill_matched=(response.intent == scenario.expected_skill_invoked),
    )


def _emit_log_line(log: CallLog) -> None:
    """One-line JSON-ish log per scenario, easy to grep."""
    payload: dict[str, Any] = {
        "scenario_id": log.scenario_id,
        "variation": log.variation_served,
        "intent": log.intent_returned,
        "expected": log.expected_skill_invoked,
        "match": log.skill_matched,
        "action": log.action_taken,
        "escalated": log.escalated,
        "latency_ms": round(log.latency_ms, 2),
    }
    if log.error:
        payload["error"] = log.error
    logger.info(json.dumps(payload))


def _summarize(logs: list[CallLog]) -> dict[str, Any]:
    """End-of-run summary printed when the loop finishes."""
    total = len(logs)
    matches = sum(1 for log in logs if log.skill_matched)
    escalations = sum(1 for log in logs if log.escalated)
    errors = sum(1 for log in logs if log.error)
    avg_latency = (
        sum(log.latency_ms for log in logs) / total if total else 0.0
    )
    return {
        "total": total,
        "skill_match_rate": round(matches / total, 3) if total else 0.0,
        "escalation_rate": round(escalations / total, 3) if total else 0.0,
        "error_rate": round(errors / total, 3) if total else 0.0,
        "avg_latency_ms": round(avg_latency, 2),
    }


async def run(
    *,
    scenarios_path: Path,
    variation: str | None,
    rate_seconds: float,
    count: int | None,
    seed: int | None,
) -> int:
    """Drive synthetic traffic. Return exit code."""
    try:
        scenarios = _load_scenarios(scenarios_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Scenario load error: %s", exc)
        return 1

    if not scenarios:
        logger.error("No scenarios found in %s", scenarios_path)
        return 1

    _ensure_orchestrator_importable()

    rng = random.Random(seed)
    # If count was specified, sample (with replacement when count > len) so the
    # script can drive an arbitrary volume. Otherwise iterate once through all.
    if count is None:
        sequence = scenarios
    else:
        if count <= len(scenarios):
            sequence = rng.sample(scenarios, count)
        else:
            sequence = rng.choices(scenarios, k=count)

    logger.info(
        "drive_traffic starting: scenarios=%d count=%d variation=%s rate=%.2fs",
        len(scenarios),
        len(sequence),
        variation or "<orchestrator default>",
        rate_seconds,
    )

    logs: list[CallLog] = []
    for i, scenario in enumerate(sequence):
        customer_id = f"REPLAY-{rng.randint(1, 20):03d}"
        try:
            log = await _drive_one(
                scenario,
                variation_override=variation,
                customer_id=customer_id,
            )
        except Exception as exc:  # noqa: BLE001 — drive_traffic must not crash
            logger.exception(
                "scenario %s raised: %s", scenario.id, exc
            )
            continue
        logs.append(log)
        _emit_log_line(log)

        if rate_seconds > 0 and i < len(sequence) - 1:
            await asyncio.sleep(rate_seconds)

    summary = _summarize(logs)
    logger.info("summary: %s", json.dumps(summary))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=_DEFAULT_SCENARIOS_PATH,
        help=f"Path to replay_scenarios.json (default: {_DEFAULT_SCENARIOS_PATH}).",
    )
    parser.add_argument(
        "--variation",
        type=str,
        default=None,
        help=(
            "Force a specific AI Config variation (e.g., v2-detailed-responses). "
            "Logged on each call; the orchestrator itself still negotiates the "
            "variation with LaunchDarkly in production mode."
        ),
    )
    parser.add_argument(
        "--rate-seconds",
        type=float,
        default=30.0,
        help="Seconds to wait between calls (default: 30, per BUILD_PLAN.md 6.2).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="How many inquiries to send. Default: all scenarios once.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible scenario ordering (when --count is used).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Bound rate to non-negative.
    rate = max(0.0, float(args.rate_seconds))

    exit_code = asyncio.run(
        run(
            scenarios_path=args.scenarios,
            variation=args.variation,
            rate_seconds=rate,
            count=args.count,
            seed=args.seed,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
