"""Live-capture v1 vs v2 refund replies for the multi-signal tutorial.

Pins each on-disk prompt, runs the refund skill (section-level retrieval),
and scores replies with the factual-accuracy judge against the full policy
doc. Does not use LaunchDarkly targeting.

Usage (demo mode must be off):
    ENABLE_AI_DEMO_MODE=false .venv/bin/python scripts/capture_v1_v2.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from orchestrators.support.orchestrator import (  # noqa: E402
    MODEL_NAME,
    AIConfigResult,
    Inquiry,
    _first_text_block,
    _load_default_prompt,
    draft_refund_response,
    load_policies,
)

logger = logging.getLogger("capture_v1_v2")

_SCENARIOS = _REPO / "data" / "support" / "replay_scenarios.json"
_JUDGE = _REPO / "orchestrators" / "support" / "judges" / "factual_accuracy.md"
_OUT_JSON = _REPO / "data" / "support" / "captured_v1_v2.json"
_OUT_MD = _REPO / "data" / "support" / "captured_v1_v2.md"

_VARIATIONS = (
    ("v1-baseline", "v1_baseline"),
    ("v2-detailed-responses", "v2_detailed_responses"),
)


def _load_refund_scenarios() -> list[dict[str, object]]:
    raw = json.loads(_SCENARIOS.read_text(encoding="utf-8"))
    return [s for s in raw if s.get("expected_skill_invoked") == "REFUND"]


def _parse_score(text: str) -> float | None:
    match = re.search(r"\d?\.\d+|\d", text.strip())
    if not match:
        return None
    value = float(match.group())
    if value > 1.0:
        value = value / 10.0 if value <= 10 else 1.0
    return max(0.0, min(1.0, value))


async def _judge(question: str, answer: str) -> float | None:
    from anthropic import AsyncAnthropic

    template = _JUDGE.read_text(encoding="utf-8")
    prompt = template.format(
        policy_context=load_policies(),
        question=question,
        response=answer,
    )
    client = AsyncAnthropic()
    msg = await client.messages.create(
        model=MODEL_NAME,
        max_tokens=16,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_score(_first_text_block(msg))


async def _run_one(
    scenario: dict[str, object],
    variation_name: str,
    prompt_file: str,
) -> dict[str, object]:
    inquiry = Inquiry(
        subject=str(scenario["inquiry_text"]).split(".")[0][:120],
        body=str(scenario["inquiry_text"]),
        customer_id="CAPTURE-001",
    )
    cfg = AIConfigResult(
        variation_name=variation_name,
        system_prompt=_load_default_prompt(prompt_file),
        model=MODEL_NAME,
        params={"temperature": 0.3, "max_tokens": 512},
    )
    reply, citations = await draft_refund_response(inquiry, cfg)
    question = str(scenario["inquiry_text"])
    score = await _judge(question, reply)
    return {
        "id": scenario["id"],
        "tags": scenario.get("tags", []),
        "question": question,
        "variation": variation_name,
        "reply": reply,
        "citations": citations,
        "judge_score": score,
        "error": None,
        "escalated": False,
    }


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _render_markdown(payload: dict[str, object]) -> str:
    headline = next(
        r
        for r in payload["runs"]  # type: ignore[union-attr]
        if r["id"] == "SCN-009" and r["variation"] == "v1-baseline"
    )
    headline_v2 = next(
        r
        for r in payload["runs"]  # type: ignore[union-attr]
        if r["id"] == "SCN-009" and r["variation"] == "v2-detailed-responses"
    )
    by_var = payload["by_variation"]  # type: ignore[assignment]
    lines = [
        "# Captured v1 vs v2 refund run",
        "",
        f"Captured at `{payload['captured_at']}` with `{payload['model']}`, "
        "temperature 0.3. Section-level policy retrieval. Judge scored against "
        "the full `data/support/policies.md`. LaunchDarkly targeting was not used.",
        "",
        "## Headline conversation (SCN-009)",
        "",
        "CUSTOMER:",
        "",
        headline["question"],
        "",
        "V1-BASELINE RESPONSE:",
        "",
        headline["reply"],
        "",
        f"Judge score: `{headline['judge_score']}`",
        "",
        "V2-DETAILED-RESPONSES RESPONSE:",
        "",
        headline_v2["reply"],
        "",
        f"Judge score: `{headline_v2['judge_score']}`",
        "",
        "## Metric table (refund scenarios only)",
        "",
        "| Metric | v1-baseline | v2-detailed-responses |",
        "| --- | --- | --- |",
        f"| Error count | {by_var['v1-baseline']['error_rate']} | "
        f"{by_var['v2-detailed-responses']['error_rate']} |",
        f"| Escalation rate | {by_var['v1-baseline']['escalation_rate']} | "
        f"{by_var['v2-detailed-responses']['escalation_rate']} |",
        f"| Judge score (mean) | {by_var['v1-baseline']['mean_judge_score']} | "
        f"{by_var['v2-detailed-responses']['mean_judge_score']} |",
        f"| n | {by_var['v1-baseline']['n']} | {by_var['v2-detailed-responses']['n']} |",
        "",
        "Refund-path replies do not escalate. Errors are exceptions only. "
        "The judge is the signal that moves.",
        "",
        "## Per-scenario judge scores",
        "",
        "| Scenario | Tags | v1 | v2 |",
        "| --- | --- | --- | --- |",
    ]
    ids = sorted({r["id"] for r in payload["runs"]})  # type: ignore[union-attr]
    for sid in ids:
        v1 = next(r for r in payload["runs"] if r["id"] == sid and r["variation"].startswith("v1"))  # type: ignore[union-attr]
        v2 = next(r for r in payload["runs"] if r["id"] == sid and r["variation"].startswith("v2"))  # type: ignore[union-attr]
        tags = ",".join(v1["tags"])
        lines.append(f"| {sid} | {tags} | {v1['judge_score']} | {v2['judge_score']} |")
    lines.extend(["", "## Probe replies", ""])
    for sid in ("SCN-031", "SCN-032", "SCN-010"):
        for variation in ("v1-baseline", "v2-detailed-responses"):
            run = next(
                r
                for r in payload["runs"]  # type: ignore[union-attr]
                if r["id"] == sid and r["variation"] == variation
            )
            lines.extend(
                [
                    f"### {sid} — {variation}",
                    "",
                    run["question"],
                    "",
                    run["reply"],
                    "",
                    f"Judge score: `{run['judge_score']}`",
                    "",
                ]
            )
    return "\n".join(lines) + "\n"


async def main() -> int:
    if os.environ.get("ENABLE_AI_DEMO_MODE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        logger.error("Set ENABLE_AI_DEMO_MODE=false to capture live replies.")
        return 1
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY is not set.")
        return 1

    scenarios = _load_refund_scenarios()
    runs: list[dict[str, object]] = []
    for scenario in scenarios:
        for variation_name, prompt_file in _VARIATIONS:
            logger.info("running %s %s", scenario["id"], variation_name)
            runs.append(await _run_one(scenario, variation_name, prompt_file))

    by_variation: dict[str, dict[str, object]] = {}
    for variation_name, _prompt_file in _VARIATIONS:
        subset = [r for r in runs if r["variation"] == variation_name]
        scores = [float(r["judge_score"]) for r in subset if r["judge_score"] is not None]
        by_variation[variation_name] = {
            "n": len(subset),
            "mean_judge_score": _mean(scores),
            "error_rate": round(sum(1 for r in subset if r["error"]) / len(subset), 3)
            if subset
            else 0.0,
            "escalation_rate": round(sum(1 for r in subset if r["escalated"]) / len(subset), 3)
            if subset
            else 0.0,
        }

    payload = {
        "captured_at": datetime.now(UTC).isoformat(),
        "model": MODEL_NAME,
        "temperature": 0.3,
        "retrieval": "single policy section",
        "judge": "orchestrators/support/judges/factual_accuracy.md against full policies.md",
        "by_variation": by_variation,
        "runs": runs,
    }
    _OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _OUT_MD.write_text(_render_markdown(payload), encoding="utf-8")
    logger.info("wrote %s and %s", _OUT_JSON, _OUT_MD)
    print(json.dumps(by_variation, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    sys.exit(asyncio.run(main()))
