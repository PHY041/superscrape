"""Generate dynamic action plans and A/B test suggestions using GPT-5.2."""

from __future__ import annotations

import json
import logging
import os

from openai import OpenAI

from superscrape.output.models import BenchmarkData, CategoryVisualReport, ScrapedItem

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=api_key)
    return _client


_ACTION_PLAN_PROMPT = """You are an Amazon listing optimization strategist. Based on competitive data, generate a concise 3-phase action plan.

Return JSON: {"phases": [{"phase": 1, "title": "...", "timeframe": "Week 1-2", "priority": "high", "actions": [{"action": "...", "rationale": "...", "expected_impact": "high"}]}]}

3 phases: quick wins, differentiation, testing. Max 3 actions per phase. Keep each action under 100 chars. Be specific with data percentages."""


_AB_TEST_PROMPT = """You are an Amazon A/B testing strategist. Suggest 4 specific A/B tests based on competitive image data.

Return JSON: {"tests": [{"test_name": "...", "hypothesis": "If X then Y because Z", "control": "...", "variant": "...", "metric": "CTR or conversion", "confidence": "high", "estimated_impact": "+X%", "priority": 1}]}

Focus on: main image type, text overlays, model inclusion, angles. Keep descriptions concise."""


def _build_context(
    report: CategoryVisualReport,
    products: list[ScrapedItem],
    benchmark: BenchmarkData | None = None,
) -> str:
    """Build a concise context string from the report data."""
    parts: list[str] = []
    parts.append(f"Category: {report.keyword}")
    parts.append(f"Platform: {report.platform}")
    parts.append(f"Products analyzed: {report.total_products}")
    parts.append(f"Images analyzed: {report.total_images}")
    parts.append("")

    parts.append("Image type distribution:")
    for img_type, pct in report.image_type_distribution.items():
        parts.append(f"  {img_type}: {pct}%")

    parts.append(f"\nImages with people/models: {report.has_person_ratio}%")
    parts.append(f"Images with text overlays: {report.has_text_ratio}%")

    parts.append("\nBackground distribution:")
    for bg, pct in report.background_distribution.items():
        parts.append(f"  {bg}: {pct}%")

    parts.append("\nAngle distribution:")
    for angle, pct in report.angle_distribution.items():
        parts.append(f"  {angle}: {pct}%")

    # Top product info
    if products:
        parts.append("\nTop competitors:")
        for p in products[:5]:
            parts.append(
                f"  - {p.title[:60]}... | {p.price} | "
                f"Rating: {p.rating} | Reviews: {p.reviews_count}"
            )

    # Existing recommendations from statistical analysis
    if report.recommendations:
        parts.append("\nStatistical recommendations:")
        for rec in report.recommendations:
            parts.append(f"  - {rec}")

    # Category benchmark from 80K image dataset
    if benchmark and benchmark.total_products > 0:
        parts.append(f"\n--- CATEGORY BENCHMARK (from {benchmark.total_products:,} products / {benchmark.total_images:,} images) ---")
        parts.append(f"Category: {benchmark.category}")

        if benchmark.missing_slots_ranking:
            parts.append("\nMost commonly missing image slots (% of products missing it):")
            for slot, pct in list(benchmark.missing_slots_ranking.items())[:5]:
                parts.append(f"  {slot}: {pct}% missing")

        parts.append(f"\nBenchmark quality average: {benchmark.quality_avg}/5")
        parts.append(f"A+ Content adoption: {benchmark.aplus_adoption_rate}%")
        if benchmark.aplus_avg_score:
            parts.append(f"A+ average score: {benchmark.aplus_avg_score}/9")

        if benchmark.price_tier_distribution:
            parts.append("\nPrice tier distribution:")
            for tier, pct in benchmark.price_tier_distribution.items():
                parts.append(f"  {tier}: {pct}%")

        if benchmark.top_style_tags:
            parts.append(f"\nTop style tags: {', '.join(benchmark.top_style_tags[:8])}")

        parts.append("\nUSE THIS BENCHMARK DATA to make specific, data-backed recommendations.")
        parts.append("Reference exact percentages and compare the user's competitors against the full category.")

    return "\n".join(parts)


def generate_action_plan(
    report: CategoryVisualReport,
    products: list[ScrapedItem],
    benchmark: BenchmarkData | None = None,
) -> list[dict]:
    """Generate a dynamic action plan based on competitive intelligence."""
    context = _build_context(report, products, benchmark=benchmark)

    try:
        resp = _get_client().chat.completions.create(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": _ACTION_PLAN_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=0.4,
            max_completion_tokens=4000,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        raw = raw.strip()
        if not raw:
            logger.warning("Empty response from GPT for action plan (finish_reason=%s)", resp.choices[0].finish_reason)
            return []
        data = json.loads(raw)
        # Handle various wrapper keys
        if isinstance(data, dict):
            for key in ("phases", "action_plan", "plan"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        logger.error("Failed to generate action plan: %s", e)
        return []


def generate_ab_tests(
    report: CategoryVisualReport,
    products: list[ScrapedItem],
    benchmark: BenchmarkData | None = None,
) -> list[dict]:
    """Generate A/B test suggestions based on competitive intelligence."""
    context = _build_context(report, products, benchmark=benchmark)

    try:
        resp = _get_client().chat.completions.create(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": _AB_TEST_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=0.4,
            max_completion_tokens=4000,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        raw = raw.strip()
        if not raw:
            logger.warning("Empty response from GPT for A/B tests (finish_reason=%s)", resp.choices[0].finish_reason)
            return []
        data = json.loads(raw)
        if isinstance(data, dict):
            for key in ("tests", "ab_tests", "suggestions"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        logger.error("Failed to generate A/B tests: %s", e)
        return []
