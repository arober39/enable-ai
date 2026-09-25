"""In-process jobs for work that must outlive the browser tab.

A page navigation or a hidden tab aborts the HTTP request that started
the run. The job itself stays on the event loop and can be polled after
the tab comes back. Jobs live only as long as this process.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

JobKind = Literal["enablement", "build"]
JobStatus = Literal["running", "done", "error", "cancelled"]


@dataclass
class Job:
    id: str
    kind: JobKind
    status: JobStatus = "running"
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    result: dict[str, Any] | None = None
    error: str | None = None


_jobs: dict[str, Job] = {}
_tasks: set[asyncio.Task[None]] = set()
_job_tasks: dict[str, asyncio.Task[None]] = {}


def start_job(kind: JobKind) -> Job:
    job = Job(id=uuid.uuid4().hex, kind=kind)
    _jobs[job.id] = job
    return job


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def spawn(job_id: str, work: Any) -> None:
    """Run `work` (an awaitable) after the request that started it returns."""

    async def _run() -> None:
        job = _jobs.get(job_id)
        if job is None:
            return
        try:
            result = await work
            if job.status == "running":
                job.status = "done"
                job.result = result
        except asyncio.CancelledError:
            if job.status == "running":
                job.status = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001 — stored for the poller
            if job.status == "running":
                job.status = "error"
                detail = getattr(exc, "detail", None)
                job.error = str(detail) if detail else f"{type(exc).__name__}: {exc}"

    task = asyncio.create_task(_run())
    _job_tasks[job_id] = task
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    task.add_done_callback(lambda _task: _job_tasks.pop(job_id, None))


def cancel_job(job_id: str) -> Job | None:
    """Stop a running job. A finished job is left as it is."""
    job = _jobs.get(job_id)
    if job is None or job.status != "running":
        return job
    job.status = "cancelled"
    task = _job_tasks.get(job_id)
    if task is not None and not task.done():
        task.cancel()
    return job
