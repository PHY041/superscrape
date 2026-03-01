"""Competitor monitoring + batch ASIN + A/B tracking + agent signal routes."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.models.api_models import JobRequest, Platform
from api.services.ab_tracker import TestMetric, TestStatus, ab_tracker
from api.services.agent_signals import AgentRole, SignalType, signal_bus
from api.services.batch_asin import batch_manager
from api.services.competitor_monitor import monitor
from api.services.job_runner import runner
from api.services.job_store import store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["advanced"])


# ── Competitor Monitor ─────────────────────────────────────────────────────────

class MonitorASINRequest(BaseModel):
    asin: str


@router.post("/monitor/watch")
async def add_watch(req: MonitorASINRequest) -> dict:
    """Add an ASIN to the competitor monitoring watchlist."""
    monitor.add_asin(req.asin)
    return {"watchlist": monitor.get_watchlist()}


@router.delete("/monitor/watch/{asin}")
async def remove_watch(asin: str) -> dict:
    """Remove an ASIN from the watchlist."""
    monitor.remove_asin(asin)
    return {"watchlist": monitor.get_watchlist()}


class MonitorActivateRequest(BaseModel):
    interval_hours: int = 24


@router.post("/monitor/activate")
async def activate_monitor(req: MonitorActivateRequest) -> dict:
    """Activate periodic competitor monitoring."""
    return await monitor.activate(interval_hours=req.interval_hours)


@router.post("/monitor/deactivate")
async def deactivate_monitor() -> dict:
    """Stop periodic competitor monitoring."""
    return await monitor.deactivate()


@router.get("/monitor/status")
async def monitor_status() -> dict:
    """Get competitor monitor status."""
    return monitor.get_status()


@router.get("/monitor/changes")
async def list_changes() -> dict:
    """List all detected competitor listing changes."""
    changes = monitor.get_all_changes()
    return {
        "total": len(changes),
        "changes": [
            {
                "asin": c.asin,
                "field": c.field,
                "old_value": c.old_value,
                "new_value": c.new_value,
                "detected_at": c.detected_at,
                "severity": c.severity,
            }
            for c in changes
        ],
    }


@router.get("/monitor/history/{asin}")
async def asin_history(asin: str) -> dict:
    """Get snapshot history for a specific ASIN."""
    history = monitor.get_history(asin)
    return {
        "asin": asin,
        "snapshots": [
            {
                "captured_at": s.captured_at,
                "title": s.title[:80],
                "price": s.price,
                "rating": s.rating,
                "reviews_count": s.reviews_count,
                "image_count": s.image_count,
                "has_aplus": s.has_aplus,
            }
            for s in history
        ],
    }


# ── Batch ASIN Management ─────────────────────────────────────────────────────

class BatchRequest(BaseModel):
    asins: list[str] = Field(..., min_length=1, max_length=50)
    keyword: str = ""
    platform: str = "amazon"
    top_n: int = 10


@router.post("/batch")
async def create_batch(req: BatchRequest) -> dict:
    """Create a batch job for multiple ASINs.

    Each ASIN gets its own scrape job enqueued into the pipeline.
    Progress is tracked per-ASIN within the batch.
    """
    batch = batch_manager.create_batch(req.asins, req.keyword)

    # Enqueue a scrape job per ASIN
    import uuid

    platform = Platform(req.platform) if req.platform in Platform.__members__ else Platform.amazon
    for task in batch.asins:
        job_id = str(uuid.uuid4())
        store.create(job_id)
        job_req = JobRequest(
            query=task.asin,
            platform=platform,
            top_n=req.top_n,
        )
        await runner.enqueue(job_id, job_req)
        batch_manager.update_asin_status(
            batch.batch_id, task.asin, status="scraping", job_id=job_id,
        )
        logger.info("Batch %s: enqueued ASIN %s as job %s", batch.batch_id, task.asin, job_id)

    batch.status = batch_manager.get_batch(batch.batch_id).status  # type: ignore
    return {
        "batch_id": batch.batch_id,
        "total": batch.total,
        "status": "running",
        "jobs": [
            {"asin": t.asin, "job_id": t.job_id}
            for t in batch_manager.get_batch(batch.batch_id).asins  # type: ignore
        ],
    }


@router.get("/batch/{batch_id}")
async def get_batch(batch_id: str) -> dict:
    """Get batch job status."""
    batch = batch_manager.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found")
    return batch_manager.get_aggregate_report(batch_id)


@router.get("/batch")
async def list_batches() -> dict:
    """List all batch jobs."""
    batches = batch_manager.list_batches()
    return {
        "total": len(batches),
        "batches": [
            {
                "batch_id": b.batch_id,
                "keyword": b.keyword,
                "total": b.total,
                "completed": b.completed_count,
                "status": b.status.value,
            }
            for b in batches
        ],
    }


# ── A/B Test Tracking ──────────────────────────────────────────────────────────

class CreateTestRequest(BaseModel):
    asin: str
    test_name: str
    hypothesis: str
    primary_metric: str = "ctr"
    duration_days: int = 14


class RecordResultsRequest(BaseModel):
    variant_name: str
    metrics: dict[str, float]
    sample_size: int = 0


class CompleteTestRequest(BaseModel):
    winner: str = ""
    confidence_level: float = 0.0
    lift_pct: float = 0.0
    notes: str = ""


@router.post("/ab-tests")
async def create_ab_test(req: CreateTestRequest) -> dict:
    """Create a new A/B test plan."""
    metric = TestMetric(req.primary_metric) if req.primary_metric in TestMetric.__members__ else TestMetric.ctr
    test = ab_tracker.create_test(
        asin=req.asin,
        test_name=req.test_name,
        hypothesis=req.hypothesis,
        primary_metric=metric,
        duration_days=req.duration_days,
    )
    return {"test_id": test.test_id, "status": test.status.value}


@router.post("/ab-tests/{test_id}/start")
async def start_ab_test(test_id: str) -> dict:
    """Start an A/B test."""
    test = ab_tracker.start_test(test_id)
    if test is None:
        raise HTTPException(status_code=404, detail=f"Test '{test_id}' not found")
    return {"test_id": test.test_id, "status": test.status.value}


@router.post("/ab-tests/{test_id}/results")
async def record_ab_results(test_id: str, req: RecordResultsRequest) -> dict:
    """Record metrics for a test variant."""
    test = ab_tracker.record_results(test_id, req.variant_name, req.metrics, req.sample_size)
    if test is None:
        raise HTTPException(status_code=404, detail=f"Test '{test_id}' not found")
    return {"test_id": test.test_id, "status": "results_recorded"}


@router.post("/ab-tests/{test_id}/complete")
async def complete_ab_test(test_id: str, req: CompleteTestRequest) -> dict:
    """Complete an A/B test with results."""
    test = ab_tracker.complete_test(
        test_id, winner=req.winner,
        confidence_level=req.confidence_level,
        lift_pct=req.lift_pct, notes=req.notes,
    )
    if test is None:
        raise HTTPException(status_code=404, detail=f"Test '{test_id}' not found")
    return {"test_id": test.test_id, "status": test.status.value, "winner": test.winner}


@router.get("/ab-tests")
async def list_ab_tests(asin: str = "", status: str = "") -> dict:
    """List A/B tests, optionally filtered."""
    status_filter = TestStatus(status) if status and status in TestStatus.__members__ else None
    tests = ab_tracker.list_tests(asin=asin or None, status=status_filter)
    return {
        "total": len(tests),
        "tests": [
            {
                "test_id": t.test_id,
                "asin": t.asin,
                "test_name": t.test_name,
                "status": t.status.value,
                "winner": t.winner,
                "lift_pct": t.lift_pct,
            }
            for t in tests
        ],
    }


@router.get("/ab-tests/{asin}/insights")
async def ab_test_insights(asin: str) -> dict:
    """Get aggregated A/B test insights for an ASIN."""
    return ab_tracker.get_insights(asin)


# ── Agent Signal Bus ───────────────────────────────────────────────────────────

class EmitSignalRequest(BaseModel):
    signal_type: str
    source_agent: str
    payload: dict = {}
    asin: str = ""
    job_id: str = ""


@router.post("/signals/emit")
async def emit_signal(req: EmitSignalRequest) -> dict:
    """Emit a signal from one agent to the next."""
    try:
        sig_type = SignalType(req.signal_type)
        source = AgentRole(req.source_agent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    signal = signal_bus.emit(sig_type, source, req.payload, req.asin, req.job_id)
    return {
        "signal_id": signal.signal_id,
        "source": signal.source_agent.value,
        "target": signal.target_agent.value,
        "type": signal.signal_type.value,
    }


@router.get("/signals/pending/{agent}")
async def pending_signals(agent: str) -> dict:
    """Get pending signals for an agent."""
    try:
        agent_role = AgentRole(agent)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent}")

    signals = signal_bus.peek(agent_role)
    return {
        "agent": agent,
        "pending": len(signals),
        "signals": [
            {
                "signal_id": s.signal_id,
                "type": s.signal_type.value,
                "source": s.source_agent.value,
                "asin": s.asin,
                "created_at": s.created_at,
            }
            for s in signals
        ],
    }


@router.post("/signals/consume/{agent}")
async def consume_signals(agent: str) -> dict:
    """Consume pending signals for an agent."""
    try:
        agent_role = AgentRole(agent)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent}")

    signals = signal_bus.consume(agent_role)
    return {
        "agent": agent,
        "consumed": len(signals),
        "signals": [
            {
                "signal_id": s.signal_id,
                "type": s.signal_type.value,
                "source": s.source_agent.value,
                "payload": s.payload,
                "asin": s.asin,
            }
            for s in signals
        ],
    }


@router.get("/signals/loop-status")
async def loop_status() -> dict:
    """Get the 4-agent loop status."""
    return signal_bus.get_loop_status()
