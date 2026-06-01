"""CLI entry point: `python -m coordinator "Enable AI for customer support"`.

Calls `run_coordinator`, pretty-prints the resulting EnablementPlan as JSON to
stdout, and exits 0 on success. Exits non-zero with a structured error on
schema validation failure or runtime error.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

from coordinator.agent import run_coordinator


def _configure_logging() -> None:
    """Send INFO+ logs to stderr so they don't muddy the JSON on stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _usage() -> str:
    return (
        "Usage: python -m coordinator \"<request>\"\n"
        "Example: python -m coordinator \"Enable AI for customer support\""
    )


async def _amain(request: str) -> int:
    try:
        result = await run_coordinator(request)
    except ValueError as exc:
        print(json.dumps({"error": "invalid_request", "message": str(exc)}), file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(json.dumps({"error": "runtime_error", "message": str(exc)}), file=sys.stderr)
        return 3

    # Pretty-print the structured result to stdout.
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0


def main() -> None:
    _configure_logging()
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print(_usage(), file=sys.stderr)
        sys.exit(2)
    # Join everything after argv[0] so shells that don't quote the request still work.
    request = " ".join(sys.argv[1:])
    sys.exit(asyncio.run(_amain(request)))


if __name__ == "__main__":
    main()
