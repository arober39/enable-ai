#!/usr/bin/env python3
"""Send repeated live Agent Architect requests during a guarded rollout stage.

Usage:
  1) Start backend in live mode first (same command as repo docs):
       ENABLE_AI_DEMO_MODE=false make ui-backend
  2) While the guarded rollout stage is open, run:
       .venv/bin/python ui/scripts/send_live_rollout_traffic.py --count 10

This script calls the existing `POST /api/enablement` path with one stable
payload and repeats it. It does not read or hardcode secrets.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time

import httpx

logger = logging.getLogger("ui.scripts.send_live_rollout_traffic")

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_COUNT = 10
DEFAULT_DELAY_SECONDS = 1.2
DEFAULT_FRICTION = (
    "Blueprint handoff takes too long because tooling overlap is unclear, "
    "so I need one clear supervised-agent plan."
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Send repeated Agent Architect live requests through /api/enablement "
            "to generate rollout evaluations."
        )
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Backend base URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help=f"Number of requests to send (default: {DEFAULT_COUNT}).",
    )
    parser.add_argument(
        "--role",
        default="",
        help="Role id. Defaults to /api/preferences selected_role.",
    )
    parser.add_argument(
        "--tools",
        default="",
        help="Comma-separated tool ids. Defaults to /api/stacks/{role_id}.",
    )
    parser.add_argument(
        "--friction",
        default=DEFAULT_FRICTION,
        help="Stable friction text reused for each request.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=(
            "Minimum spacing between request starts. Keep >=1.0 so each run gets "
            "a distinct session/context id (default: 1.2)."
        ),
    )
    return parser.parse_args()


def _selected_role_from_preferences(payload: object) -> str:
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected /api/preferences payload shape.")
    selected_role = payload.get("selected_role")
    if not isinstance(selected_role, str) or not selected_role:
        raise RuntimeError("Could not resolve selected_role from /api/preferences.")
    return selected_role


def _tools_from_stack(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected /api/stacks payload shape.")
    tools = payload.get("tools")
    if not isinstance(tools, list) or not all(isinstance(item, str) for item in tools):
        raise RuntimeError("Could not resolve tools list from /api/stacks response.")
    if not tools:
        raise RuntimeError("Resolved stack had zero tools.")
    return list(tools)


def _task_selections(work_tasks_payload: object) -> list[dict[str, str]]:
    if not isinstance(work_tasks_payload, list):
        raise RuntimeError("Unexpected /api/work-tasks payload shape.")
    selections: list[dict[str, str]] = []
    for item in work_tasks_payload:
        if not isinstance(item, dict):
            continue
        task_id = item.get("id")
        label = item.get("label")
        source = item.get("source")
        if not isinstance(task_id, str) or not isinstance(label, str):
            continue
        if not isinstance(source, str):
            source = "actual"
        selections.append({"id": task_id, "label": label, "source": source})
    if not selections:
        raise RuntimeError("Could not build task selections from /api/work-tasks.")
    return selections


def _variation_from_response(body: object) -> str:
    if not isinstance(body, dict):
        return "n/a"
    plan = body.get("plan")
    if not isinstance(plan, dict):
        return "n/a"
    metadata = plan.get("metadata")
    if not isinstance(metadata, dict):
        return "n/a"
    # The current API response does not expose variation; keep this forward-compatible.
    variation = metadata.get("variation_key")
    if isinstance(variation, str) and variation:
        return variation
    return "n/a"


def _session_id_from_response(body: object) -> str:
    if not isinstance(body, dict):
        return "unknown"
    plan = body.get("plan")
    if not isinstance(plan, dict):
        return "unknown"
    metadata = plan.get("metadata")
    if not isinstance(metadata, dict):
        return "unknown"
    session_id = metadata.get("coordinator_session_id")
    if isinstance(session_id, str) and session_id:
        return session_id
    return "unknown"


def _stable_tools_argument(raw_tools: str) -> list[str]:
    tool_names = [name.strip() for name in raw_tools.split(",") if name.strip()]
    if not tool_names:
        raise RuntimeError("--tools resolved to an empty list.")
    return tool_names


async def _get_json(client: httpx.AsyncClient, path: str) -> object:
    response = await client.get(path)
    response.raise_for_status()
    return response.json()


async def _post_enablement(
    client: httpx.AsyncClient,
    payload: dict[str, object],
) -> tuple[bool, int, str, str, str]:
    response = await client.post("/api/enablement", json=payload)
    if response.status_code >= 400:
        detail = response.text.strip().replace("\n", " ")
        return False, response.status_code, "rejected", "n/a", detail[:240]

    body = response.json()
    if not isinstance(body, dict):
        return False, response.status_code, "invalid-json", "n/a", "Unexpected response body."
    mode = body.get("mode")
    session_id = _session_id_from_response(body)
    variation = _variation_from_response(body)
    if mode != "live":
        return False, response.status_code, session_id, variation, f"mode={mode!r}"
    return True, response.status_code, session_id, variation, "accepted"


async def _run(args: argparse.Namespace) -> int:
    if args.count <= 0:
        raise RuntimeError("--count must be > 0.")
    if args.delay_seconds < 1.0:
        raise RuntimeError(
            "--delay-seconds must be >= 1.0 to keep session/context ids distinct."
        )

    timeout = httpx.Timeout(300.0, connect=10.0)
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=timeout) as client:
        health = await _get_json(client, "/api/health")
        if not isinstance(health, dict):
            raise RuntimeError("Unexpected /api/health payload shape.")
        if bool(health.get("demo_mode")):
            raise RuntimeError(
                "Backend is in demo mode. Set ENABLE_AI_DEMO_MODE=false and restart with "
                "`make ui-backend` before using this script."
            )
        if not bool(health.get("has_anthropic_key")):
            raise RuntimeError(
                "Backend reports no ANTHROPIC_API_KEY. Live mode requires it."
            )

        role_id = args.role.strip()
        if not role_id:
            role_id = _selected_role_from_preferences(await _get_json(client, "/api/preferences"))

        tools: list[str]
        if args.tools.strip():
            tools = _stable_tools_argument(args.tools)
        else:
            stacks_payload = await _get_json(client, f"/api/stacks/{role_id}")
            tools = _tools_from_stack(stacks_payload)

        tasks_payload = await _get_json(client, f"/api/work-tasks?role={role_id}")
        tasks = _task_selections(tasks_payload)

        payload: dict[str, object] = {
            "role": role_id,
            "tools": tools,
            "tasks": tasks,
            "friction": args.friction,
        }
        logger.info(
            "sending %d live requests role=%s tools=%s tasks=%d base_url=%s",
            args.count,
            role_id,
            ",".join(tools),
            len(tasks),
            args.base_url,
        )

        successes = 0
        failures = 0
        seen_session_ids: set[str] = set()
        duplicate_session_ids = 0

        for index in range(1, args.count + 1):
            started_at = time.monotonic()
            ok, status_code, session_id, variation, note = await _post_enablement(client, payload)
            if session_id in seen_session_ids:
                duplicate_session_ids += 1
            seen_session_ids.add(session_id)

            status_text = "ok" if ok else "fail"
            logger.info(
                "request %02d/%02d status=%s http=%d session=%s variation=%s note=%s",
                index,
                args.count,
                status_text,
                status_code,
                session_id,
                variation,
                note,
            )
            if ok:
                successes += 1
            else:
                failures += 1

            elapsed = time.monotonic() - started_at
            remaining = args.delay_seconds - elapsed
            if index < args.count and remaining > 0:
                await asyncio.sleep(remaining)

    logger.info(
        "finished successes=%d failures=%d unique_sessions=%d duplicate_sessions=%d",
        successes,
        failures,
        len(seen_session_ids),
        duplicate_session_ids,
    )
    return 0 if successes > 0 else 1


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    exit_code = asyncio.run(_run(args))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
