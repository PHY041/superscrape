"""Seedream 4.5 lifestyle image generation via BytePlus API."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from superscrape.output.models import AmazonProduct

logger = logging.getLogger(__name__)

_BYTEPLUSES_ENDPOINT = (
    "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations"
)
_SEEDREAM_MODEL = "seedream-4-5-251128"
_DEFAULT_API_KEY = None  # must be set via BYTEPLUSES_API_KEY env var


def _build_lifestyle_prompt(product: AmazonProduct) -> str:
    """Build a conservative, brand-safe lifestyle prompt for a product."""
    title_snippet = product.title[:80] if product.title else "product"
    category = product.category.split(" > ")[-1] if product.category else ""
    context = f"{category} {title_snippet}".strip()

    return (
        f"High-end lifestyle product photograph of {context}. "
        "Soft overcast natural lighting, no harsh direct sun. "
        "Gentle diffused light, colors naturally muted under cloud-filtered light. "
        "Atmospheric haze. Quiet, contemplative mood. "
        "High-end travel magazine editorial. Sophisticated restrained palette — "
        "think Condé Nast Traveler or Cereal Magazine. "
        "Neutral tones. Understated elegance. Matte finish. "
        "Product clearly visible, prominently placed in a natural setting. "
        "No people. No text. No watermarks."
    )


def generate_lifestyle_images(
    products: list[AmazonProduct],
    *,
    max_products: int = 5,
    width: int = 1024,
    height: int = 1024,
) -> list[str]:
    """Generate lifestyle images for up to `max_products` products.

    Returns a list of image URLs from the Seedream API.
    Failures for individual products are logged and skipped rather than raised.
    """
    api_key = os.environ.get("BYTEPLUSES_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "BYTEPLUSES_API_KEY is not set. "
            "Export it before running: export BYTEPLUSES_API_KEY=..."
        )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    urls: list[str] = []
    target = products[:max_products]

    with httpx.Client(timeout=120.0) as client:
        for i, product in enumerate(target):
            prompt = _build_lifestyle_prompt(product)
            payload = {
                "model": _SEEDREAM_MODEL,
                "prompt": prompt,
                "width": width,
                "height": height,
                "num_images": 1,
            }

            try:
                response = client.post(
                    _BYTEPLUSES_ENDPOINT, json=payload, headers=headers
                )
                response.raise_for_status()
                data = response.json()

                image_url = data["data"][0]["url"]
                urls.append(image_url)
                logger.info(
                    "Seedream image generated [%d/%d] for ASIN %s",
                    i + 1,
                    len(target),
                    product.asin,
                )
            except (httpx.HTTPError, KeyError, IndexError) as exc:
                logger.warning(
                    "Seedream generation failed for ASIN %s: %s", product.asin, exc
                )

    return urls
