"""Job management routes: create, poll, and stream SSE progress."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.models.api_models import JobRequest, JobStatus, PipelineStep
from api.services.job_runner import runner
from api.services.job_store import store

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", status_code=202, response_model=JobStatus)
async def create_job(req: JobRequest) -> JobStatus:
    """Create a new scraping job and enqueue it for processing.

    Returns HTTP 202 Accepted with initial JobStatus.
    Poll GET /jobs/{job_id} or stream GET /jobs/{job_id}/stream for updates.
    """
    job_id = str(uuid.uuid4())
    status = store.create(job_id)
    await runner.enqueue(job_id, req)
    return status


@router.get("/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    """Poll the current status of a job."""
    status = store.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return status


@router.get("/{job_id}/stream")
async def stream_job(job_id: str) -> StreamingResponse:
    """Stream real-time progress events via Server-Sent Events (SSE).

    Connect once; the stream closes automatically when the job completes or fails.

    Event format:
        data: {"step": "...", "message": "...", "progress": N, "detail": {}}
    """
    if store.get(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    async def _event_generator():
        try:
            async for event in store.subscribe(job_id):
                payload = json.dumps(event.model_dump())
                yield f"data: {payload}\n\n"
                # Close the stream once the job has terminated
                if event.step in (PipelineStep.done, PipelineStep.failed):
                    break
        except Exception:
            yield "data: {\"step\": \"failed\", \"message\": \"Stream error\", \"progress\": 0, \"detail\": {}}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
