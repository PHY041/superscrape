"""Export routes: ZIP download of job results (images, text, report)."""

from __future__ import annotations

import io
import json
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.models.api_models import PipelineStep
from api.services.job_store import store

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/{job_id}")
async def export_job(job_id: str) -> StreamingResponse:
    """Export all job results as a ZIP file.

    Includes:
    - report.json — full competitor intelligence report
    - listing_text.json — generated listing text (if available)
    - action_plan.json — dynamic action plan
    - ab_tests.json — A/B test suggestions
    - seasonal_alerts.json — seasonal event alerts
    - products.json — scraped product data
    - analyses.json — image analysis results
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

    # Build ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Report
        report_dict = data.report.model_dump() if hasattr(data.report, "model_dump") else data.report
        zf.writestr("report.json", json.dumps(report_dict, indent=2, ensure_ascii=False))

        # Products
        products_list = [p.model_dump() for p in data.products]
        zf.writestr("products.json", json.dumps(products_list, indent=2, ensure_ascii=False))

        # Analyses
        analyses_list = [a.model_dump() for a in data.analyses]
        zf.writestr("analyses.json", json.dumps(analyses_list, indent=2, ensure_ascii=False))

        # Action plan
        if data.action_plan:
            zf.writestr("action_plan.json", json.dumps(data.action_plan, indent=2, ensure_ascii=False))

        # A/B tests
        if data.ab_tests:
            zf.writestr("ab_tests.json", json.dumps(data.ab_tests, indent=2, ensure_ascii=False))

        # Seasonal alerts
        if data.seasonal_alerts:
            zf.writestr("seasonal_alerts.json", json.dumps(data.seasonal_alerts, indent=2, ensure_ascii=False))

        # Review insights
        if data.review_insights:
            zf.writestr("review_insights.json", json.dumps(data.review_insights, indent=2, ensure_ascii=False))

        # Story arc
        if data.story_arc:
            zf.writestr("story_arc.json", json.dumps(data.story_arc, indent=2, ensure_ascii=False))

        # Listing text (if generated)
        if hasattr(data, "listing_text") and data.listing_text:
            zf.writestr("listing_text.json", json.dumps(data.listing_text, indent=2, ensure_ascii=False))

        # Benchmark data
        if hasattr(data, "benchmark") and data.benchmark:
            zf.writestr("benchmark.json", json.dumps(data.benchmark, indent=2, ensure_ascii=False))

    buf.seek(0)

    keyword = ""
    if hasattr(data.report, "keyword"):
        keyword = data.report.keyword.replace(" ", "_")[:30]
    filename = f"superscrape_{keyword}_{job_id[:8]}.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
