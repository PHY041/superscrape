"""Listing generation service — bridges scrape results to listing_gen pipeline.

Takes competitor intel + product photos → auto-generates config → runs pipeline
→ generates listing text → returns structured results.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
import uuid
from pathlib import Path

from openai import OpenAI

from superscrape.listing_gen.category_config import get_category_config
from superscrape.listing_gen.models import (
    BrandConfig,
    ImageSlotSpec,
    ProjectConfig,
    SceneRequirement,
    SlotMethod,
    SlotType,
)
from superscrape.output.models import BenchmarkData, CategoryVisualReport, ScrapedItem

logger = logging.getLogger(__name__)

_PROJECTS_DIR = Path(os.environ.get("PROJECTS_DIR", "/tmp/superscrape_projects"))
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=api_key)
    return _client


# ── Config auto-generation prompt ────────────────────────────────────────────

_CONFIG_GEN_PROMPT = """You are an expert Amazon listing image strategist.
Based on the competitor visual intelligence and product info, design a 7-image listing strategy.

For each image slot (1-7), specify:
- slot: slot number (1-7)
- type: one of "hero", "infographic", "lifestyle", "multi_scene", "size_chart", "outfit_pairing", "detail"
- method: one of "bg_remove" (for hero/white bg), "pil_template" (infographic/size_chart), "seedream_scene" (lifestyle), "pil_scene_grid" (multi_scene), "pil_outfit_grid" (outfit)
- description: what this image should show
- requires_photos: list of needed photo angles (e.g. ["front", "detail_collar"])

Also determine:
- product_category: best matching category from the provided list
- scenes: 4-6 lifestyle scene suggestions with names

RULES:
- Slot 1 MUST be hero (white background, product-only)
- Include at least 1 infographic with feature callouts
- Include at least 1 lifestyle/scene image
- Include a size chart if it's apparel
- Balance for Amazon conversion: hero → features → social proof → details

Return a JSON object:
{
  "product_category": "boys_shirt",
  "slots": [
    {"slot": 1, "type": "hero", "method": "bg_remove", "description": "...", "requires_photos": ["front"]},
    ...
  ],
  "scenes": [
    {"name": "Outdoor", "description": "Active outdoor scene"},
    ...
  ]
}

Return ONLY valid JSON, no markdown fences."""


def _detect_category(keyword: str, products: list[ScrapedItem]) -> str:
    """Attempt to detect product category from keyword and product data.

    Scores each category by counting whole-word keyword matches.
    """
    import re
    kw_words = set(re.findall(r"\w+", keyword.lower()))
    category_keywords = {
        "boys_shirt": ["boy", "boys", "shirt", "button"],
        "womens_dress": ["women", "woman", "dress", "gown"],
        "mens_jacket": ["men", "jacket", "coat", "blazer"],
        "mens_shirt": ["men", "shirt", "button"],
        "womens_top": ["women", "top", "blouse", "tee"],
        "kids_pants": ["kids", "pants", "trousers", "jeans", "legging"],
        "kids_shoes": ["kids", "shoes", "sneaker", "boot"],
        "accessories_bag": ["bag", "backpack", "purse", "handbag", "tote"],
    }
    best_cat = "general_apparel"
    best_score = 0
    for cat, words in category_keywords.items():
        score = sum(1 for w in words if w in kw_words)
        if score > best_score:
            best_score = score
            best_cat = cat
    return best_cat


def auto_generate_config(
    keyword: str,
    products: list[ScrapedItem],
    report: CategoryVisualReport,
    product_photos: list[str],
    brand_name: str = "",
    brand_colors: list[str] | None = None,
) -> ProjectConfig:
    """Use GPT-5.2 to auto-generate a ProjectConfig from scrape results.

    Args:
        keyword: Search keyword used for scraping
        products: Scraped competitor products
        report: Visual intelligence report
        product_photos: Paths to user-uploaded product photos
        brand_name: Optional brand name
        brand_colors: Optional brand color hex codes

    Returns:
        ProjectConfig ready for pipeline execution
    """
    # Build context for GPT
    context_parts: list[str] = []
    context_parts.append(f"Product keyword: {keyword}")
    context_parts.append(f"Brand: {brand_name or 'Unknown'}")

    category_list = list(get_category_config("general_apparel").keys())
    context_parts.append(f"\nAvailable categories: {', '.join(['boys_shirt', 'womens_dress', 'mens_jacket', 'mens_shirt', 'womens_top', 'kids_pants', 'kids_shoes', 'accessories_bag', 'general_apparel'])}")

    context_parts.append(f"\nCompetitor analysis ({report.total_products} products, {report.total_images} images):")
    context_parts.append(f"Image types: {json.dumps(report.image_type_distribution)}")
    context_parts.append(f"Models/people: {report.has_person_ratio}%")
    context_parts.append(f"Text overlays: {report.has_text_ratio}%")
    context_parts.append(f"Backgrounds: {json.dumps(report.background_distribution)}")

    if report.recommendations:
        context_parts.append("\nRecommendations:")
        for rec in report.recommendations:
            context_parts.append(f"  - {rec}")

    context_parts.append(f"\nAvailable product photos: {len(product_photos)} images")

    context = "\n".join(context_parts)

    try:
        resp = _get_client().chat.completions.create(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": _CONFIG_GEN_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=0.3,
            max_completion_tokens=2000,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content.strip()
        gpt_config = json.loads(raw)
    except Exception as e:
        logger.warning("GPT config generation failed, using default: %s", e)
        gpt_config = _default_config(keyword)

    # Build ProjectConfig from GPT output
    detected_category = gpt_config.get("product_category", _detect_category(keyword, products))
    cat_config = get_category_config(detected_category)

    project_id = f"auto-{uuid.uuid4().hex[:8]}"
    project_dir = _PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    # Copy product photos to project assets
    assets_dir = project_dir / "assets" / "product_photos"
    assets_dir.mkdir(parents=True, exist_ok=True)
    photo_map: dict[str, str] = {}
    for i, photo_path in enumerate(product_photos):
        src = Path(photo_path)
        if src.exists():
            dst = assets_dir / f"photo_{i}{src.suffix}"
            shutil.copy2(src, dst)
            # Map to angle names if possible
            angle = cat_config.get("photo_angles", ["front"])[min(i, len(cat_config.get("photo_angles", ["front"])) - 1)]
            photo_map[angle] = str(dst)

    # Build slots from GPT output
    slots: list[ImageSlotSpec] = []
    for slot_data in gpt_config.get("slots", []):
        try:
            slot_type = SlotType(slot_data["type"])
            slot_method = SlotMethod(slot_data["method"])
        except (KeyError, ValueError):
            continue

        slots.append(ImageSlotSpec(
            slot=slot_data["slot"],
            type=slot_type,
            method=slot_method,
            size=(2000, 2000),
            requires_photos=slot_data.get("requires_photos", []),
            scene_description=slot_data.get("description", ""),
        ))

    # Build scenes
    scenes: list[SceneRequirement] = []
    for scene_data in gpt_config.get("scenes", []):
        scenes.append(SceneRequirement(
            name=scene_data.get("name", ""),
            description=scene_data.get("description", ""),
        ))

    config = ProjectConfig(
        project_id=project_id,
        product_name=keyword,
        product_category=detected_category,
        brand=BrandConfig(
            name=brand_name,
            colors=brand_colors or [],
        ),
        main_images=slots,
        scenes=scenes,
        size_data=None,  # Can be enhanced later
    )

    # Save config
    config.save(project_dir / "config.json")
    logger.info("Auto-generated config saved to %s", project_dir / "config.json")

    return config


def _default_config(keyword: str) -> dict:
    """Fallback config when GPT generation fails."""
    return {
        "product_category": "general_apparel",
        "slots": [
            {"slot": 1, "type": "hero", "method": "bg_remove", "description": "White background hero shot", "requires_photos": ["front"]},
            {"slot": 2, "type": "infographic", "method": "pil_template", "description": "Feature callout infographic", "requires_photos": ["front", "detail"]},
            {"slot": 3, "type": "lifestyle", "method": "seedream_scene", "description": "Lifestyle scene", "requires_photos": ["front"]},
            {"slot": 4, "type": "detail", "method": "pil_template", "description": "Product details closeup", "requires_photos": ["detail"]},
        ],
        "scenes": [
            {"name": "Casual", "description": "Casual everyday setting"},
            {"name": "Outdoor", "description": "Outdoor active scene"},
        ],
    }


def run_listing_generation(
    config: ProjectConfig,
    project_dir: Path | None = None,
) -> dict:
    """Run the listing_gen pipeline synchronously.

    Returns dict with per-slot results including output paths.
    """
    from superscrape.listing_gen.pipeline import generate_all_sync

    if project_dir is None:
        project_dir = _PROJECTS_DIR / config.project_id

    try:
        results = generate_all_sync(project_dir)
        logger.info("Listing generation complete: %s", results)
        return results
    except Exception as e:
        logger.error("Listing generation failed: %s", e)
        return {"error": str(e)}


def generate_listing_text(
    keyword: str,
    products: list[ScrapedItem],
    report: CategoryVisualReport,
    brand_name: str = "",
    benchmark: BenchmarkData | None = None,
) -> dict:
    """Generate Amazon listing text (title, bullets, description) using GPT-5.2.

    Based on competitor intelligence from the scrape results.
    """
    # Build competitor context
    top_titles = [p.title for p in products[:10]]
    prices = [p.price for p in products if p.price]
    price_range = f"{prices[0]} - {prices[-1]}" if len(prices) >= 2 else ""

    # Extract common keywords from competitor titles
    from collections import Counter
    stop_words = {"the", "a", "an", "and", "or", "for", "with", "in", "of", "to", "by", "s", "-", "&"}
    words: list[str] = []
    for title in top_titles:
        for word in title.lower().split():
            clean = word.strip(",.()[]'\"&/")
            if len(clean) > 2 and clean not in stop_words and not clean.isdigit():
                words.append(clean)
    common_keywords = [w for w, _ in Counter(words).most_common(20)]

    system_prompt = """You are an expert Amazon listing copywriter.
Generate Amazon-compliant listing text that maximizes conversion rate and search visibility.

RULES:
- Title: max 200 chars, capitalize first letter of each word (except prepositions)
- Title format: [Brand] + [Product Type] + [Key Feature] + [Material] + [Size/Age Range]
- Bullets: exactly 5 bullet points, each max 500 chars
- Start each bullet with a CAPITALIZED keyword phrase
- Description: HTML allowed (<br>, <b>, <p>), max 2000 chars
- Search terms: max 250 bytes, lowercase, no brand name, no ASINs
- NEVER use "best", "top quality", "#1", "amazing", "perfect"
- NEVER reference prices or promotions

Return ONLY valid JSON:
{
  "title": "...",
  "bullets": ["KEYWORD — detail...", ...],
  "description": "<p>...</p>",
  "search_terms": "keyword1 keyword2..."
}"""

    user_parts: list[str] = []
    user_parts.append(f"Product keyword: {keyword}")
    if brand_name:
        user_parts.append(f"Brand: {brand_name}")
    user_parts.append(f"\nTop competitor titles (for keyword reference, DO NOT copy):")
    for t in top_titles[:5]:
        user_parts.append(f"  - {t}")
    if price_range:
        user_parts.append(f"\nPrice range: {price_range}")
    user_parts.append(f"\nHigh-frequency keywords: {', '.join(common_keywords[:15])}")
    user_parts.append(f"\nVisual insights: {report.has_person_ratio}% show models, {report.has_text_ratio}% use text overlays")

    if benchmark and benchmark.total_products > 0:
        user_parts.append(f"\nCategory benchmark ({benchmark.total_products:,} products):")
        if benchmark.top_style_tags:
            user_parts.append(f"  Dominant styles: {', '.join(benchmark.top_style_tags[:6])}")
        if benchmark.price_tier_distribution:
            tiers = [f"{t}: {p}%" for t, p in list(benchmark.price_tier_distribution.items())[:3]]
            user_parts.append(f"  Price tiers: {', '.join(tiers)}")

    user_parts.append(f"\nGenerate the complete Amazon listing text. Return ONLY JSON.")

    try:
        resp = _get_client().chat.completions.create(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n".join(user_parts)},
            ],
            temperature=0.3,
            max_completion_tokens=1500,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content.strip()
        result = json.loads(raw)

        required = ("title", "bullets", "description", "search_terms")
        for key in required:
            if key not in result:
                raise ValueError(f"Missing field: {key}")

        return result
    except Exception as e:
        logger.error("Listing text generation failed: %s", e)
        return {
            "title": "",
            "bullets": [],
            "description": "",
            "search_terms": "",
            "error": str(e),
        }
