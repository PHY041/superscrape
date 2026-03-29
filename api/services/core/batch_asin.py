"""Batch ASIN management — manage multiple ASINs simultaneously.

Supports batch operations across multiple product listings:
- Batch scraping and analysis
- Batch image generation
- Progress tracking per-ASIN
- Aggregate reporting across ASINs
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class BatchStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    partial = "partial"  # some ASINs succeeded, some failed
    failed = "failed"


@dataclass
class ASINTask:
    """Status of a single ASIN within a batch."""

    asin: str
    status: str = "pending"  # pending | scraping | analyzing | generating | done | failed
    job_id: str = ""  # linked SuperScrape job ID
    error: str = ""
    progress: int = 0
    images_generated: int = 0


@dataclass
class BatchJob:
    """A batch operation across multiple ASINs."""

    batch_id: str = ""
    created_at: str = ""
    keyword: str = ""
    asins: list[ASINTask] = field(default_factory=list)
    status: BatchStatus = BatchStatus.pending
    total: int = 0
    completed_count: int = 0
    failed_count: int = 0


class BatchASINManager:
    """Manage batch operations across multiple product ASINs.

    Current status: STUB — provides interface and tracking.
    Full implementation needs:
    1. Integration with JobRunner for parallel scraping
    2. Queue management for rate limiting
    3. Persistent storage for batch state
    4. Webhook/SSE notifications for batch progress
    """

    def __init__(self) -> None:
        self._batches: dict[str, BatchJob] = {}

    def create_batch(
        self,
        asins: list[str],
        keyword: str = "",
    ) -> BatchJob:
        """Create a new batch job for multiple ASINs."""
        batch_id = str(uuid.uuid4())[:8]
        batch = BatchJob(
            batch_id=batch_id,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
            keyword=keyword,
            asins=[ASINTask(asin=a) for a in asins],
            total=len(asins),
        )
        self._batches[batch_id] = batch
        logger.info("Created batch %s with %d ASINs", batch_id, len(asins))
        return batch

    def get_batch(self, batch_id: str) -> BatchJob | None:
        """Get batch job status."""
        return self._batches.get(batch_id)

    def update_asin_status(
        self,
        batch_id: str,
        asin: str,
        status: str,
        job_id: str = "",
        progress: int = 0,
        error: str = "",
    ) -> None:
        """Update status of a single ASIN within a batch."""
        batch = self._batches.get(batch_id)
        if batch is None:
            return

        for task in batch.asins:
            if task.asin == asin:
                task.status = status
                task.job_id = job_id or task.job_id
                task.progress = progress
                task.error = error
                break

        # Update batch-level counts
        batch.completed_count = sum(1 for t in batch.asins if t.status == "done")
        batch.failed_count = sum(1 for t in batch.asins if t.status == "failed")

        if batch.completed_count + batch.failed_count >= batch.total:
            if batch.failed_count == 0:
                batch.status = BatchStatus.completed
            elif batch.completed_count == 0:
                batch.status = BatchStatus.failed
            else:
                batch.status = BatchStatus.partial

    def list_batches(self) -> list[BatchJob]:
        """List all batch jobs."""
        return list(self._batches.values())

    def get_aggregate_report(self, batch_id: str) -> dict:
        """Get aggregate report across all ASINs in a batch."""
        batch = self._batches.get(batch_id)
        if batch is None:
            return {}

        return {
            "batch_id": batch.batch_id,
            "keyword": batch.keyword,
            "total_asins": batch.total,
            "completed": batch.completed_count,
            "failed": batch.failed_count,
            "status": batch.status.value,
            "asin_statuses": [
                {
                    "asin": t.asin,
                    "status": t.status,
                    "job_id": t.job_id,
                    "progress": t.progress,
                    "error": t.error,
                }
                for t in batch.asins
            ],
        }


# Module-level singleton
batch_manager = BatchASINManager()
