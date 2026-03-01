"""Async pipeline orchestrator for Scout jobs."""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from api.models.api_models import JobRequest, PipelineStep, Platform, ProgressEvent
from api.services.job_store import store

logger = logging.getLogger(__name__)

_REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", "/tmp/superscrape_reports"))
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="camoufox")

# ── Lazy Scraper Registry ─────────────────────────────────────────────────────
# New platform = add one entry here + one file in superscrape/sites/
_SCRAPER_PATHS: dict[Platform, str] = {
    Platform.amazon: "superscrape.sites.amazon.Amazon",
    Platform.walmart: "superscrape.sites.walmart.Walmart",
    Platform.ebay: "superscrape.sites.ebay.Ebay",
    Platform.etsy: "superscrape.sites.etsy.Etsy",
    Platform.shopee: "superscrape.sites.shopee.Shopee",
    Platform.tiktok_shop: "superscrape.sites.tiktok_shop.TikTokShop",
}

_PLATFORM_LABELS: dict[Platform, str] = {
    Platform.amazon: "Amazon",
    Platform.walmart: "Walmart",
    Platform.ebay: "eBay",
    Platform.etsy: "Etsy",
    Platform.shopee: "Shopee",
    Platform.tiktok_shop: "TikTok Shop",
}


def _get_scraper(platform: Platform):
    """Lazy-import and return the scraper class for the given platform."""
    path = _SCRAPER_PATHS.get(platform)
    if not path:
        raise ValueError(f"Unsupported platform: {platform.value}")

    module_path, class_name = path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _emit(job_id: str, step: PipelineStep, message: str, progress: int, **detail) -> None:
    """Helper to push a ProgressEvent to the job store."""
    event = ProgressEvent(
        step=step,
        message=message,
        progress=progress,
        detail=detail,
    )
    store.update(job_id, event)
    logger.info("[%s] %d%% — %s", job_id, progress, message)


def _run_pipeline_sync(job_id: str, req: JobRequest) -> None:
    """Synchronous pipeline executed inside ThreadPoolExecutor.

    Runs in a worker thread so Camoufox blocking I/O does not block the event loop.
    """
    from api.reports.html_builder import build_html_report
    from api.reports.pdf_exporter import export_pdf
    from superscrape.analyzers.vision import batch_analyze_all_images
    from superscrape.reporters.visual_report import aggregate_report

    platform = req.platform
    platform_label = _PLATFORM_LABELS.get(platform, platform.value.title())
    pval = platform.value  # include in every event for SSE reconnect

    try:
        # ── Step 1: Scraping ───────────────────────────────────────────────
        _emit(job_id, PipelineStep.scraping, f"Starting {platform_label} scrape...", 5, platform=pval)

        scraper = _get_scraper(platform)
        keyword = req.query
        products = scraper.search_images(keyword, top_n=req.top_n)

        _emit(
            job_id,
            PipelineStep.scraping,
            f"Scraped {len(products)} products from {platform_label}",
            35,
            product_count=len(products),
            platform=pval,
        )

        # ── Step 2: Vision Analysis ────────────────────────────────────────
        _emit(job_id, PipelineStep.analyzing, "Analyzing product images with GPT Vision...", 40, platform=pval)
        analyses = batch_analyze_all_images(products, max_images_per_product=7)
        _emit(
            job_id,
            PipelineStep.analyzing,
            f"Analyzed {len(analyses)} images",
            70,
            analyses_count=len(analyses),
            platform=pval,
        )

        # ── Step 3: Optional Seedream ──────────────────────────────────────
        lifestyle_images: list[str] = []
        if req.generate_lifestyle:
            from api.services.seedream import generate_lifestyle_images

            _emit(job_id, PipelineStep.generating, "Generating Seedream lifestyle images...", 72, platform=pval)
            lifestyle_images = generate_lifestyle_images(products, max_products=5)
            _emit(
                job_id,
                PipelineStep.generating,
                f"Generated {len(lifestyle_images)} lifestyle images",
                85,
                lifestyle_count=len(lifestyle_images),
                platform=pval,
            )

        # ── Step 4: Report ─────────────────────────────────────────────────
        _emit(job_id, PipelineStep.building_report, "Building category report...", 88, platform=pval)
        report = aggregate_report(keyword, products, analyses, platform=platform.value)

        # Ensure output directory exists
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
        safe_keyword = "".join(c if c.isalnum() else "_" for c in keyword)[:40]
        base_name = f"{job_id}_{safe_keyword}_{timestamp}"

        html_path = _REPORTS_DIR / f"{base_name}.html"
        pdf_path = _REPORTS_DIR / f"{base_name}.pdf"

        html_content = build_html_report(
            report=report,
            products=products,
            analyses=analyses,
            lifestyle_images=lifestyle_images,
            language=req.language,
        )
        html_path.write_text(html_content, encoding="utf-8")

        _emit(job_id, PipelineStep.building_report, "Exporting PDF...", 93, platform=pval)
        try:
            export_pdf(str(html_path), str(pdf_path))
            pdf_url = f"/reports/{job_id}/pdf"
        except Exception as exc:
            logger.warning("PDF export failed for job %s: %s", job_id, exc)
            pdf_url = None

        # ── Step 5: Strategy Generation ──────────────────────────────
        _emit(job_id, PipelineStep.building_report, "Generating action plan & A/B tests...", 95, platform=pval)

        action_plan: list = []
        ab_tests: list = []
        seasonal_alerts: list = []
        review_insights: dict = {}
        story_arc: dict = {}
        try:
            from api.services.review_analyzer import analyze_reviews
            from api.services.seasonal import get_seasonal_alerts
            from api.services.story_arc import design_story_arc
            from api.services.strategy_gen import generate_ab_tests, generate_action_plan

            review_insights = analyze_reviews(products)
            action_plan = generate_action_plan(report, products)
            ab_tests = generate_ab_tests(report, products)
            seasonal_alerts = get_seasonal_alerts(keyword)
            story_arc = design_story_arc(report, products, review_insights)
            logger.info(
                "Strategy gen done: %d phases, %d tests, %d alerts, %d pain points, story arc=%s",
                len(action_plan), len(ab_tests), len(seasonal_alerts),
                len(review_insights.get("pain_points", [])),
                story_arc.get("story_arc_name", "none"),
            )
        except Exception as exc:
            logger.warning("Strategy generation failed (non-fatal): %s", exc)

        _emit(job_id, PipelineStep.building_report, "Finalising report...", 98, platform=pval)

        # Persist structured data for the /data endpoint
        store.save_data(
            job_id,
            products=products,
            analyses=analyses,
            report=report,
            action_plan=action_plan,
            ab_tests=ab_tests,
            seasonal_alerts=seasonal_alerts,
            review_insights=review_insights,
            story_arc=story_arc,
        )

        report_url = f"/reports/{job_id}/html"
        store.mark_done(job_id, report_url=report_url, pdf_url=pdf_url)

    except Exception as exc:
        logger.exception("Pipeline error for job %s", job_id)
        store.mark_failed(job_id, error=str(exc))


class JobRunner:
    """Manages the asyncio queue and thread-pool dispatch for pipeline jobs."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[str, JobRequest]] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the background worker. Called on app startup."""
        self._task = asyncio.create_task(self._worker(), name="job-runner-worker")
        logger.info("JobRunner worker started")

    async def stop(self) -> None:
        """Gracefully stop the background worker. Called on app shutdown."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        _executor.shutdown(wait=False)
        logger.info("JobRunner worker stopped")

    async def enqueue(self, job_id: str, req: JobRequest) -> None:
        """Add a job to the processing queue."""
        await self._queue.put((job_id, req))
        logger.info("Enqueued job %s", job_id)

    async def _worker(self) -> None:
        """Continuously pull jobs from the queue and run them in the executor."""
        loop = asyncio.get_running_loop()
        while True:
            job_id, req = await self._queue.get()
            try:
                await loop.run_in_executor(_executor, _run_pipeline_sync, job_id, req)
            except Exception as exc:
                logger.exception("Unhandled error dispatching job %s", job_id)
                store.mark_failed(job_id, error=str(exc))
            finally:
                self._queue.task_done()


# Module-level singleton — imported by main.py lifespan
runner = JobRunner()
