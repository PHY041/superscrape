"""Job store with SSE subscriber pattern + file-based persistence.

Jobs and their data are persisted to disk as JSON files so they survive
server restarts. The SSE subscriber pattern remains fully in-memory
(queues are ephemeral by nature).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from api.models.api_models import JobStatus, PipelineStep, ProgressEvent

logger = logging.getLogger(__name__)

_PERSIST_DIR = Path(os.environ.get("JOB_STORE_DIR", "/tmp/superscrape_jobs"))

# Sentinel pushed to subscriber queues when the job terminates
_SENTINEL = object()


class JobData:
    """Container for pipeline output data (products, analyses, report, strategy)."""

    __slots__ = ("products", "analyses", "report", "action_plan", "ab_tests", "seasonal_alerts", "review_insights", "story_arc")

    def __init__(
        self,
        products: list,
        analyses: list,
        report: object | None = None,
        action_plan: list | None = None,
        ab_tests: list | None = None,
        seasonal_alerts: list | None = None,
        review_insights: dict | None = None,
        story_arc: dict | None = None,
    ) -> None:
        self.products = products
        self.analyses = analyses
        self.report = report
        self.action_plan = action_plan or []
        self.ab_tests = ab_tests or []
        self.seasonal_alerts = seasonal_alerts or []
        self.review_insights = review_insights or {}
        self.story_arc = story_arc or {}


def _serialize_report(report: object) -> dict | None:
    """Serialize a report object to a dict for JSON persistence."""
    if report is None:
        return None
    if hasattr(report, "model_dump"):
        return report.model_dump()
    if isinstance(report, dict):
        return report
    return None


class JobStore:
    """Thread-safe store for job state and SSE subscribers with file persistence."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobStatus] = {}
        self._data: dict[str, JobData] = {}
        # Each job can have multiple SSE subscribers; each gets its own queue
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lock = threading.Lock()  # thread-safe for cross-thread access

        # Load persisted jobs on startup
        self._load_persisted()

    def _load_persisted(self) -> None:
        """Load completed jobs from disk on startup."""
        if not _PERSIST_DIR.exists():
            return

        status_dir = _PERSIST_DIR / "status"
        if not status_dir.exists():
            return

        loaded = 0
        for f in status_dir.glob("*.json"):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                job_id = raw["job_id"]
                self._jobs[job_id] = JobStatus(**raw)

                # Load data if available
                data_file = _PERSIST_DIR / "data" / f"{job_id}.json"
                if data_file.exists():
                    data_raw = json.loads(data_file.read_text(encoding="utf-8"))
                    self._data[job_id] = JobData(
                        products=data_raw.get("products", []),
                        analyses=data_raw.get("analyses", []),
                        report=data_raw.get("report"),
                        action_plan=data_raw.get("action_plan", []),
                        ab_tests=data_raw.get("ab_tests", []),
                        seasonal_alerts=data_raw.get("seasonal_alerts", []),
                        review_insights=data_raw.get("review_insights", {}),
                        story_arc=data_raw.get("story_arc", {}),
                    )
                loaded += 1
            except Exception as e:
                logger.warning("Failed to load persisted job %s: %s", f.name, e)

        if loaded:
            logger.info("Loaded %d persisted jobs from %s", loaded, _PERSIST_DIR)

    def _persist_status(self, job_id: str) -> None:
        """Write job status to disk."""
        try:
            status_dir = _PERSIST_DIR / "status"
            status_dir.mkdir(parents=True, exist_ok=True)
            status = self._jobs.get(job_id)
            if status:
                path = status_dir / f"{job_id}.json"
                path.write_text(
                    json.dumps(status.model_dump(), default=str, ensure_ascii=False),
                    encoding="utf-8",
                )
        except Exception as e:
            logger.warning("Failed to persist status for %s: %s", job_id, e)

    def _persist_data(self, job_id: str) -> None:
        """Write job data to disk."""
        try:
            data_dir = _PERSIST_DIR / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            data = self._data.get(job_id)
            if data is None:
                return

            serialized = {
                "products": [
                    p.model_dump() if hasattr(p, "model_dump") else p
                    for p in data.products
                ],
                "analyses": [
                    a.model_dump() if hasattr(a, "model_dump") else a
                    for a in data.analyses
                ],
                "report": _serialize_report(data.report),
                "action_plan": data.action_plan,
                "ab_tests": data.ab_tests,
                "seasonal_alerts": data.seasonal_alerts,
                "review_insights": data.review_insights,
                "story_arc": data.story_arc,
            }

            path = data_dir / f"{job_id}.json"
            path.write_text(
                json.dumps(serialized, default=str, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed to persist data for %s: %s", job_id, e)

    def create(self, job_id: str) -> JobStatus:
        """Create a new job and return the initial status."""
        status = JobStatus(job_id=job_id)
        self._jobs[job_id] = status
        self._persist_status(job_id)
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

        self._persist_status(job_id)

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

        self._persist_status(job_id)

    def save_data(
        self,
        job_id: str,
        products: list,
        analyses: list,
        report: object | None = None,
        action_plan: list | None = None,
        ab_tests: list | None = None,
        seasonal_alerts: list | None = None,
        review_insights: dict | None = None,
        story_arc: dict | None = None,
    ) -> None:
        """Store structured pipeline output for later retrieval via /data endpoint."""
        with self._lock:
            self._data[job_id] = JobData(
                products=products,
                analyses=analyses,
                report=report,
                action_plan=action_plan,
                ab_tests=ab_tests,
                seasonal_alerts=seasonal_alerts,
                review_insights=review_insights,
                story_arc=story_arc,
            )
        self._persist_data(job_id)

    def get_data(self, job_id: str) -> JobData | None:
        """Return stored pipeline data, or None if not available."""
        return self._data.get(job_id)

    def list_jobs(self, limit: int = 50) -> list[JobStatus]:
        """Return recent jobs, newest first."""
        jobs = sorted(
            self._jobs.values(),
            key=lambda j: j.created_at,
            reverse=True,
        )
        return jobs[:limit]

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
