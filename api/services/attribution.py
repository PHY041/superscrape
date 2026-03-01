"""Conversion attribution + ROI dashboard — Agent 4 core capabilities.

Tracks the causal impact of listing image changes on key business metrics.
Provides ROI quantification in three business languages:
1. Cost savings (saved X hours of photography)
2. Revenue impact (Y% conversion lift = $Z more revenue)
3. Competitive advantage (moved from position X to Y)

Requires SP-API integration for real data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger(__name__)


@dataclass
class AttributionWindow:
    """Before/after comparison window for causal attribution."""

    asin: str
    change_date: str  # date when images were updated
    change_description: str = ""
    pre_period_days: int = 14
    post_period_days: int = 14
    pre_metrics: dict[str, float] = field(default_factory=dict)
    post_metrics: dict[str, float] = field(default_factory=dict)
    lift: dict[str, float] = field(default_factory=dict)


@dataclass
class ROISummary:
    """ROI summary in three business languages."""

    asin: str = ""
    period: str = ""

    # Language 1: Cost savings
    photography_hours_saved: float = 0.0
    photography_cost_saved: float = 0.0
    design_iterations_saved: int = 0

    # Language 2: Revenue impact
    conversion_lift_pct: float = 0.0
    estimated_additional_units: int = 0
    estimated_additional_revenue: float = 0.0
    sessions_to_revenue_ratio: float = 0.0

    # Language 3: Competitive advantage
    search_rank_change: int = 0  # positive = improved
    image_quality_percentile: float = 0.0
    competitive_gaps_closed: int = 0


class AttributionEngine:
    """Track conversion attribution and ROI for listing changes.

    Current status: STUB — provides framework and mock data.
    Full implementation requires:
    1. SP-API integration for real business reports
    2. Time-series storage for historical metrics
    3. Statistical significance testing (t-test, Mann-Whitney)
    4. Confounding variable detection (price changes, seasonality)
    """

    def __init__(self) -> None:
        self._windows: list[AttributionWindow] = []
        self._roi_cache: dict[str, ROISummary] = {}

    def create_attribution_window(
        self,
        asin: str,
        change_date: str,
        change_description: str = "",
        pre_period_days: int = 14,
        post_period_days: int = 14,
    ) -> AttributionWindow:
        """Create a before/after attribution window for a listing change.

        Call this when images are updated. After the post-period elapses,
        call `compute_attribution()` to measure impact.
        """
        window = AttributionWindow(
            asin=asin,
            change_date=change_date,
            change_description=change_description,
            pre_period_days=pre_period_days,
            post_period_days=post_period_days,
        )
        self._windows.append(window)
        logger.info(
            "Created attribution window for %s: %s (±%dd)",
            asin, change_date, pre_period_days,
        )
        return window

    def compute_attribution(self, asin: str) -> AttributionWindow | None:
        """Compute attribution for the latest window of an ASIN.

        Requires SP-API data for both pre and post periods.
        Returns the window with computed lift metrics.
        """
        windows = [w for w in self._windows if w.asin == asin]
        if not windows:
            return None

        window = windows[-1]

        # STUB: In production, fetch real metrics from SP-API
        logger.info(
            "Attribution computation for %s — SP-API not connected, returning placeholder",
            asin,
        )
        window.pre_metrics = {
            "sessions": 0,
            "conversion_rate": 0.0,
            "units_ordered": 0,
            "revenue": 0.0,
        }
        window.post_metrics = {
            "sessions": 0,
            "conversion_rate": 0.0,
            "units_ordered": 0,
            "revenue": 0.0,
        }
        window.lift = {k: 0.0 for k in window.pre_metrics}

        return window

    def compute_roi(self, asin: str) -> ROISummary:
        """Compute ROI summary in three business languages."""
        # STUB: In production, aggregate real data
        logger.info("ROI computation for %s — returning placeholder", asin)

        summary = ROISummary(
            asin=asin,
            period="stub",
            photography_hours_saved=0,
            photography_cost_saved=0,
            conversion_lift_pct=0,
            estimated_additional_units=0,
            estimated_additional_revenue=0,
        )
        self._roi_cache[asin] = summary
        return summary

    def get_dashboard_data(self, asins: list[str] | None = None) -> dict:
        """Return ROI dashboard data for display.

        Aggregates attribution windows and ROI summaries.
        """
        if asins:
            windows = [w for w in self._windows if w.asin in asins]
        else:
            windows = self._windows

        return {
            "total_asins_tracked": len(set(w.asin for w in windows)),
            "total_attribution_windows": len(windows),
            "windows": [
                {
                    "asin": w.asin,
                    "change_date": w.change_date,
                    "description": w.change_description,
                    "lift": w.lift,
                }
                for w in windows
            ],
            "roi_summaries": {
                asin: {
                    "conversion_lift_pct": s.conversion_lift_pct,
                    "estimated_additional_revenue": s.estimated_additional_revenue,
                    "photography_cost_saved": s.photography_cost_saved,
                }
                for asin, s in self._roi_cache.items()
            },
            "status": "stub_data",
        }


# Module-level singleton
attribution = AttributionEngine()
