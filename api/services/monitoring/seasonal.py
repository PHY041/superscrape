"""Dynamic seasonal alerts based on current date and product category."""

from __future__ import annotations

from datetime import date, timedelta

# ── Seasonal event calendar (US Amazon) ──────────────────────────────────────
# Each event: (name, start_month, start_day, end_month, end_day, keywords, recommendation)

_EVENTS = [
    {
        "name": "Valentine's Day",
        "start": (2, 14),
        "prep_weeks": 6,
        "keywords": ["gift", "couple", "romantic", "heart", "love", "jewelry", "fashion"],
        "recommendation": "Update lifestyle images with romantic/couple themes. Add gift-wrapping visuals.",
    },
    {
        "name": "Spring Season",
        "start": (3, 20),
        "prep_weeks": 6,
        "keywords": ["spring", "outdoor", "light", "floral", "pastel", "dress", "shirt"],
        "recommendation": "Swap to spring color palettes and outdoor lifestyle images. Highlight light fabrics.",
    },
    {
        "name": "Mother's Day",
        "start": (5, 11),
        "prep_weeks": 5,
        "keywords": ["gift", "women", "mom", "mother", "family", "dress", "jewelry"],
        "recommendation": "Add gift-oriented imagery. Update A+ with family/mother themes.",
    },
    {
        "name": "Father's Day",
        "start": (6, 15),
        "prep_weeks": 5,
        "keywords": ["gift", "men", "dad", "father", "shirt", "watch", "outdoor"],
        "recommendation": "Feature dad-focused lifestyle scenes. Emphasize quality and durability.",
    },
    {
        "name": "Prime Day",
        "start": (7, 15),
        "prep_weeks": 6,
        "keywords": [],  # affects all categories
        "recommendation": "Optimize main image for max CTR — this is your highest-traffic day. Prepare A/B test variants 2 weeks before.",
    },
    {
        "name": "Back-to-School",
        "start": (8, 1),
        "prep_weeks": 8,
        "keywords": ["kids", "boys", "girls", "school", "backpack", "uniform", "children", "youth"],
        "recommendation": "Update to school-themed lifestyle images. Feature age-appropriate models. Highlight durability and value packs.",
    },
    {
        "name": "Fall Season",
        "start": (9, 22),
        "prep_weeks": 6,
        "keywords": ["fall", "autumn", "jacket", "sweater", "boots", "layering", "warm"],
        "recommendation": "Switch to warm-tone color palettes. Add layering outfit suggestions.",
    },
    {
        "name": "Halloween",
        "start": (10, 31),
        "prep_weeks": 6,
        "keywords": ["costume", "party", "halloween", "dress up", "spooky"],
        "recommendation": "Add seasonal themed images if relevant. Consider limited-edition variants.",
    },
    {
        "name": "Black Friday / Cyber Monday",
        "start": (11, 28),
        "prep_weeks": 6,
        "keywords": [],  # affects all categories
        "recommendation": "Maximize image quality and A+ content before the rush. Lock in your best-performing main image. Prepare deal-specific hero images.",
    },
    {
        "name": "Holiday Season",
        "start": (12, 25),
        "prep_weeks": 8,
        "keywords": ["gift", "christmas", "holiday", "winter", "present", "festive"],
        "recommendation": "Add gift-themed lifestyle images. Feature holiday scenes and packaging. Consider adding gift guide badge to infographics.",
    },
    {
        "name": "New Year",
        "start": (1, 1),
        "prep_weeks": 4,
        "keywords": ["new year", "resolution", "fitness", "organization", "fresh start"],
        "recommendation": "Update imagery for new year themes — fresh starts, clean aesthetics.",
    },
    {
        "name": "Summer Season",
        "start": (6, 21),
        "prep_weeks": 6,
        "keywords": ["summer", "beach", "outdoor", "swimwear", "shorts", "tank", "sun"],
        "recommendation": "Switch to bright, outdoor lifestyle images. Feature summer activities and warm-weather scenes.",
    },
]


def _keyword_matches(keyword: str, event_keywords: list[str]) -> bool:
    """Check if the search keyword is relevant to an event."""
    if not event_keywords:
        return True  # Universal events (Prime Day, BFCM) apply to all
    kw_lower = keyword.lower()
    return any(ek in kw_lower for ek in event_keywords)


def _days_until_event(today: date, month: int, day: int) -> int:
    """Calculate days until the next occurrence of an event date."""
    event_date = date(today.year, month, day)
    if event_date < today:
        event_date = date(today.year + 1, month, day)
    return (event_date - today).days


def get_seasonal_alerts(
    keyword: str,
    locale: str = "us",
) -> list[dict]:
    """Generate seasonal alerts relevant to the keyword and current date.

    Args:
        keyword: Product search keyword (e.g. "boys button shirt")
        locale: Market locale (currently only "us" supported)

    Returns:
        List of alert dicts sorted by urgency (most urgent first).
    """
    today = date.today()
    alerts: list[dict] = []

    for event in _EVENTS:
        if not _keyword_matches(keyword, event["keywords"]):
            continue

        start_month, start_day = event["start"]
        days_until = _days_until_event(today, start_month, start_day)
        prep_weeks = event["prep_weeks"]
        prep_days = prep_weeks * 7

        # Only show alerts for events within the prep window (+ 7 days after for "in progress" events)
        if days_until > prep_days:
            continue

        if days_until <= 0:
            # Event is today or passed this year — check next year
            days_until = _days_until_event(today + timedelta(days=1), start_month, start_day)
            if days_until > prep_days:
                continue

        # Determine urgency
        if days_until <= 7:
            urgency = "critical"
        elif days_until <= 21:
            urgency = "high"
        elif days_until <= 42:
            urgency = "medium"
        else:
            urgency = "low"

        event_date = today + timedelta(days=days_until)

        alerts.append({
            "event_name": event["name"],
            "date": event_date.isoformat(),
            "days_until": days_until,
            "urgency": urgency,
            "prep_weeks_recommended": prep_weeks,
            "recommendation": event["recommendation"],
        })

    # Sort by urgency: critical > high > medium > low, then by days_until
    urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda a: (urgency_order.get(a["urgency"], 4), a["days_until"]))

    return alerts
