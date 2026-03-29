"""Review NLP analyzer — extracts pain points and visual strategy insights from reviews."""

from __future__ import annotations

import json
import logging
import os

from openai import OpenAI

from superscrape.output.models import ScrapedItem

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


_REVIEW_ANALYSIS_PROMPT = """You are an Amazon product review analyst specializing in extracting actionable insights for listing optimization.

Analyze the provided customer reviews and return a JSON object with:

{
  "pain_points": [
    {"category": "sizing|color_accuracy|material|durability|fit|packaging|value|shipping|functionality|appearance",
     "description": "...",
     "frequency": "high|medium|low",
     "sentiment_score": -1.0 to 1.0,
     "sample_quotes": ["..."]}
  ],
  "positive_highlights": [
    {"aspect": "...", "frequency": "high|medium|low", "sample_quotes": ["..."]}
  ],
  "visual_recommendations": [
    "Show actual color under different lighting to address color accuracy complaints",
    "Include size comparison photo — many reviews mention sizing confusion"
  ],
  "sentiment_summary": {
    "overall_score": 0.0 to 1.0,
    "positive_pct": 0,
    "negative_pct": 0,
    "neutral_pct": 0,
    "top_complaint": "...",
    "top_praise": "..."
  }
}

Focus on insights that directly inform product photography and listing image strategy.
Max 8 pain points, 5 positive highlights, 6 visual recommendations. Be concise."""


def analyze_reviews(products: list[ScrapedItem]) -> dict:
    """Analyze reviews across all products to extract pain points and insights.

    Returns a dict with pain_points, positive_highlights, visual_recommendations,
    and sentiment_summary.
    """
    # Collect all review texts
    all_reviews: list[str] = []
    for product in products:
        if not hasattr(product, "reviews"):
            continue
        for review in product.reviews:
            if review.text and len(review.text) > 20:
                star_prefix = f"[{review.stars}★]" if review.stars else ""
                all_reviews.append(f"{star_prefix} {review.text[:400]}")

    if not all_reviews:
        logger.info("No review text available for analysis")
        return _empty_result()

    # Limit context to ~60 reviews to stay within token limits
    review_text = "\n---\n".join(all_reviews[:60])
    context = f"Product category: {products[0].title[:80] if products else 'unknown'}\n\nReviews ({len(all_reviews)} total, showing first {min(len(all_reviews), 60)}):\n\n{review_text}"

    try:
        resp = _get_client().chat.completions.create(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": _REVIEW_ANALYSIS_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=0.3,
            max_completion_tokens=4000,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        raw = raw.strip()
        if not raw:
            logger.warning("Empty response from GPT for review analysis")
            return _empty_result()

        data = json.loads(raw)
        return {
            "pain_points": data.get("pain_points", []),
            "positive_highlights": data.get("positive_highlights", []),
            "visual_recommendations": data.get("visual_recommendations", []),
            "sentiment_summary": data.get("sentiment_summary", {}),
            "total_reviews_analyzed": len(all_reviews),
        }
    except Exception as e:
        logger.error("Failed to analyze reviews: %s", e)
        return _empty_result()


def _empty_result() -> dict:
    """Return an empty review analysis result."""
    return {
        "pain_points": [],
        "positive_highlights": [],
        "visual_recommendations": [],
        "sentiment_summary": {},
        "total_reviews_analyzed": 0,
    }
