"""Job management routes: create, poll, stream, and generate listing assets."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.models.api_models import JobRequest, JobStatus, PipelineStep
from api.services.job_runner import runner
from api.services.job_store import store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(limit: int = 50) -> dict:
    """List recent jobs, newest first."""
    jobs = store.list_jobs(limit=limit)
    return {
        "total": len(jobs),
        "jobs": [j.model_dump() for j in jobs],
    }


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


@router.get("/{job_id}/data")
async def get_job_data(job_id: str) -> dict:
    """Return structured product data for frontend consumption.

    Available after the job completes. Returns products, analyses,
    and the aggregated category report.
    """
    status = store.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if status.step != PipelineStep.done:
        raise HTTPException(
            status_code=409,
            detail=f"Job '{job_id}' is not yet complete (current step: {status.step.value})",
        )

    data = store.get_data(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No data stored for job '{job_id}'")

    return {
        "products": [p.model_dump() for p in data.products],
        "analyses": [a.model_dump() for a in data.analyses],
        "report": data.report.model_dump() if hasattr(data.report, "model_dump") else data.report,
        "action_plan": data.action_plan,
        "ab_tests": data.ab_tests,
        "seasonal_alerts": data.seasonal_alerts,
        "review_insights": data.review_insights,
        "story_arc": data.story_arc,
        "benchmark": data.benchmark,
    }


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
            yield 'data: {"step": "failed", "message": "Stream error", "progress": 0, "detail": {}}\n\n'

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Listing generation endpoints ─────────────────────────────────────────────


class GenerateRequest(BaseModel):
    """Request body for listing generation."""

    product_photos: list[str] = Field(
        default_factory=list,
        description="Paths to uploaded product photos",
    )
    brand_name: str = Field(default="", description="Brand name for the listing")
    brand_colors: list[str] = Field(
        default_factory=list,
        description="Brand colors as hex codes (e.g. ['#FF0000', '#000000'])",
    )


@router.post("/{job_id}/generate")
async def generate_listing(job_id: str, req: GenerateRequest) -> dict:
    """Generate listing images and text from a completed scrape job.

    Requires the job to be complete. Uses the scrape results + user product photos
    to auto-generate a 7-image listing strategy and Amazon listing text.

    Steps:
    1. Auto-generate ProjectConfig via GPT-5.2 based on competitor intel
    2. Run listing_gen pipeline for image generation
    3. Generate listing text (title, bullets, description)
    4. Return all results
    """
    status = store.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if status.step != PipelineStep.done:
        raise HTTPException(
            status_code=409,
            detail=f"Job '{job_id}' is not yet complete (current step: {status.step.value})",
        )

    data = store.get_data(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No data stored for job '{job_id}'")

    from api.services.listing_service import (
        auto_generate_config,
        generate_listing_text,
        run_listing_generation,
    )

    report = data.report
    products = data.products

    # Step 1: Auto-generate config
    logger.info("Generating listing config for job %s...", job_id)
    config = auto_generate_config(
        keyword=report.keyword if hasattr(report, "keyword") else "",
        products=products,
        report=report,
        product_photos=req.product_photos,
        brand_name=req.brand_name,
        brand_colors=req.brand_colors,
    )

    # Step 2: Run image generation pipeline
    logger.info("Running listing image generation for job %s...", job_id)
    gen_results = run_listing_generation(config)

    # Step 3: Generate listing text
    logger.info("Generating listing text for job %s...", job_id)
    listing_text = generate_listing_text(
        keyword=report.keyword if hasattr(report, "keyword") else "",
        products=products,
        report=report,
        brand_name=req.brand_name,
    )

    return {
        "project_id": config.project_id,
        "config": config.model_dump(),
        "image_results": gen_results,
        "listing_text": listing_text,
    }


@router.post("/{job_id}/generate-text")
async def generate_listing_text_only(job_id: str, req: GenerateRequest) -> dict:
    """Generate only listing text (title, bullets, description) without images.

    Faster alternative when product photos aren't available yet.
    """
    status = store.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if status.step != PipelineStep.done:
        raise HTTPException(
            status_code=409,
            detail=f"Job '{job_id}' is not yet complete",
        )

    data = store.get_data(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No data for job '{job_id}'")

    from api.services.listing_service import generate_listing_text

    listing_text = generate_listing_text(
        keyword=data.report.keyword if hasattr(data.report, "keyword") else "",
        products=data.products,
        report=data.report,
        brand_name=req.brand_name,
    )

    return {"listing_text": listing_text}
