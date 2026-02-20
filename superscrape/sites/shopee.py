"""Shopee scraper -- search results and product images."""

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

# Default to Singapore; override via SHOPEE_REGION env var
_REGIONS = {
    "sg": "https://shopee.sg",
    "my": "https://shopee.com.my",
    "th": "https://shopee.co.th",
    "ph": "https://shopee.ph",
    "vn": "https://shopee.vn",
    "id": "https://shopee.co.id",
    "tw": "https://shopee.tw",
    "br": "https://shopee.com.br",
}


class ShopeeProduct(ScrapedItem):
    """A Shopee product listing with images."""

    platform: str = "shopee"
    shopee_id: str = ""
    shop_name: str = ""
    sold_count: int = 0
    region: str = "sg"

    @model_validator(mode="after")
    def _sync_ids(self) -> "ShopeeProduct":
        if self.shopee_id and not self.item_id:
            self.item_id = self.shopee_id
        elif self.item_id and not self.shopee_id:
            self.shopee_id = self.item_id
        return self


def _get_base_url(region: str = "sg") -> str:
    return _REGIONS.get(region, _REGIONS["sg"])


# ── JavaScript extraction for search results ──────────────────────────────────

_JS_SEARCH_RESULTS = r'''() => {
    const items = document.querySelectorAll('[data-sqe="item"]');
    if (items.length === 0) {
        // Fallback: try the search result card pattern
        const cards = document.querySelectorAll('.shopee-search-item-result__item');
        if (cards.length > 0) {
            return Array.from(cards).map(card => {
                const link = card.querySelector('a');
                const href = link?.getAttribute('href') || '';
                const title = card.querySelector('.ie3A\\+n, .Cve6sh, [data-sqe="name"]')?.textContent?.trim() || '';
                const priceEl = card.querySelector('.ZEgDH9, .vioxXd, [class*="price"]');
                const price = priceEl?.textContent?.trim() || '';
                const imgEl = card.querySelector('img');
                const imageUrl = imgEl?.src || '';
                const ratingEl = card.querySelector('[class*="rating"]');
                const ratingText = ratingEl?.getAttribute('style') || '';
                const ratingMatch = ratingText.match(/width:\s*([\d.]+)%/);
                const rating = ratingMatch ? (parseFloat(ratingMatch[1]) / 20) : 0;
                const soldEl = card.querySelector('[class*="sold"]');
                const soldText = soldEl?.textContent || '';
                const soldMatch = soldText.replace(/[,\.k]/gi, '').match(/(\d+)/);
                const soldCount = soldMatch ? parseInt(soldMatch[1]) : 0;
                return { href, title, price, imageUrl, rating, soldCount };
            }).filter(item => item.title);
        }
        return [];
    }
    return Array.from(items).map(item => {
        const link = item.querySelector('a');
        const href = link?.getAttribute('href') || '';
        const title = item.querySelector('[data-sqe="name"]')?.textContent?.trim()
            || item.querySelector('.ie3A\\+n, .Cve6sh')?.textContent?.trim() || '';
        const priceEl = item.querySelector('.ZEgDH9, .vioxXd, [class*="price"]');
        const price = priceEl?.textContent?.trim() || '';
        const imgEl = item.querySelector('img');
        const imageUrl = imgEl?.src || '';
        const ratingEl = item.querySelector('[class*="rating"]');
        const ratingText = ratingEl?.getAttribute('style') || '';
        const ratingMatch = ratingText.match(/width:\s*([\d.]+)%/);
        const rating = ratingMatch ? (parseFloat(ratingMatch[1]) / 20) : 0;
        const soldEl = item.querySelector('[class*="sold"]');
        const soldText = soldEl?.textContent || '';
        const soldMatch = soldText.replace(/[,\.k]/gi, '').match(/(\d+)/);
        const soldCount = soldMatch ? parseInt(soldMatch[1]) : 0;
        return { href, title, price, imageUrl, rating, soldCount };
    }).filter(item => item.title);
}'''

# ── JavaScript extraction for product page images ─────────────────────────────

_JS_PRODUCT_PAGE = r'''() => {
    const title = document.querySelector('[class*="title"], .qaNIZv, h1')?.textContent?.trim() || '';

    // Price
    const priceEl = document.querySelector('[class*="price"], .pqTWkA');
    const price = priceEl?.textContent?.trim() || '';

    // Rating
    const ratingEl = document.querySelector('[class*="rating-stars"]');
    const ratingText = ratingEl?.getAttribute('style') || '';
    const ratingMatch = ratingText.match(/width:\s*([\d.]+)%/);
    const rating = ratingMatch ? (parseFloat(ratingMatch[1]) / 20) : 0;

    // Reviews count
    const reviewsEl = document.querySelector('[class*="product-rating"]');
    const reviewsText = reviewsEl?.textContent || '';
    const reviewsMatch = reviewsText.replace(/[,\.]/g, '').match(/(\d+)/);
    const reviewsCount = reviewsMatch ? parseInt(reviewsMatch[1]) : 0;

    // Sold count
    const soldEl = document.querySelector('[class*="sold"]');
    const soldText = soldEl?.textContent || '';
    const soldMatch = soldText.replace(/[,\.k]/gi, '').match(/(\d+)/);
    const soldCount = soldMatch ? parseInt(soldMatch[1]) : 0;

    // Shop name
    const shopEl = document.querySelector('[class*="shop-name"], .EfwBtf');
    const shopName = shopEl?.textContent?.trim() || '';

    // Images: collect all product images
    const imgUrls = new Set();

    // Main carousel images
    document.querySelectorAll('[class*="image-carousel"] img, .ZPN9uD img, ._2GchKS img').forEach(img => {
        const src = img.src || img.getAttribute('data-src') || '';
        if (src && !src.includes('placeholder')) imgUrls.add(src);
    });

    // Thumbnail strip
    document.querySelectorAll('[class*="thumbnail"] img, .ZPN9uD img').forEach(img => {
        const src = img.src || img.getAttribute('data-src') || '';
        if (src && !src.includes('placeholder')) imgUrls.add(src);
    });

    // Fallback: any large product images on page
    document.querySelectorAll('img').forEach(img => {
        const src = img.src || '';
        if (src && src.includes('f_auto') && !src.includes('shop') && !src.includes('avatar')) {
            imgUrls.add(src);
        }
    });

    // Upgrade image URLs to high resolution
    const hiResUrls = Array.from(imgUrls).map(url => {
        // Shopee CDN pattern: remove size suffix to get original
        return url.replace(/_tn\b/, '').replace(/\b\d+x\d+\./, '.');
    });

    return {
        title, price, rating, reviewsCount, soldCount, shopName,
        imageUrls: hiResUrls,
    };
}'''


def _extract_shopee_id_from_url(url: str) -> str:
    """Extract Shopee product ID from URL.

    Shopee URLs look like: /Product-Name-i.{shop_id}.{item_id}
    """
    match = re.search(r"-i\.(\d+)\.(\d+)", url)
    if match:
        return f"{match.group(1)}.{match.group(2)}"
    return ""


def _make_product_images(urls: list[str]) -> list[ProductImage]:
    """Convert raw Shopee image URLs to ProductImage objects."""
    seen: set[str] = set()
    images: list[ProductImage] = []
    for url in urls:
        if url in seen or not url:
            continue
        seen.add(url)
        # Generate a stable image_id from URL
        img_id = re.search(r"/([^/]+)\.\w+$", url)
        image_id = img_id.group(1) if img_id else str(len(images))
        images.append(ProductImage(url=url, image_id=image_id, hi_res_url=url))
    return images


class Shopee:
    """Shopee product and search scraper using Camoufox."""

    @staticmethod
    def search(
        keyword: str,
        *,
        region: str = "sg",
        headless: bool = True,
    ) -> list[dict]:
        """Search Shopee and return raw result dicts."""
        base_url = _get_base_url(region)
        search_url = f"{base_url}/search?keyword={urllib.parse.quote_plus(keyword)}"

        def _scrape() -> list[dict]:
            with fresh_browser(headless=headless) as page:
                page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
                # Shopee is SPA-heavy -- wait for items to render
                page.wait_for_timeout(6000)
                # Scroll to trigger lazy loading
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
                return page.evaluate(_JS_SEARCH_RESULTS)

        return retry_with_backoff(_scrape, description=f"shopee_search({keyword})")

    @staticmethod
    def product(
        url: str,
        *,
        region: str = "sg",
        headless: bool = True,
    ) -> ShopeeProduct:
        """Scrape a single Shopee product page."""
        shopee_id = _extract_shopee_id_from_url(url)

        def _scrape() -> ShopeeProduct:
            with fresh_browser(headless=headless) as page:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                data = page.evaluate(_JS_PRODUCT_PAGE)

            images = _make_product_images(data.get("imageUrls", []))
            return ShopeeProduct(
                shopee_id=shopee_id,
                title=data.get("title", ""),
                price=data.get("price", ""),
                rating=data.get("rating", 0),
                reviews_count=data.get("reviewsCount", 0),
                sold_count=data.get("soldCount", 0),
                shop_name=data.get("shopName", ""),
                images=images,
                url=url,
                region=region,
            )

        return retry_with_backoff(_scrape, description=f"shopee_product({url[-50:]})")

    @staticmethod
    def search_images(
        keyword: str,
        *,
        top_n: int = 50,
        region: str = "sg",
        headless: bool = True,
    ) -> list[ShopeeProduct]:
        """Search keyword -> get top N products -> scrape all their images.

        Core method for Shopee Visual Intelligence.
        """
        base_url = _get_base_url(region)
        raw_results = Shopee.search(keyword, region=region, headless=headless)

        # Deduplicate and limit
        seen_urls: set[str] = set()
        unique: list[dict] = []
        for r in raw_results:
            href = r.get("href", "")
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)
            unique.append(r)
            if len(unique) >= top_n:
                break

        products: list[ShopeeProduct] = []
        total = len(unique)

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures: dict = {}
            for i, sr in enumerate(unique):
                href = sr.get("href", "")
                full_url = href if href.startswith("http") else f"{base_url}{href}"
                futures[executor.submit(
                    Shopee.product, full_url, region=region, headless=headless
                )] = (i, sr)
                time.sleep(0.5)  # stagger submissions

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
