"""Competitor change monitoring — tracks listing changes over time.

Periodically scrapes competitor ASINs and detects changes in:
- Title, price, images, A+ content
- Rating/review count shifts
- New image additions or removals

Uses asyncio background task for periodic scheduling.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_PERSIST_DIR = Path(os.environ.get("MONITOR_DIR", "/tmp/superscrape_monitor"))


@dataclass
class ListingSnapshot:
    """Point-in-time snapshot of a listing's key attributes."""

    asin: str
    captured_at: str = ""
    title: str = ""
    price: str = ""
    rating: float = 0.0
    reviews_count: int = 0
    image_count: int = 0
    image_hash: str = ""  # hash of sorted image URLs for quick diff
    has_aplus: bool = False
    brand: str = ""


@dataclass
class ListingChange:
    """A detected change between two snapshots."""

    asin: str
    field: str
    old_value: str
    new_value: str
    detected_at: str = ""
    severity: str = "low"  # low | medium | high


@dataclass
class MonitorConfig:
    """Configuration for competitor monitoring."""

    asins: list[str] = field(default_factory=list)
    check_interval_hours: int = 24
    notify_on_change: bool = True
    active: bool = False


class CompetitorMonitor:
    """Track competitor listing changes over time.

    Provides persistent watchlist, snapshot diffing, and async scheduling
    for periodic scraping of competitor ASINs.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, list[ListingSnapshot]] = {}
        self._changes: list[ListingChange] = []
        self._config = MonitorConfig()
        self._scheduler_task: asyncio.Task | None = None
        self._load_persisted()

    def _load_persisted(self) -> None:
        """Load watchlist and snapshots from disk."""
        config_path = _PERSIST_DIR / "config.json"
        if config_path.exists():
            try:
                raw = json.loads(config_path.read_text(encoding="utf-8"))
                self._config.asins = raw.get("asins", [])
                self._config.active = raw.get("active", False)
                self._config.check_interval_hours = raw.get("check_interval_hours", 24)
                logger.info("Loaded monitor config: %d ASINs", len(self._config.asins))
            except Exception as e:
                logger.warning("Failed to load monitor config: %s", e)

        snapshots_path = _PERSIST_DIR / "snapshots.json"
        if snapshots_path.exists():
            try:
                raw = json.loads(snapshots_path.read_text(encoding="utf-8"))
                for asin, snaps in raw.items():
                    self._snapshots[asin] = [ListingSnapshot(**s) for s in snaps]
                logger.info("Loaded %d ASIN snapshot histories", len(self._snapshots))
            except Exception as e:
                logger.warning("Failed to load snapshots: %s", e)

    def _persist(self) -> None:
        """Save config and snapshots to disk."""
        try:
            _PERSIST_DIR.mkdir(parents=True, exist_ok=True)

            config_path = _PERSIST_DIR / "config.json"
            config_path.write_text(json.dumps({
                "asins": self._config.asins,
                "active": self._config.active,
                "check_interval_hours": self._config.check_interval_hours,
            }), encoding="utf-8")

            snapshots_path = _PERSIST_DIR / "snapshots.json"
            serialized = {}
            for asin, snaps in self._snapshots.items():
                serialized[asin] = [
                    {"asin": s.asin, "captured_at": s.captured_at, "title": s.title,
                     "price": s.price, "rating": s.rating, "reviews_count": s.reviews_count,
                     "image_count": s.image_count, "image_hash": s.image_hash,
                     "has_aplus": s.has_aplus, "brand": s.brand}
                    for s in snaps[-20:]  # keep last 20 snapshots per ASIN
                ]
            snapshots_path.write_text(json.dumps(serialized), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to persist monitor data: %s", e)

    @property
    def is_active(self) -> bool:
        return self._config.active

    def add_asin(self, asin: str) -> None:
        """Add an ASIN to the monitoring watchlist."""
        if asin not in self._config.asins:
            self._config.asins.append(asin)
            self._persist()
            logger.info("Added ASIN %s to monitor watchlist", asin)

    def remove_asin(self, asin: str) -> None:
        """Remove an ASIN from the watchlist."""
        if asin in self._config.asins:
            self._config.asins.remove(asin)
            self._persist()

    def take_snapshot(self, asin: str, product_data: dict) -> ListingSnapshot:
        """Create a snapshot from current product data."""
        image_urls = sorted(
            img.get("hi_res_url", img.get("url", ""))
            for img in product_data.get("images", [])
        )
        image_hash = hashlib.md5(
            json.dumps(image_urls).encode()
        ).hexdigest()[:12]

        snapshot = ListingSnapshot(
            asin=asin,
            captured_at=datetime.now(tz=timezone.utc).isoformat(),
            title=product_data.get("title", ""),
            price=product_data.get("price", ""),
            rating=product_data.get("rating", 0.0),
            reviews_count=product_data.get("reviews_count", 0),
            image_count=len(product_data.get("images", [])),
            image_hash=image_hash,
            has_aplus=len(product_data.get("aplus_images", [])) > 0,
            brand=product_data.get("brand", ""),
        )

        if asin not in self._snapshots:
            self._snapshots[asin] = []
        self._snapshots[asin].append(snapshot)
        self._persist()

        return snapshot

    def detect_changes(self, asin: str) -> list[ListingChange]:
        """Compare latest snapshot against previous to detect changes."""
        history = self._snapshots.get(asin, [])
        if len(history) < 2:
            return []

        prev = history[-2]
        curr = history[-1]
        changes: list[ListingChange] = []
        now = datetime.now(tz=timezone.utc).isoformat()

        if prev.title != curr.title:
            changes.append(ListingChange(
                asin=asin, field="title",
                old_value=prev.title[:100], new_value=curr.title[:100],
                detected_at=now, severity="high",
            ))

        if prev.price != curr.price:
            changes.append(ListingChange(
                asin=asin, field="price",
                old_value=prev.price, new_value=curr.price,
                detected_at=now, severity="medium",
            ))

        if prev.image_hash != curr.image_hash:
            changes.append(ListingChange(
                asin=asin, field="images",
                old_value=f"{prev.image_count} images",
                new_value=f"{curr.image_count} images",
                detected_at=now, severity="high",
            ))

        if prev.has_aplus != curr.has_aplus:
            changes.append(ListingChange(
                asin=asin, field="aplus_content",
                old_value=str(prev.has_aplus),
                new_value=str(curr.has_aplus),
                detected_at=now, severity="high",
            ))

        review_delta = curr.reviews_count - prev.reviews_count
        if abs(review_delta) > 10:
            changes.append(ListingChange(
                asin=asin, field="reviews_count",
                old_value=str(prev.reviews_count),
                new_value=f"{curr.reviews_count} ({review_delta:+d})",
                detected_at=now, severity="low",
            ))

        self._changes.extend(changes)
        return changes

    def get_history(self, asin: str) -> list[ListingSnapshot]:
        """Return all snapshots for an ASIN."""
        return self._snapshots.get(asin, [])

    def get_all_changes(self) -> list[ListingChange]:
        """Return all detected changes across all ASINs."""
        return self._changes

    def get_watchlist(self) -> list[str]:
        """Return the current ASIN watchlist."""
        return self._config.asins

    def get_status(self) -> dict:
        """Return monitor status summary."""
        return {
            "active": self._config.active,
            "watched_asins": len(self._config.asins),
            "total_snapshots": sum(len(v) for v in self._snapshots.values()),
            "total_changes_detected": len(self._changes),
            "check_interval_hours": self._config.check_interval_hours,
            "scheduler_running": self._scheduler_task is not None
            and not self._scheduler_task.done(),
        }

    async def activate(self, interval_hours: int | None = None) -> dict:
        """Activate periodic monitoring scheduler."""
        if interval_hours is not None:
            self._config.check_interval_hours = interval_hours
        self._config.active = True
        self._persist()

        if self._scheduler_task is None or self._scheduler_task.done():
            self._scheduler_task = asyncio.create_task(self._scheduler_loop())
            logger.info(
                "Monitor scheduler started — interval %dh, %d ASINs",
                self._config.check_interval_hours,
                len(self._config.asins),
            )

        return self.get_status()

    async def deactivate(self) -> dict:
        """Stop the monitoring scheduler."""
        self._config.active = False
        self._persist()

        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None
            logger.info("Monitor scheduler stopped")

        return self.get_status()

    async def _scheduler_loop(self) -> None:
        """Background loop that scrapes watched ASINs at the configured interval."""
        while self._config.active:
            try:
                await self._run_check_cycle()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Monitor check cycle failed: %s", e)

            sleep_secs = self._config.check_interval_hours * 3600
            try:
                await asyncio.sleep(sleep_secs)
            except asyncio.CancelledError:
                raise

    async def _run_check_cycle(self) -> None:
        """Scrape each watched ASIN and detect changes."""
        if not self._config.asins:
            return

        logger.info("Monitor cycle: checking %d ASINs", len(self._config.asins))

        from concurrent.futures import ThreadPoolExecutor

        from superscrape.sites.amazon import AmazonScraper

        loop = asyncio.get_running_loop()
        for asin in list(self._config.asins):
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    product = await loop.run_in_executor(
                        pool, lambda a=asin: AmazonScraper().product(a),
                    )
                if product is None:
                    logger.warning("Monitor: failed to scrape ASIN %s", asin)
                    continue

                product_data = product.model_dump() if hasattr(product, "model_dump") else {}
                self.take_snapshot(asin, product_data)
                changes = self.detect_changes(asin)
                if changes:
                    logger.info(
                        "Monitor: %d changes detected for ASIN %s",
                        len(changes), asin,
                    )
            except Exception as e:
                logger.warning("Monitor: error checking ASIN %s: %s", asin, e)

        logger.info("Monitor cycle complete")


# Module-level singleton
monitor = CompetitorMonitor()
