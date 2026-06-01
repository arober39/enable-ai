"""Tutorial reproduction wrapper: 200 conversations over 15 minutes.

A thin wrapper around `scripts/drive_traffic.py` that pins the parameters
the `tutorial-01-multi-signal-guardrails` tutorial expects:

  - 200 inquiries total
  - 15 minutes wall-clock (rate = 15*60 / 199 ≈ 4.52s between calls)
  - Force traffic through a specified AI Config variation

Usage:
    python scripts/replay_traffic.py --variation v2-detailed-responses

Or via Makefile:
    make replay-traffic VARIATION=v2-detailed-responses

The output format is identical to drive_traffic.py — one JSON log line per
call plus an end-of-run summary.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow this script to import drive_traffic whether invoked as
# `python scripts/replay_traffic.py` (no `scripts` package on sys.path) or
# `python -m scripts.replay_traffic` (package import works directly).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from drive_traffic import run as drive_run  # noqa: E402

logger = logging.getLogger("replay_traffic")

_REPO_ROOT: Path = Path(__file__).resolve().parent.parent
_DEFAULT_SCENARIOS_PATH: Path = (
    _REPO_ROOT / "data" / "support" / "replay_scenarios.json"
)

#: Tutorial-pinned constants. Do not change without updating the tutorial.
_TOTAL_INQUIRIES = 200
_DURATION_SECONDS = 15 * 60  # 15 minutes


def _replay_rate_seconds() -> float:
    """Compute the per-call delay so 200 calls span 15 minutes."""
    if _TOTAL_INQUIRIES <= 1:
        return 0.0
    return _DURATION_SECONDS / (_TOTAL_INQUIRIES - 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--variation",
        type=str,
        required=True,
        help="AI Config variation to force through (e.g., v2-detailed-responses).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260513,
        help="Random seed for reproducible scenario order. Default seeded for tutorial.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info(
        "replay_traffic starting: variation=%s count=%d duration=%ds rate=%.2fs/call",
        args.variation,
        _TOTAL_INQUIRIES,
        _DURATION_SECONDS,
        _replay_rate_seconds(),
    )

    sys.exit(
        asyncio.run(
            drive_run(
                scenarios_path=_DEFAULT_SCENARIOS_PATH,
                variation=args.variation,
                rate_seconds=_replay_rate_seconds(),
                count=_TOTAL_INQUIRIES,
                seed=args.seed,
            )
        )
    )


if __name__ == "__main__":
    main()
