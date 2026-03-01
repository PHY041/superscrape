"""Competitor change monitoring — tracks listing changes over time.

Periodically scrapes competitor ASINs and detects changes in:
- Title, price, images, A+ content
- Rating/review count shifts
- New image additions or removals

Requires a scheduling system (cron/APScheduler) for daily runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


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

    Current status: STUB — provides interface and in-memory storage.
    Production implementation needs:
    1. Persistent storage (Supabase/SQLite) for snapshots
    2. APScheduler or cron for periodic scraping
    3. Notification system (email/webhook) for alerts
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, list[ListingSnapshot]] = {}
        self._changes: list[ListingChange] = []
        self._config = MonitorConfig()

    @property
    def is_active(self) -> bool:
        return self._config.active

    def add_asin(self, asin: str) -> None:
        """Add an ASIN to the monitoring watchlist."""
        if asin not in self._config.asins:
            self._config.asins.append(asin)
            logger.info("Added ASIN %s to monitor watchlist", asin)

    def remove_asin(self, asin: str) -> None:
        """Remove an ASIN from the watchlist."""
        if asin in self._config.asins:
            self._config.asins.remove(asin)

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
        }


# Module-level singleton
monitor = CompetitorMonitor()
