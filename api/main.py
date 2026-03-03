"""FastAPI application entry point for SuperScrape API."""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.benchmarks import router as benchmarks_router
from api.routes.exports import router as exports_router
from api.routes.jobs import router as jobs_router
from api.routes.monitor import router as monitor_router
from api.routes.reports import router as reports_router
from api.routes.uploads import router as uploads_router
from api.services.job_runner import runner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the JobRunner worker on startup; stop it on shutdown."""
    await runner.start()
    logger.info("SuperScrape API ready")
    yield
    await runner.stop()
    logger.info("SuperScrape API shut down")


app = FastAPI(
    title="SuperScrape API",
    description=(
        "Web scraping + AI visual intelligence — scrape, analyze, and report "
        "on competitor product images via a simple REST + SSE API."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(jobs_router)
app.include_router(reports_router)
app.include_router(uploads_router)
app.include_router(exports_router)
app.include_router(monitor_router)
app.include_router(benchmarks_router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Quick liveness check."""
    return {"status": "ok"}
