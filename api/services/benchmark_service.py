"""Category benchmark service — loads 80K pre-analyzed clothing image data.

Provides category-level baselines (image types, angles, backgrounds, missing
slots, A+ adoption, price tiers) so that per-job scrape results can be
compared against the full dataset of 4,000+ products / 80,000+ images.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from pathlib import Path

from superscrape.output.models import BenchmarkData

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "projects" / "clothing_images"

# Pre-aggregated benchmarks keyed by L2 category name (e.g. "Active", "Jeans")
_benchmarks: dict[str, BenchmarkData] = {}
# Global (all-category) benchmark
_global_benchmark: BenchmarkData | None = None
_loaded = False


def _pct(count: int, total: int) -> float:
    """Return percentage rounded to 1 decimal, safe against zero division."""
    return round(count / total * 100, 1) if total else 0.0


def _load_data() -> None:
    """Load and pre-aggregate the 80K dataset into per-category benchmarks."""
    global _benchmarks, _global_benchmark, _loaded
    if _loaded:
        return

    products_path = _DATA_DIR / "all_products.json"
    images_path = _DATA_DIR / "image_analysis.jsonl"
    product_analysis_path = _DATA_DIR / "product_analysis.jsonl"
    aplus_path = _DATA_DIR / "aplus_analysis.jsonl"

    if not products_path.exists():
        logger.warning("Benchmark data not found at %s — skipping", _DATA_DIR)
        _loaded = True
        return

    # ── Step 1: Load product metadata (ASIN → category mapping) ──────────
    logger.info("Loading benchmark products from %s ...", products_path)
    with open(products_path) as f:
        raw_products = json.load(f)

    asin_to_cat: dict[str, str] = {}  # asin → L2 category
    asin_to_catpath: dict[str, str] = {}
    cat_product_counts: Counter[str] = Counter()

    for p in raw_products:
        asin = p.get("asin", "")
        cat_path = p.get("category_path", "")
        parts = cat_path.split(" > ")
        l2 = parts[1] if len(parts) >= 2 else "Other"
        asin_to_cat[asin] = l2
        asin_to_catpath[asin] = cat_path
        cat_product_counts[l2] += 1

    total_products = len(raw_products)
    logger.info("Loaded %d products across %d categories", total_products, len(cat_product_counts))

    # ── Step 2: Aggregate image analysis per category ────────────────────
    # Per-category accumulators
    cat_img_count: Counter[str] = Counter()
    cat_img_type: dict[str, Counter] = defaultdict(Counter)
    cat_angle: dict[str, Counter] = defaultdict(Counter)
    cat_bg: dict[str, Counter] = defaultdict(Counter)
    cat_has_person: Counter[str] = Counter()  # images with model category
    cat_has_text: Counter[str] = Counter()
    cat_quality_sum: dict[str, float] = defaultdict(float)
    cat_style_tags: dict[str, Counter] = defaultdict(Counter)
    cat_reverse_prompts: dict[str, list] = defaultdict(list)

    if images_path.exists():
        logger.info("Loading image analyses from %s ...", images_path)
        with open(images_path) as f:
            for line in f:
                try:
                    img = json.loads(line)
                except json.JSONDecodeError:
                    continue

                asin = img.get("asin", "")
                cat = asin_to_cat.get(asin, "Other")

                cat_img_count[cat] += 1
                cat_img_count["__all__"] += 1

                # Image type (category field in image_analysis = image type)
                img_type = img.get("category", "unknown")
                cat_img_type[cat][img_type] += 1
                cat_img_type["__all__"][img_type] += 1

                # Camera angle
                comp = img.get("composition", {})
                angle = comp.get("camera_angle", "unknown")
                cat_angle[cat][angle] += 1
                cat_angle["__all__"][angle] += 1

                # Background
                bg = comp.get("background", "unknown")
                cat_bg[cat][bg] += 1
                cat_bg["__all__"][bg] += 1

                # Person/model detection (image type == "model")
                if img_type == "model":
                    cat_has_person[cat] += 1
                    cat_has_person["__all__"] += 1

                # Text overlay
                text_info = img.get("text_overlay", {})
                if text_info.get("has_text"):
                    cat_has_text[cat] += 1
                    cat_has_text["__all__"] += 1

                # Quality score
                qs = img.get("quality_score", 0)
                cat_quality_sum[cat] += qs
                cat_quality_sum["__all__"] += qs

                # Style tags
                for tag in img.get("style_tags", []):
                    cat_style_tags[cat][tag] += 1
                    cat_style_tags["__all__"][tag] += 1

                # Reverse prompts (keep top ones per category, limit memory)
                rp = img.get("reverse_prompt", "")
                if rp and len(cat_reverse_prompts[cat]) < 50:
                    cat_reverse_prompts[cat].append({
                        "prompt": rp,
                        "type": img_type,
                        "url": img.get("url", ""),
                    })

        total_images = cat_img_count["__all__"]
        logger.info("Loaded %d image analyses", total_images)
    else:
        total_images = 0

    # ── Step 3: Load product analysis (missing slots, A+, price tiers) ───
    cat_missing: dict[str, Counter] = defaultdict(Counter)
    cat_aplus_has: Counter[str] = Counter()
    cat_aplus_score_sum: dict[str, float] = defaultdict(float)
    cat_aplus_count: Counter[str] = Counter()
    cat_price_tier: dict[str, Counter] = defaultdict(Counter)
    cat_analysis_count: Counter[str] = Counter()

    if product_analysis_path.exists():
        logger.info("Loading product analyses from %s ...", product_analysis_path)
        with open(product_analysis_path) as f:
            for line in f:
                try:
                    pa = json.loads(line)
                except json.JSONDecodeError:
                    continue

                asin = pa.get("asin", "")
                cat = asin_to_cat.get(asin, "Other")
                cat_analysis_count[cat] += 1
                cat_analysis_count["__all__"] += 1

                # Missing slots
                missing = pa.get("main_sequence", {}).get("missing_slots", [])
                for slot in missing:
                    cat_missing[cat][slot] += 1
                    cat_missing["__all__"][slot] += 1

                # A+ content
                aplus = pa.get("aplus_content", {})
                if aplus.get("has_aplus"):
                    cat_aplus_has[cat] += 1
                    cat_aplus_has["__all__"] += 1
                    score = aplus.get("aplus_score", 0)
                    if score:
                        cat_aplus_score_sum[cat] += score
                        cat_aplus_score_sum["__all__"] += score
                        cat_aplus_count[cat] += 1
                        cat_aplus_count["__all__"] += 1

                # Price tier
                tier = pa.get("brand_positioning", {}).get("price_tier", "unknown")
                cat_price_tier[cat][tier] += 1
                cat_price_tier["__all__"][tier] += 1

    # ── Step 4: Build BenchmarkData per category ─────────────────────────
    def _build_benchmark(cat_key: str, display_name: str) -> BenchmarkData:
        n_imgs = cat_img_count.get(cat_key, 0)
        n_prods = cat_product_counts.get(cat_key, 0) if cat_key != "__all__" else total_products
        n_analysis = cat_analysis_count.get(cat_key, 0)

        # Convert counters to percentage dicts
        def _counter_to_pct(counter: Counter, total: int) -> dict[str, float]:
            return {k: _pct(v, total) for k, v in counter.most_common()}

        # Missing slots as percentage of analyzed products
        missing_pct = {k: _pct(v, n_analysis) for k, v in cat_missing.get(cat_key, Counter()).most_common()}

        # Top style tags
        top_tags = [tag for tag, _ in cat_style_tags.get(cat_key, Counter()).most_common(10)]

        # Quality avg
        q_avg = round(cat_quality_sum.get(cat_key, 0) / n_imgs, 2) if n_imgs else 0.0

        # A+ stats
        aplus_rate = _pct(cat_aplus_has.get(cat_key, 0), n_analysis) if n_analysis else 0.0
        aplus_avg = round(
            cat_aplus_score_sum.get(cat_key, 0) / cat_aplus_count.get(cat_key, 1), 1
        ) if cat_aplus_count.get(cat_key, 0) else 0.0

        return BenchmarkData(
            category=display_name,
            matched_categories=[cat_key] if cat_key != "__all__" else list(cat_product_counts.keys()),
            total_products=n_prods,
            total_images=n_imgs,
            image_type_distribution=_counter_to_pct(cat_img_type.get(cat_key, Counter()), n_imgs),
            angle_distribution=_counter_to_pct(cat_angle.get(cat_key, Counter()), n_imgs),
            background_distribution=_counter_to_pct(cat_bg.get(cat_key, Counter()), n_imgs),
            has_person_ratio=_pct(cat_has_person.get(cat_key, 0), n_imgs),
            has_text_ratio=_pct(cat_has_text.get(cat_key, 0), n_imgs),
            top_style_tags=top_tags,
            quality_avg=q_avg,
            missing_slots_ranking=missing_pct,
            aplus_adoption_rate=aplus_rate,
            aplus_avg_score=aplus_avg,
            price_tier_distribution=_counter_to_pct(cat_price_tier.get(cat_key, Counter()), n_analysis),
            top_reverse_prompts=cat_reverse_prompts.get(cat_key, [])[:10],
        )

    # Build per-category benchmarks
    for cat_name in cat_product_counts:
        _benchmarks[cat_name] = _build_benchmark(cat_name, cat_name)

    # Build global benchmark
    _global_benchmark = _build_benchmark("__all__", "All Clothing")
    _loaded = True

    logger.info(
        "Benchmark service ready: %d categories, %d products, %d images",
        len(_benchmarks), total_products, total_images,
    )


def get_categories() -> list[dict[str, int]]:
    """Return list of available benchmark categories with product counts."""
    _load_data()
    return [
        {"category": b.category, "total_products": b.total_products, "total_images": b.total_images}
        for b in sorted(_benchmarks.values(), key=lambda b: b.total_products, reverse=True)
    ]


def get_benchmark(keyword: str) -> BenchmarkData | None:
    """Match a search keyword to the most relevant category benchmark.

    Matching strategy:
    1. Exact L2 category name match (case-insensitive)
    2. Keyword substring match against category names
    3. Fall back to global (all-category) benchmark
    """
    _load_data()
    if not _benchmarks:
        return None

    kw_lower = keyword.lower()

    # Exact match
    for cat_name, bench in _benchmarks.items():
        if cat_name.lower() == kw_lower:
            return bench

    # Substring / keyword match — score each category
    kw_words = set(kw_lower.split())
    best_score = 0
    best_cat = None

    _KEYWORD_MAP: dict[str, list[str]] = {
        "Active": ["active", "activewear", "sport", "athletic", "workout", "gym", "running", "yoga", "legging", "shorts"],
        "Jeans": ["jean", "jeans", "denim"],
        "Fashion Hoodies & Sweatshirts": ["hoodie", "hoodies", "sweatshirt", "pullover", "fleece"],
        "Baby Boys": ["baby", "boy", "infant", "toddler", "onesie"],
        "Baby Girls": ["baby", "girl", "infant", "toddler"],
        "Bodysuits": ["bodysuit", "romper", "jumpsuit"],
        "Jackets & Coats": ["jacket", "coat", "parka", "windbreaker", "bomber", "puffer"],
        "Underwear": ["underwear", "boxer", "brief", "panties"],
        "Dresses": ["dress", "gown", "sundress", "maxi", "midi"],
        "Socks & Hosiery": ["sock", "socks", "hosiery", "stocking"],
        "Clothing Sets": ["set", "outfit", "matching"],
        "Socks & Tights": ["tights", "leotard"],
        "Swim": ["swim", "swimsuit", "swimwear", "bikini", "trunk"],
        "Lingerie, Sleep & Lounge": ["lingerie", "pajama", "sleepwear", "lounge", "nightgown", "robe"],
        "Suits & Sport Coats": ["suit", "blazer", "sport coat", "formal"],
        "Coats, Jackets & Vests": ["vest", "gilet", "waistcoat"],
        "Swimsuits & Cover Ups": ["cover up", "sarong", "beach"],
        "Suiting & Blazers": ["suiting", "blazer"],
        "Overalls": ["overall", "dungaree", "bib"],
    }

    for cat_name, bench in _benchmarks.items():
        score = 0
        cat_words = set(cat_name.lower().split())

        # Direct word overlap
        overlap = kw_words & cat_words
        score += len(overlap) * 3

        # Keyword map matching
        mapped_words = _KEYWORD_MAP.get(cat_name, [])
        for w in kw_words:
            if w in mapped_words:
                score += 2
            # Partial match (e.g. "shirt" in "sweatshirt")
            for mw in mapped_words:
                if w in mw or mw in w:
                    score += 1

        # Substring of category name
        if kw_lower in cat_name.lower():
            score += 3

        if score > best_score:
            best_score = score
            best_cat = cat_name

    if best_cat and best_score >= 2:
        return _benchmarks[best_cat]

    # Fall back to global benchmark for weak/no matches
    return _global_benchmark


def get_top_gaps(keyword: str, limit: int = 5) -> list[dict]:
    """Return the top opportunity gaps for a category."""
    bench = get_benchmark(keyword)
    if not bench:
        return []

    gaps: list[dict] = []
    for slot, pct in list(bench.missing_slots_ranking.items())[:limit]:
        gaps.append({
            "slot": slot,
            "missing_pct": pct,
            "insight": f"{pct}% of products in this category are missing '{slot}' — adding one puts you ahead of the majority.",
        })
    return gaps


def get_reverse_prompts(keyword: str, image_type: str = "", limit: int = 10) -> list[dict]:
    """Return reference reverse prompts for a category, optionally filtered by image type."""
    bench = get_benchmark(keyword)
    if not bench:
        return []

    prompts = bench.top_reverse_prompts
    if image_type:
        prompts = [p for p in prompts if p.get("type", "") == image_type]
    return prompts[:limit]
