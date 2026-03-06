"""Listing import routes: import pre-generated listing-gen projects."""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/listing", tags=["listing"])

_REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", "/tmp/superscrape_reports"))


class ImportRequest(BaseModel):
    project_dir: str


@router.post("/jobs/{job_id}/import")
async def import_listing_project(job_id: str, req: ImportRequest) -> dict:
    """Import an existing listing-gen project into a superscrape job.

    Reads brief.json, listing_text.json, and copies generated images
    so they're accessible via the standard reports/static routes.
    """
    src = Path(req.project_dir)
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Project directory not found: {req.project_dir}")

    output_dir = src / "output"

    # Read brief.json
    brief: dict = {}
    brief_path = src / "brief.json"
    if brief_path.exists():
        brief = json.loads(brief_path.read_text(encoding="utf-8"))

    # Read listing_text.json
    listing_text: dict = {}
    lt_path = output_dir / "listing_text.json"
    if lt_path.exists():
        listing_text = json.loads(lt_path.read_text(encoding="utf-8"))

    # Read compliance_report.json
    compliance: dict = {}
    cr_path = output_dir / "compliance_report.json"
    if cr_path.exists():
        compliance = json.loads(cr_path.read_text(encoding="utf-8"))

    # Copy generated images to REPORTS_DIR/{job_id}/images/
    images_dest = _REPORTS_DIR / job_id / "images"
    images_dest.mkdir(parents=True, exist_ok=True)

    image_paths: list[dict[str, str]] = []
    if output_dir.exists():
        for img_file in sorted(output_dir.glob("slot_*.png")):
            dst = images_dest / img_file.name
            shutil.copy2(img_file, dst)
            image_paths.append({
                "filename": img_file.name,
                "path": f"/reports/{job_id}/images/{img_file.name}",
            })

    logger.info("Imported listing project %s → job %s (%d images)", req.project_dir, job_id, len(image_paths))

    return {
        "job_id": job_id,
        "brief": brief,
        "listing_text": listing_text,
        "compliance": compliance,
        "images": image_paths,
        "images_count": len(image_paths),
    }
