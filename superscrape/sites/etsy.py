"""Etsy scraper -- search results and product images."""

from __future__ import annotations

import logging
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

from pydantic import model_validator

from superscrape.core.browser import fresh_browser
from superscrape.core.retry import retry_with_backoff
from superscrape.output.models import ProductImage, ScrapedItem

logger = logging.getLogger(__name__)

_BASE = "https://www.etsy.com"


class EtsyProduct(ScrapedItem):
    """An Etsy listing with images."""

    platform: str = "etsy"
    listing_id: str = ""
    shop_name: str = ""
    favorites: int = 0

    @model_validator(mode="after")
    def _sync_ids(self) -> "EtsyProduct":
        if self.listing_id and not self.item_id:
            self.item_id = self.listing_id
        elif self.item_id and not self.listing_id:
            self.listing_id = self.item_id
        return self


def _extract_listing_id(url: str) -> str:
    """Extract Etsy listing ID from /listing/{id}/ URL."""
    match = re.search(r"/listing/(\d+)", url)
    return match.group(1) if match else ""


def _make_product_images(urls: list[str]) -> list[ProductImage]:
    """Deduplicate and convert Etsy image URLs to hi-res."""
    seen: set[str] = set()
    images: list[ProductImage] = []
    for url in urls:
        if not url or "etsystatic" not in url:
            continue
        # Upgrade to full size: il_794xN or il_fullxfull
        hi_res = re.sub(r"il_\d+x\d+", "il_fullxfull", url)
        base = re.sub(r"\?\S+$", "", hi_res)  # strip query params
        if base in seen:
            continue
        seen.add(base)
        img_match = re.search(r"/([^/]+)\.\w+$", base)
        image_id = img_match.group(1) if img_match else str(len(images))
        images.append(ProductImage(url=url, image_id=image_id, hi_res_url=hi_res))
    return images


_JS_SEARCH = r'''() => {
    const items = [];
    const seen = new Set();

    // Method 1: data-listing-id cards
    document.querySelectorAll('[data-listing-id]').forEach(card => {
        const lid = card.getAttribute('data-listing-id');
        if (seen.has(lid)) return;
        seen.add(lid);

        const link = card.querySelector('a[href*="/listing/"]');
        const href = link?.getAttribute('href') || '';
        const img = card.querySelector('img');
        const imgSrc = img?.src || '';
        const title = img?.alt || card.querySelector('[class*="title"], h3')?.textContent?.trim() || '';
        const priceEl = card.querySelector('[class*="price"], [class*="currency"]');
        const price = priceEl?.textContent?.trim()?.split('\n')[0] || '';

        if (title && href) {
            items.push({href, title: title.substring(0, 120), price, img: imgSrc, lid});
        }
    });

    // Method 2: fallback via listing links
    if (items.length === 0) {
        document.querySelectorAll('a[href*="/listing/"]').forEach(a => {
            const href = a.getAttribute('href') || '';
            const match = href.match(/\/listing\/(\d+)/);
            if (!match) return;
            const lid = match[1];
            if (seen.has(lid)) return;
            seen.add(lid);

            const img = a.querySelector('img');
            const imgSrc = img?.src || '';
            const title = img?.alt || a.textContent?.trim()?.substring(0, 120) || '';
            if (title) {
                items.push({href, title: title.substring(0, 120), img: imgSrc, lid});
            }
        });
    }

    return items;
}'''

_JS_PRODUCT = r'''() => {
    const title = document.querySelector('h1[data-buy-box-listing-title], h1')?.textContent?.trim() || '';
    const priceEl = document.querySelector('[data-buy-box-region="price"] p, [class*="price"], [data-appears-component-name="price"]');
    const price = priceEl?.textContent?.trim() || '';
    const shopEl = document.querySelector('[data-shop-name], a[href*="/shop/"]');
    const shopName = shopEl?.textContent?.trim() || '';
    const favEl = document.querySelector('[data-favorites-count], [class*="favorite"]');
    const favText = favEl?.textContent?.replace(/[,]/g, '') || '';
    const favMatch = favText.match(/(\d+)/);
    const favorites = favMatch ? parseInt(favMatch[1]) : 0;
    const ratingEl = document.querySelector('[data-rating], [class*="star-rating"]');
    const ratingText = ratingEl?.getAttribute('data-rating') || ratingEl?.textContent || '';
    const ratingMatch = ratingText.match(/([\d.]+)/);
    const rating = ratingMatch ? parseFloat(ratingMatch[1]) : 0;
    const reviewsEl = document.querySelector('[data-reviews-count], [class*="reviews"]');
    const reviewsText = reviewsEl?.textContent?.replace(/[,]/g, '') || '';
    const reviewsMatch = reviewsText.match(/(\d+)/);
    const reviewsCount = reviewsMatch ? parseInt(reviewsMatch[1]) : 0;

    const imgs = new Set();
    // Carousel images
    document.querySelectorAll('img[src*="etsystatic"]').forEach(img => {
        const src = img.src || '';
        if (src && !src.includes('avatar') && !src.includes('icon') && img.width > 50) {
            imgs.add(src);
        }
    });
    // Data-src lazy images
    document.querySelectorAll('img[data-src*="etsystatic"]').forEach(img => {
        imgs.add(img.getAttribute('data-src'));
    });

    return {title, price, shopName, favorites, rating, reviewsCount, imageUrls: Array.from(imgs)};
}'''


class Etsy:
    """Etsy product and search scraper using Camoufox."""

    @staticmethod
    def search(keyword: str, *, headless: bool = True) -> list[dict]:
        """Search Etsy and return raw result dicts."""
        search_url = f"{_BASE}/search?q={urllib.parse.quote_plus(keyword)}"

        def _scrape() -> list[dict]:
            with fresh_browser(headless=headless) as page:
                page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(1500)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)
                return page.evaluate(_JS_SEARCH)

        return retry_with_backoff(_scrape, description=f"etsy_search({keyword})")

    @staticmethod
    def product(url: str, *, headless: bool = True) -> EtsyProduct:
        """Scrape a single Etsy product page."""
        listing_id = _extract_listing_id(url)

        def _scrape() -> EtsyProduct:
            with fresh_browser(headless=headless) as page:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                data = page.evaluate(_JS_PRODUCT)

            images = _make_product_images(data.get("imageUrls", []))
            return EtsyProduct(
                listing_id=listing_id,
                title=data.get("title", ""),
                price=data.get("price", ""),
                shop_name=data.get("shopName", ""),
                favorites=data.get("favorites", 0),
                rating=data.get("rating", 0),
                reviews_count=data.get("reviewsCount", 0),
                images=images,
                url=url,
            )

        return retry_with_backoff(_scrape, description=f"etsy_product({listing_id})")

    @staticmethod
    def search_images(
        keyword: str,
        *,
        top_n: int = 50,
        headless: bool = True,
    ) -> list[EtsyProduct]:
        """Search -> get top N products -> scrape all their images."""
        raw_results = Etsy.search(keyword, headless=headless)

        seen: set[str] = set()
        unique: list[dict] = []
        for r in raw_results:
            lid = r.get("lid", "")
            if not lid or lid in seen:
                continue
            seen.add(lid)
            unique.append(r)
            if len(unique) >= top_n:
                break

        logger.info("Etsy search '%s': %d unique products", keyword, len(unique))
        products: list[EtsyProduct] = []
        total = len(unique)

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures: dict = {}
            for i, sr in enumerate(unique):
                href = sr.get("href", "")
                full_url = href if href.startswith("http") else f"{_BASE}{href}"
                futures[executor.submit(
                    Etsy.product, full_url, headless=headless
                )] = (i, sr)
                time.sleep(0.5)

            for future in as_completed(futures):
                i, sr = futures[future]
                try:
                    product = future.result()
                    products.append(product)
                    logger.info(
                        "[%d/%d] %s... (%d images)",
                        i + 1, total, product.title[:60], len(product.images),
                    )
                except Exception as e:
                    logger.warning("[%d/%d] FAILED: %s", i + 1, total, e)

        return products
