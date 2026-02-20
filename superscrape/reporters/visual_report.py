"""Generate category visual intelligence reports from analyzed products."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from superscrape.output.models import (
    CategoryVisualReport,
    ImageAnalysis,
    ScrapedItem,
)

_PLATFORM_LABELS = {
    "amazon": "Amazon",
    "walmart": "Walmart",
    "ebay": "eBay",
    "etsy": "Etsy",
    "shopee": "Shopee",
    "tiktok_shop": "TikTok Shop",
    "instagram": "Instagram",
    "pinterest": "Pinterest",
    "tiktok": "TikTok",
    "xiaohongshu": "Xiaohongshu",
    "lazada": "Lazada",
    "temu": "Temu",
}


def _pct(count: int, total: int) -> float:
    return round(count / total * 100, 1) if total > 0 else 0.0


def aggregate_report(
    keyword: str,
    products: list[ScrapedItem],
    analyses: list[ImageAnalysis],
    platform: str = "amazon",
) -> CategoryVisualReport:
    """Build aggregated statistics from individual image analyses."""
    total = len(analyses)
    if total == 0:
        return CategoryVisualReport(keyword=keyword, platform=platform)

    type_counts = Counter(a.image_type for a in analyses)
    angle_counts = Counter(a.angle for a in analyses)
    bg_counts = Counter(a.background for a in analyses)
    person_count = sum(1 for a in analyses if a.has_person)
    text_count = sum(1 for a in analyses if a.has_text)

    type_dist = {k: _pct(v, total) for k, v in type_counts.most_common()}
    angle_dist = {k: _pct(v, total) for k, v in angle_counts.most_common()}
    bg_dist = {k: _pct(v, total) for k, v in bg_counts.most_common()}

    # Generate recommendations based on data
    recs = _generate_recommendations(type_dist, angle_dist, bg_dist, person_count, text_count, total)

    # Per-product summary: map image URL -> item_id
    url_to_id = {img.hi_res_url: p.item_id for p in products for img in p.images}
    product_map: dict[str, list[ImageAnalysis]] = {}
    for a in analyses:
        item_id = a.item_id or url_to_id.get(a.image_url)
        if item_id:
            product_map.setdefault(item_id, []).append(a)

    product_analyses = []
    for p in products[:20]:  # top 20 for the report
        pa = product_map.get(p.item_id, [])
        if pa:
            # Build per-slot image stack breakdown
            image_stack = [
                {
                    "slot": j + 1,
                    "image_type": a.image_type,
                    "angle": a.angle,
                    "has_person": a.has_person,
                    "has_text": a.has_text,
                    "background": a.background,
                    "description": a.description,
                }
                for j, a in enumerate(pa)
            ]
            product_analyses.append({
                "item_id": p.item_id,
                "asin": p.item_id,  # backward compat
                "title": p.title[:80],
                "price": p.price,
                "rating": p.rating,
                "reviews": p.reviews_count,
                "url": p.url,
                "main_image_type": pa[0].image_type,
                "main_image_angle": pa[0].angle,
                "has_person": any(a.has_person for a in pa),
                "has_text": any(a.has_text for a in pa),
                "image_count": len(p.images),
                "analyzed_count": len(pa),
                "image_stack": image_stack,
            })

    return CategoryVisualReport(
        keyword=keyword,
        platform=platform,
        total_products=len(products),
        total_images=total,
        image_type_distribution=type_dist,
        angle_distribution=angle_dist,
        has_person_ratio=_pct(person_count, total),
        has_text_ratio=_pct(text_count, total),
        background_distribution=bg_dist,
        recommendations=recs,
        product_analyses=product_analyses,
    )


def _generate_recommendations(
    type_dist: dict, angle_dist: dict, bg_dist: dict,
    person_count: int, text_count: int, total: int,
) -> list[str]:
    """Generate actionable recommendations based on the data."""
    recs = []

    # Main image type
    top_type = max(type_dist, key=type_dist.get) if type_dist else None
    if top_type == "white_bg" and type_dist.get("white_bg", 0) > 60:
        recs.append(
            f"White background dominates ({type_dist['white_bg']}%). "
            "Consider a lifestyle hero image to stand out from competitors."
        )
    elif top_type == "lifestyle":
        recs.append(
            f"Lifestyle images lead ({type_dist['lifestyle']}%). "
            "Match this trend but differentiate with unique scenes."
        )

    # Text overlays
    text_pct = _pct(text_count, total)
    if text_pct > 50:
        recs.append(
            f"{text_pct}% of competitors use text overlays/callouts. "
            "Add key feature callouts to your images."
        )
    elif text_pct < 20:
        recs.append(
            f"Only {text_pct}% use text overlays. "
            "Adding feature callouts could be a differentiator."
        )

    # Person/model
    person_pct = _pct(person_count, total)
    if person_pct > 40:
        recs.append(
            f"{person_pct}% of competitors show people/models. "
            "Include a model using your product to match buyer expectations."
        )
    elif person_pct < 15:
        recs.append(
            f"Only {person_pct}% show people. "
            "Adding a person using the product could increase relatability."
        )

    # Angles
    if angle_dist.get("front", 0) > 70:
        recs.append(
            "Front-facing angles dominate. Try a 45-degree angle for dimensionality."
        )

    # Infographic
    if type_dist.get("infographic", 0) < 10:
        recs.append(
            "Few competitors use infographic-style images. "
            "An infographic showing dimensions/features could be your edge."
        )

    return recs


def render_markdown(report: CategoryVisualReport) -> str:
    """Render a CategoryVisualReport as a Markdown document."""
    lines: list[str] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    platform_label = _PLATFORM_LABELS.get(report.platform, report.platform.title())

    lines.append(f"# {platform_label} Visual Intelligence Report: \"{report.keyword}\"")
    lines.append("")
    lines.append(f"> Generated by SuperScrape | {now}")
    lines.append(f"> Products analyzed: {report.total_products} | Main images analyzed: {report.total_images}")
    lines.append("")

    # --- Image Type Distribution ---
    lines.append("## 1. Main Image Type Distribution")
    lines.append("")
    lines.append("| Type | % |")
    lines.append("|------|---|")
    for t, pct in sorted(report.image_type_distribution.items(), key=lambda x: -x[1]):
        bar = "\u2588" * int(pct / 3)
        lines.append(f"| {t} | {pct}% {bar} |")
    lines.append("")

    # --- Angle Distribution ---
    lines.append("## 2. Camera Angle Distribution")
    lines.append("")
    lines.append("| Angle | % |")
    lines.append("|-------|---|")
    for a, pct in sorted(report.angle_distribution.items(), key=lambda x: -x[1]):
        bar = "\u2588" * int(pct / 3)
        lines.append(f"| {a} | {pct}% {bar} |")
    lines.append("")

    # --- Background ---
    lines.append("## 3. Background Style")
    lines.append("")
    lines.append("| Background | % |")
    lines.append("|------------|---|")
    for b, pct in sorted(report.background_distribution.items(), key=lambda x: -x[1]):
        lines.append(f"| {b} | {pct}% |")
    lines.append("")

    # --- Key Metrics ---
    lines.append("## 4. Key Metrics")
    lines.append("")
    lines.append(f"- **Images with people/models**: {report.has_person_ratio}%")
    lines.append(f"- **Images with text overlays**: {report.has_text_ratio}%")
    lines.append("")

    # --- Recommendations ---
    lines.append("## 5. Recommendations")
    lines.append("")
    for i, rec in enumerate(report.recommendations, 1):
        lines.append(f"{i}. {rec}")
    lines.append("")

    # --- Top Products ---
    if report.product_analyses:
        lines.append("## 6. Top Products Analyzed")
        lines.append("")
        lines.append("| # | ID | Title | Price | Rating | Reviews | Main Image Type | Angle | Person? | Text? |")
        lines.append("|---|------|-------|-------|--------|---------|-----------------|-------|---------|-------|")
        for i, pa in enumerate(report.product_analyses, 1):
            item_id = pa.get("item_id", pa.get("asin", ""))
            lines.append(
                f"| {i} | {item_id} | {pa['title'][:40]}... | {pa['price']} | "
                f"{pa['rating']} | {pa['reviews']} | {pa['main_image_type']} | "
                f"{pa['main_image_angle']} | {'Yes' if pa['has_person'] else 'No'} | "
                f"{'Yes' if pa['has_text'] else 'No'} |"
            )
        lines.append("")

    # --- Footer ---
    lines.append("---")
    lines.append("*Generated by [SuperScrape](https://github.com/PHY041/superscrape)*")

    return "\n".join(lines)
