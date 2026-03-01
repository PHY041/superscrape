"""File upload routes for product photos."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

router = APIRouter(prefix="/uploads", tags=["uploads"])

_UPLOADS_DIR = Path(os.environ.get("UPLOADS_DIR", "/tmp/superscrape_uploads"))


@router.post("")
async def upload_files(files: list[UploadFile]) -> dict:
    """Upload one or more product photos.

    Returns a list of file paths that can be passed to the generate endpoint.
    Max 10 files, each up to 10MB.
    """
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files allowed")

    upload_id = uuid.uuid4().hex[:8]
    upload_dir = _UPLOADS_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[str] = []

    for file in files:
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail=f"File '{file.filename}' is not an image",
            )

        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"File '{file.filename}' exceeds 10MB limit",
            )

        # Sanitize filename
        ext = Path(file.filename or "photo.jpg").suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            ext = ".jpg"

        safe_name = f"{uuid.uuid4().hex[:8]}{ext}"
        file_path = upload_dir / safe_name
        file_path.write_bytes(content)
        saved_paths.append(str(file_path))

    return {
        "upload_id": upload_id,
        "files": saved_paths,
        "count": len(saved_paths),
    }
