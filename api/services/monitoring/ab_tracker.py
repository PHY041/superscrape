"""A/B test tracking system — manages test lifecycle and results.

Tracks A/B tests from planning through execution to analysis.
Integrates with Amazon's Manage Your Experiments (MYE) when available,
or supports manual result entry.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class TestStatus(str, Enum):
    planned = "planned"
    running = "running"
    completed = "completed"
    cancelled = "cancelled"


class TestMetric(str, Enum):
    ctr = "ctr"
    conversion_rate = "conversion_rate"
    units_sold = "units_sold"
    revenue = "revenue"
    sessions = "sessions"


@dataclass
class TestVariant:
    """A single variant in an A/B test."""

    name: str  # "control" or "variant_a", "variant_b"
    description: str = ""
    image_url: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    sample_size: int = 0


@dataclass
class ABTest:
    """A tracked A/B test."""

    test_id: str = ""
    asin: str = ""
    test_name: str = ""
    hypothesis: str = ""
    primary_metric: TestMetric = TestMetric.ctr
    status: TestStatus = TestStatus.planned
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_days: int = 14
    variants: list[TestVariant] = field(default_factory=list)
    winner: str = ""  # variant name
    confidence_level: float = 0.0
    lift_pct: float = 0.0
    notes: str = ""


class ABTestTracker:
    """Manage A/B test lifecycle from planning to analysis.

    Current status: In-memory storage. Production needs:
    1. Persistent storage (Supabase)
    2. MYE API integration for automated test management
    3. Statistical significance calculator
    4. Automated alerting when tests reach significance
    """

    def __init__(self) -> None:
        self._tests: dict[str, ABTest] = {}

    def create_test(
        self,
        asin: str,
        test_name: str,
        hypothesis: str,
        primary_metric: TestMetric = TestMetric.ctr,
        duration_days: int = 14,
        variants: list[TestVariant] | None = None,
    ) -> ABTest:
        """Create a new A/B test plan."""
        test_id = str(uuid.uuid4())[:8]
        test = ABTest(
            test_id=test_id,
            asin=asin,
            test_name=test_name,
            hypothesis=hypothesis,
            primary_metric=primary_metric,
            status=TestStatus.planned,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
            duration_days=duration_days,
            variants=variants or [
                TestVariant(name="control"),
                TestVariant(name="variant_a"),
            ],
        )
        self._tests[test_id] = test
        logger.info("Created A/B test %s: %s", test_id, test_name)
        return test

    def start_test(self, test_id: str) -> ABTest | None:
        """Mark a test as running."""
        test = self._tests.get(test_id)
        if test is None:
            return None
        test.status = TestStatus.running
        test.started_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("Started A/B test %s", test_id)
        return test

    def record_results(
        self,
        test_id: str,
        variant_name: str,
        metrics: dict[str, float],
        sample_size: int = 0,
    ) -> ABTest | None:
        """Record metrics for a variant."""
        test = self._tests.get(test_id)
        if test is None:
            return None

        for variant in test.variants:
            if variant.name == variant_name:
                variant.metrics.update(metrics)
                variant.sample_size = sample_size
                break

        return test

    def complete_test(
        self,
        test_id: str,
        winner: str = "",
        confidence_level: float = 0.0,
        lift_pct: float = 0.0,
        notes: str = "",
    ) -> ABTest | None:
        """Mark a test as completed with results."""
        test = self._tests.get(test_id)
        if test is None:
            return None

        test.status = TestStatus.completed
        test.completed_at = datetime.now(tz=timezone.utc).isoformat()
        test.winner = winner
        test.confidence_level = confidence_level
        test.lift_pct = lift_pct
        test.notes = notes

        logger.info(
            "Completed A/B test %s: winner=%s, lift=%.1f%%, confidence=%.1f%%",
            test_id, winner, lift_pct, confidence_level,
        )
        return test

    def get_test(self, test_id: str) -> ABTest | None:
        """Get a test by ID."""
        return self._tests.get(test_id)

    def list_tests(
        self,
        asin: str | None = None,
        status: TestStatus | None = None,
    ) -> list[ABTest]:
        """List tests, optionally filtered by ASIN or status."""
        tests = list(self._tests.values())
        if asin:
            tests = [t for t in tests if t.asin == asin]
        if status:
            tests = [t for t in tests if t.status == status]
        return tests

    def get_insights(self, asin: str) -> dict:
        """Aggregate insights from completed tests for an ASIN."""
        completed = [
            t for t in self._tests.values()
            if t.asin == asin and t.status == TestStatus.completed
        ]
        if not completed:
            return {"asin": asin, "tests_completed": 0, "insights": []}

        insights = []
        total_lift = 0.0
        for test in completed:
            if test.winner and test.lift_pct:
                insights.append({
                    "test": test.test_name,
                    "winner": test.winner,
                    "lift": test.lift_pct,
                    "confidence": test.confidence_level,
                })
                total_lift += test.lift_pct

        return {
            "asin": asin,
            "tests_completed": len(completed),
            "avg_lift_pct": total_lift / len(completed) if completed else 0,
            "insights": insights,
        }


# Module-level singleton
ab_tracker = ABTestTracker()
