"""7-Image Story Arc Designer — AI-powered listing image strategy generator.

Agent 2 core capability: takes competitor intel + review pain points → outputs
a 7-position image strategy with visual briefs for each slot.
"""

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


_STORY_ARC_PROMPT = """You are an Amazon listing image strategist who designs 7-image story arcs.

Amazon allows 7 main images. Each position has a specific role in the customer's decision journey.
Design a complete 7-image strategy based on competitive analysis data.

Return JSON:
{
  "story_arc_name": "descriptive name for this strategy",
  "narrative_theme": "the overarching story this image set tells",
  "slots": [
    {
      "position": 1,
      "slot_type": "hero|lifestyle|infographic|size_chart|comparison|detail|social_proof",
      "purpose": "why this image at this position",
      "visual_brief": "specific description of what the image should show",
      "text_overlay": "suggested text/callout for the image (or empty)",
      "background": "white|studio|outdoor|indoor|solid_color",
      "key_selling_point": "which product benefit this highlights",
      "differentiation_from_competitors": "how this differs from what competitors show"
    }
  ],
  "rationale": "why this arc beats current competitor strategies",
  "estimated_ctr_impact": "+X% estimated based on competitive gaps"
}

Rules:
- Position 1 MUST be white background hero (Amazon requirement)
- Include at least 1 lifestyle, 1 infographic, 1 size/comparison
- Address top customer pain points from reviews
- Exploit gaps in competitor image strategies
- Each slot brief must be specific enough for a photographer/designer to execute"""


def design_story_arc(
    report: CategoryVisualReport,
    products: list[ScrapedItem],
    review_insights: dict | None = None,
    benchmark: BenchmarkData | None = None,
) -> dict:
    """Design a 7-image story arc based on competitive intelligence.

    Args:
        report: Aggregated visual intelligence report
        products: Scraped competitor products
        review_insights: Optional pain point analysis from review_analyzer

    Returns:
        Story arc dict with 7 slot briefs and strategic rationale
    """
    parts: list[str] = []
    parts.append(f"Category: {report.keyword}")
    parts.append(f"Platform: {report.platform}")
    parts.append(f"Products analyzed: {report.total_products}")
    parts.append(f"Images analyzed: {report.total_images}")

    parts.append("\nCompetitor image patterns:")
    for img_type, pct in report.image_type_distribution.items():
        parts.append(f"  {img_type}: {pct}%")

    parts.append(f"\nModels/people used: {report.has_person_ratio}%")
    parts.append(f"Text overlays used: {report.has_text_ratio}%")

    parts.append("\nBackground distribution:")
    for bg, pct in report.background_distribution.items():
        parts.append(f"  {bg}: {pct}%")

    if report.recommendations:
        parts.append("\nStatistical recommendations:")
        for rec in report.recommendations[:5]:
            parts.append(f"  - {rec}")

    # Add review pain points if available
    if review_insights:
        pain_points = review_insights.get("pain_points", [])
        if pain_points:
            parts.append("\nTop customer pain points from reviews:")
            for pp in pain_points[:5]:
                parts.append(f"  - [{pp.get('category', '?')}] {pp.get('description', '')}")

        visual_recs = review_insights.get("visual_recommendations", [])
        if visual_recs:
            parts.append("\nReview-driven visual recommendations:")
            for rec in visual_recs[:4]:
                parts.append(f"  - {rec}")

    # Top competitor titles for context
    if products:
        parts.append("\nTop competitors:")
        for p in products[:5]:
            parts.append(f"  - {p.title[:70]}... | {p.price} | {p.rating}★")

    # Category benchmark (80K image dataset)
    if benchmark and benchmark.total_products > 0:
        parts.append(f"\n--- CATEGORY BENCHMARK ({benchmark.total_products:,} products / {benchmark.total_images:,} images) ---")
        if benchmark.missing_slots_ranking:
            parts.append("Most commonly missing image slots:")
            for slot, pct in list(benchmark.missing_slots_ranking.items())[:5]:
                parts.append(f"  {slot}: {pct}% of products are missing this")
        parts.append(f"A+ adoption: {benchmark.aplus_adoption_rate}%, avg score: {benchmark.aplus_avg_score}/9")
        parts.append(f"Quality avg: {benchmark.quality_avg}/5")
        if benchmark.top_style_tags:
            parts.append(f"Category style: {', '.join(benchmark.top_style_tags[:6])}")
        parts.append("IMPORTANT: Use missing slot data to prioritize which images to include. If 87% are missing size_chart, recommend it.")

    context = "\n".join(parts)

    try:
        resp = _get_client().chat.completions.create(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": _STORY_ARC_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=0.5,
            max_completion_tokens=4000,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        raw = raw.strip()
        if not raw:
            logger.warning("Empty response from GPT for story arc")
            return _default_arc(report.keyword)

        return json.loads(raw)
    except Exception as e:
        logger.error("Failed to design story arc: %s", e)
        return _default_arc(report.keyword)


def _default_arc(keyword: str) -> dict:
    """Fallback 7-slot story arc when GPT fails."""
    return {
        "story_arc_name": f"Standard {keyword} arc",
        "narrative_theme": "Feature-first product showcase",
        "slots": [
            {"position": i + 1, "slot_type": t, "purpose": p, "visual_brief": "", "text_overlay": "", "background": "white" if i == 0 else "studio", "key_selling_point": "", "differentiation_from_competitors": ""}
            for i, (t, p) in enumerate([
                ("hero", "White background product hero shot"),
                ("infographic", "Key features with callout badges"),
                ("lifestyle", "Product in use / lifestyle context"),
                ("detail", "Close-up of materials and craftsmanship"),
                ("size_chart", "Size comparison or dimensions"),
                ("social_proof", "Customer testimonials or ratings highlight"),
                ("comparison", "Competitive advantage comparison"),
            ])
        ],
        "rationale": "Default strategy — generate with competitive data for better results",
        "estimated_ctr_impact": "unknown",
    }
