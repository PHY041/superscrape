"""AI vision analyzer -- classifies product images using GPT-5.2 Vision."""

from __future__ import annotations

import json
import logging
import os

from openai import OpenAI

from superscrape.core.retry import retry_with_backoff
from superscrape.output.models import ImageAnalysis, ScrapedItem

logger = logging.getLogger(__name__)

_ECOMMERCE_PLATFORMS = frozenset({"amazon", "shopee", "tiktok_shop", "lazada", "temu", "ebay", "walmart", "etsy"})
_SOCIAL_PLATFORMS = frozenset({"instagram", "pinterest", "tiktok", "xiaohongshu"})

_ECOMMERCE_PROMPT = """You are an expert ecommerce product photographer and listing optimization consultant.
Analyze the given product image and classify it precisely.

Return a JSON object with these fields:
- image_type: one of "white_bg", "lifestyle", "infographic", "model", "flat_lay", "size_comparison", "packaging", "detail_closeup"
- angle: one of "front", "45deg", "side", "top", "back", "bottom"
- has_text: boolean - whether the image has text overlays / callout badges
- has_person: boolean - whether a person / model is visible
- background: one of "white", "solid_color", "studio", "outdoor", "indoor", "transparent"
- dominant_colors: list of 2-3 main colors (e.g. ["white", "blue", "silver"])
- description: one sentence describing what the image shows

Return ONLY valid JSON, no markdown fences."""

_SOCIAL_PROMPT = """You are an expert social media visual strategist.
Analyze the given social media image and classify it precisely.

Return a JSON object with these fields:
- image_type: one of "product_shot", "lifestyle", "flat_lay", "selfie", "quote_card", "carousel_slide", "ugc", "behind_the_scenes", "infographic"
- angle: one of "front", "45deg", "side", "top", "back", "bottom"
- has_text: boolean - whether the image has text overlays / captions
- has_person: boolean - whether a person is visible
- background: one of "white", "solid_color", "studio", "outdoor", "indoor", "transparent"
- dominant_colors: list of 2-3 main colors (e.g. ["white", "blue", "silver"])
- description: one sentence describing what the image shows

Return ONLY valid JSON, no markdown fences."""

_client: OpenAI | None = None


def validate_api_key() -> None:
    """Validate that OPENAI_API_KEY is set. Call at CLI startup."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise EnvironmentError("OPENAI_API_KEY is not set. Export it before running: export OPENAI_API_KEY=sk-...")


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY is not set. Export it before running: export OPENAI_API_KEY=sk-...")
        _client = OpenAI(api_key=api_key)
    return _client


def _prompt_for_platform(platform: str) -> str:
    """Return the appropriate system prompt for the platform type."""
    if platform in _SOCIAL_PLATFORMS:
        return _SOCIAL_PROMPT
    return _ECOMMERCE_PROMPT


def analyze_image(image_url: str, platform: str = "amazon") -> ImageAnalysis:
    """Analyze a single product image using GPT-5.2 Vision."""
    client = _get_client()
    system_prompt = _prompt_for_platform(platform)

    def _call() -> str:
        resp = client.chat.completions.create(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this product image:"},
                        {"type": "image_url", "image_url": {"url": image_url, "detail": "low"}},
                    ],
                },
            ],
            temperature=0.1,
            max_completion_tokens=300,
        )
        return resp.choices[0].message.content.strip()

    raw = retry_with_backoff(_call, description=f"analyze_image({image_url[-40:]})")
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    parse_ok = True
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
        parse_ok = False

    _required = ("image_type", "angle", "has_text", "has_person", "background", "dominant_colors", "description")
    if not parse_ok:
        confidence = 0.0
    elif all(k in data for k in _required):
        confidence = 1.0
    else:
        confidence = 0.5

    return ImageAnalysis(
        image_url=image_url,
        image_type=data.get("image_type", "unknown"),
        angle=data.get("angle", "unknown"),
        has_text=data.get("has_text", False),
        has_person=data.get("has_person", False),
        background=data.get("background", "unknown"),
        dominant_colors=data.get("dominant_colors", []),
        description=data.get("description", ""),
        confidence=confidence,
    )


def batch_analyze_first_images(
    items: list[ScrapedItem],
) -> list[ImageAnalysis]:
    """Analyze ONLY the main (hero) image of each product/item.

    Works with any ScrapedItem subclass (AmazonProduct, ShopeeProduct, etc.).
    Uses item.main_image_url which is overridden per-platform for smart picking.
    """
    analyses: list[ImageAnalysis] = []
    for i, item in enumerate(items):
        img_url = item.main_image_url
        if not img_url:
            continue
        try:
            platform = item.platform or "amazon"
            analysis = analyze_image(img_url, platform=platform)
            analyses.append(analysis.model_copy(update={"item_id": item.item_id, "asin": item.item_id}))
            logger.info("Analyzed [%d/%d] %s...", i + 1, len(items), item.title[:50])
        except Exception as e:
            logger.warning("Failed [%d/%d]: %s", i + 1, len(items), e)

    return analyses


def batch_analyze_all_images(
    items: list[ScrapedItem],
    *,
    max_images_per_product: int = 3,
) -> list[ImageAnalysis]:
    """Analyze multiple images per product for richer distribution data.

    Analyzes up to *max_images_per_product* images from each item's image
    gallery, starting with the hero image. This yields much denser data for
    category-level visual intelligence reports.
    """
    analyses: list[ImageAnalysis] = []
    total_items = len(items)
    img_count = 0

    for i, item in enumerate(items):
        platform = item.platform or "amazon"

        # Collect image URLs: hero first, then gallery
        urls: list[str] = []
        hero = item.main_image_url
        if hero:
            urls.append(hero)

        for img in item.images:
            hi_res = img.hi_res_url or img.url
            if hi_res and hi_res not in urls:
                urls.append(hi_res)
            if len(urls) >= max_images_per_product:
                break

        for j, img_url in enumerate(urls):
            try:
                analysis = analyze_image(img_url, platform=platform)
                analyses.append(analysis.model_copy(update={"item_id": item.item_id, "asin": item.item_id}))
                img_count += 1
                logger.info(
                    "Analyzed [%d/%d] img %d/%d %s...",
                    i + 1,
                    total_items,
                    j + 1,
                    len(urls),
                    item.title[:40],
                )
            except Exception as e:
                logger.warning(
                    "Failed [%d/%d] img %d: %s",
                    i + 1,
                    total_items,
                    j + 1,
                    e,
                )

    logger.info("Total images analyzed: %d across %d products", img_count, total_items)
    return analyses
