"""In-memory job store with SSE subscriber pattern."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import AsyncIterator

from api.models.api_models import JobStatus, PipelineStep, ProgressEvent

logger = logging.getLogger(__name__)

# Sentinel pushed to subscriber queues when the job terminates
_SENTINEL = object()


class JobStore:
    """Thread-safe in-memory store for job state and SSE subscribers."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobStatus] = {}
        # Each job can have multiple SSE subscribers; each gets its own queue
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lock = threading.Lock()  # thread-safe for cross-thread access

    def create(self, job_id: str) -> JobStatus:
        """Create a new job and return the initial status."""
        status = JobStatus(job_id=job_id)
        self._jobs[job_id] = status
        return status

    def get(self, job_id: str) -> JobStatus | None:
        """Return the current status for a job, or None if not found."""
        return self._jobs.get(job_id)

    def update(self, job_id: str, event: ProgressEvent) -> None:
        """Apply a progress event to the job and push it to all subscriber queues."""
        with self._lock:
            status = self._jobs.get(job_id)
            if status is None:
                logger.warning("update called for unknown job_id=%s", job_id)
                return

            updated = status.model_copy(
                update={
                    "step": event.step,
                    "progress": event.progress,
                    "message": event.message,
                }
            )
            self._jobs[job_id] = updated

            # Push to every active SSE subscriber (snapshot list under lock)
            for q in list(self._subscribers[job_id]):
                q.put_nowait(event)

    def mark_done(self, job_id: str, report_url: str, pdf_url: str | None = None) -> None:
        """Mark a job as completed, store URLs, and terminate all subscriber streams."""
        with self._lock:
            status = self._jobs.get(job_id)
            if status is None:
                return

            done_event = ProgressEvent(
                step=PipelineStep.done,
                message="Report ready",
                progress=100,
                detail={"report_url": report_url, "pdf_url": pdf_url or ""},
            )
            updated = status.model_copy(
                update={
                    "step": PipelineStep.done,
                    "progress": 100,
                    "message": "Report ready",
                    "report_url": report_url,
                    "pdf_url": pdf_url,
                    "completed_at": datetime.now(tz=timezone.utc),
                }
            )
            self._jobs[job_id] = updated

            for q in list(self._subscribers[job_id]):
                q.put_nowait(done_event)
                q.put_nowait(_SENTINEL)

    def mark_failed(self, job_id: str, error: str) -> None:
        """Mark a job as failed and terminate all subscriber streams."""
        with self._lock:
            status = self._jobs.get(job_id)
            if status is None:
                return

            fail_event = ProgressEvent(
                step=PipelineStep.failed,
                message=f"Pipeline failed: {error}",
                progress=0,
                detail={"error": error},
            )
            updated = status.model_copy(
                update={
                    "step": PipelineStep.failed,
                    "message": f"Pipeline failed: {error}",
                    "error": error,
                    "completed_at": datetime.now(tz=timezone.utc),
                }
            )
            self._jobs[job_id] = updated

            for q in list(self._subscribers[job_id]):
                q.put_nowait(fail_event)
                q.put_nowait(_SENTINEL)

    async def subscribe(self, job_id: str) -> AsyncIterator[ProgressEvent]:
        """Async generator that yields ProgressEvents as they arrive.

        Yields all events until the job terminates (sentinel received).
        Cleans up the queue on exit.
        """
        queue: asyncio.Queue = asyncio.Queue()

        # Atomic append + terminal check to prevent missed sentinel
        with self._lock:
            self._subscribers[job_id].append(queue)
            current = self._jobs.get(job_id)
        if current and current.step in (PipelineStep.done, PipelineStep.failed):
            event = ProgressEvent(
                step=current.step,
                message=current.message,
                progress=current.progress,
                detail={"report_url": current.report_url or "", "error": current.error or ""},
            )
            yield event
            self._subscribers[job_id].remove(queue)
            return

        try:
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    break
                yield item
        finally:
            try:
                self._subscribers[job_id].remove(queue)
            except ValueError:
                pass


# Module-level singleton
store = JobStore()
