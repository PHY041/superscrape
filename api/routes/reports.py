"""Report serving routes: HTML and PDF."""

from __future__ import annotations

import os
import uuid as uuid_mod
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from api.models.api_models import PipelineStep
from api.services.job_store import store


def _validate_job_id(job_id: str) -> None:
    """Reject non-UUID job IDs to prevent path traversal."""
    try:
        uuid_mod.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")


router = APIRouter(prefix="/reports", tags=["reports"])

_REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", "/tmp/superscrape_reports"))


def _find_report_file(job_id: str, suffix: str) -> Path:
    """Locate the report file for a given job_id and file suffix (.html or .pdf)."""
    if not _REPORTS_DIR.exists():
        raise HTTPException(status_code=404, detail="Reports directory not found")

    matches = list(_REPORTS_DIR.glob(f"{job_id}_*{suffix}"))
    if not matches:
        raise HTTPException(
            status_code=404,
            detail=f"No {suffix} report found for job '{job_id}'",
        )
    # Return the most recently created file (there should only be one)
    return sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def _assert_job_done(job_id: str) -> None:
    """Raise 404 if the job is unknown, 202 if it is still running."""
    status = store.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    if status.step not in (PipelineStep.done, PipelineStep.failed):
        raise HTTPException(
            status_code=409,
            detail=f"Job '{job_id}' is still running (step: {status.step})",
        )
    if status.step == PipelineStep.failed:
        raise HTTPException(
            status_code=500,
            detail=f"Job '{job_id}' failed: {status.error}",
        )


@router.get("/{job_id}/html", response_class=HTMLResponse)
async def get_html_report(job_id: str) -> HTMLResponse:
    """Return the self-contained HTML report for a completed job."""
    _validate_job_id(job_id)
    _assert_job_done(job_id)
    report_path = _find_report_file(job_id, ".html")
    html_content = report_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html_content, status_code=200)


@router.get("/{job_id}/pdf")
async def get_pdf_report(job_id: str) -> FileResponse:
    """Return the PDF report for a completed job."""
    _validate_job_id(job_id)
    _assert_job_done(job_id)
    pdf_path = _find_report_file(job_id, ".pdf")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"superscrape_report_{job_id}.pdf",
    )
