"""Walmart scraper -- search results and product images."""

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

_BASE = "https://www.walmart.com"


class WalmartProduct(ScrapedItem):
    """A Walmart product listing with images."""

    platform: str = "walmart"
    walmart_id: str = ""
    brand: str = ""
    seller: str = ""

    @model_validator(mode="after")
    def _sync_ids(self) -> "WalmartProduct":
        if self.walmart_id and not self.item_id:
            self.item_id = self.walmart_id
        elif self.item_id and not self.walmart_id:
            self.walmart_id = self.item_id
        return self


def _extract_walmart_id(url: str) -> str:
    """Extract Walmart product ID from /ip/.../{id} URL."""
    match = re.search(r"/ip/[^/]+/(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"/ip/(\d+)", url)
    return match.group(1) if match else ""


def _upgrade_image_url(url: str) -> str:
    """Upgrade Walmart thumbnail to high-res."""
    url = re.sub(r"odnHeight=\d+", "odnHeight=2000", url)
    url = re.sub(r"odnWidth=\d+", "odnWidth=2000", url)
    return url


def _make_product_images(urls: list[str]) -> list[ProductImage]:
    """Deduplicate and convert Walmart image URLs."""
    seen: set[str] = set()
    images: list[ProductImage] = []
    for url in urls:
        if not url or "walmartimages" not in url:
            continue
        base = url.split("?")[0]
        if base in seen:
            continue
        seen.add(base)
        hi_res = _upgrade_image_url(url)
        img_match = re.search(r"/([^/]+)\.\w+(?:\?|$)", base)
        image_id = img_match.group(1) if img_match else str(len(images))
        images.append(ProductImage(url=url, image_id=image_id, hi_res_url=hi_res))
    return images


# ---------------------------------------------------------------------------
# JS: Extract rich product list from __NEXT_DATA__ on search page
# ---------------------------------------------------------------------------
_JS_SEARCH_NEXT_DATA = """() => {
    const el = document.querySelector('script#__NEXT_DATA__');
    if (!el) return [];
    try {
        const data = JSON.parse(el.textContent);
        const sr = data.props.pageProps.initialData.searchResult;
        const stacks = sr.itemStacks || [];
        const items = [];
        for (const stack of stacks) {
            for (const item of (stack.items || [])) {
                if (item.__typename !== 'Product') continue;
                const r = item.rating || {};
                const pi = item.priceInfo || {};
                const url = item.canonicalUrl || '';
                items.push({
                    pid: item.usItemId || '',
                    title: (item.name || '').substring(0, 200),
                    averageRating: r.averageRating || item.averageRating || 0,
                    numberOfReviews: r.numberOfReviews || item.numberOfReviews || 0,
                    price: pi.linePrice || pi.itemPrice || '',
                    brand: item.brand || '',
                    canonicalUrl: url,
                    thumbnailUrl: (item.imageInfo || {}).thumbnailUrl || '',
                });
            }
        }
        return items;
    } catch(e) { return []; }
}"""

# Fallback: DOM-based search extraction if __NEXT_DATA__ is empty
_JS_SEARCH_DOM = r"""() => {
    const links = document.querySelectorAll('a[href*="/ip/"]');
    const seen = new Set();
    const items = [];
    links.forEach(a => {
        const href = a.getAttribute('href') || '';
        const match = href.match(/\/ip\/[^/]+\/(\d+)/);
        if (!match) return;
        const pid = match[1];
        if (seen.has(pid)) return;
        seen.add(pid);
        const img = a.querySelector('img');
        const imgSrc = img ? img.src : '';
        const title = a.getAttribute('aria-label')
            || (img ? img.alt : '')
            || (a.textContent || '').trim().substring(0, 120)
            || '';
        if (title) {
            items.push({pid, title: title.substring(0, 200), canonicalUrl: href, thumbnailUrl: imgSrc,
                         averageRating: 0, numberOfReviews: 0, price: '', brand: ''});
        }
    });
    return items;
}"""

# ---------------------------------------------------------------------------
# JS: Extract images only from product page
# ---------------------------------------------------------------------------
_JS_PRODUCT_IMAGES = """() => {
    const imgs = new Set();
    document.querySelectorAll('img').forEach(img => {
        const src = img.src || '';
        if (src.includes('walmartimages') && !src.includes('pixel') && !src.includes('beacon') && img.width > 50) {
            imgs.add(src);
        }
    });
    // Also check thumbnail strip (carousel) for lazy images
    document.querySelectorAll('[data-testid] img, [class*="carousel"] img, [class*="gallery"] img').forEach(img => {
        const src = img.src || img.getAttribute('data-src') || '';
        if (src.includes('walmartimages') && !src.includes('pixel')) {
            imgs.add(src);
        }
    });
    return Array.from(imgs);
}"""


class Walmart:
    """Walmart product and search scraper using Camoufox."""

    @staticmethod
    def search(keyword: str, *, headless: bool = True) -> list[dict]:
        """Search Walmart and return rich product dicts from __NEXT_DATA__."""
        search_url = f"{_BASE}/search?q={urllib.parse.quote_plus(keyword)}"

        def _scrape() -> list[dict]:
            with fresh_browser(headless=headless) as page:
                page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                for frac in (0.3, 0.5, 0.7, 0.85, 1.0):
                    page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {frac})")
                    page.wait_for_timeout(1500)

                # Try __NEXT_DATA__ first (has rating/price/reviews)
                items = page.evaluate(_JS_SEARCH_NEXT_DATA)
                if items:
                    return items

                # Fallback to DOM scraping
                logger.warning("Walmart __NEXT_DATA__ empty, falling back to DOM")
                return page.evaluate(_JS_SEARCH_DOM)

        return retry_with_backoff(_scrape, description=f"walmart_search({keyword})")

    @staticmethod
    def _scrape_images(url: str, *, headless: bool = True) -> list[str]:
        """Visit a product page and extract image URLs only."""

        def _scrape() -> list[str]:
            with fresh_browser(headless=headless) as page:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                # Click through image thumbnails to load all images
                thumbs = page.query_selector_all('[data-testid*="hero-image"] button, [class*="thumbnail"] button')
                for thumb in thumbs[:8]:
                    try:
                        thumb.click()
                        page.wait_for_timeout(500)
                    except Exception:
                        pass
                return page.evaluate(_JS_PRODUCT_IMAGES)

        return retry_with_backoff(_scrape, description=f"walmart_images({url})")

    @staticmethod
    def product(url: str, *, headless: bool = True) -> WalmartProduct:
        """Scrape a single Walmart product page (for standalone use)."""
        walmart_id = _extract_walmart_id(url)
        image_urls = Walmart._scrape_images(url, headless=headless)
        images = _make_product_images(image_urls)
        return WalmartProduct(
            walmart_id=walmart_id,
            images=images,
            url=url,
        )

    @staticmethod
    def search_images(
        keyword: str,
        *,
        top_n: int = 50,
        headless: bool = True,
    ) -> list[WalmartProduct]:
        """Search -> get top N products with metadata -> scrape image galleries."""
        raw_results = Walmart.search(keyword, headless=headless)

        # Deduplicate by product ID
        seen: set[str] = set()
        unique: list[dict] = []
        for r in raw_results:
            pid = r.get("pid", "")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            unique.append(r)
            if len(unique) >= top_n:
                break

        logger.info("Walmart search '%s': %d unique products", keyword, len(unique))
        products: list[WalmartProduct] = []
        total = len(unique)

        def _fetch_one(idx: int, sr: dict) -> WalmartProduct | None:
            """Fetch images for one product, merge with search metadata."""
            canon = sr.get("canonicalUrl", "")
            full_url = canon if canon.startswith("http") else f"{_BASE}{canon}"
            # Strip tracking redirect
            if "/sp/track" in full_url and "/ip/" in full_url:
                ip_match = re.search(r"(/ip/[^\s&]+)", full_url)
                if ip_match:
                    full_url = f"{_BASE}{ip_match.group(1)}"

            pid = sr.get("pid", "")
            try:
                image_urls = Walmart._scrape_images(full_url, headless=headless)
                images = _make_product_images(image_urls)
            except Exception as e:
                logger.warning("[%d/%d] Image scrape FAILED: %s", idx + 1, total, e)
                images = []

            # Fallback: use search thumbnail if product page yielded no images
            if not images:
                thumb = sr.get("thumbnailUrl", "")
                if thumb:
                    images = _make_product_images([thumb])
                    logger.info("[%d/%d] Using search thumbnail as fallback", idx + 1, total)

            return WalmartProduct(
                walmart_id=pid,
                title=sr.get("title", ""),
                price=sr.get("price", ""),
                rating=sr.get("averageRating", 0),
                reviews_count=sr.get("numberOfReviews", 0),
                brand=sr.get("brand", ""),
                images=images,
                url=full_url,
            )

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures: dict = {}
            for i, sr in enumerate(unique):
                futures[executor.submit(_fetch_one, i, sr)] = (i, sr)
                time.sleep(0.5)

            for future in as_completed(futures):
                i, sr = futures[future]
                try:
                    product = future.result()
                    if product:
                        products.append(product)
                        logger.info(
                            "[%d/%d] %s... (%.1f stars, %d reviews, %d images)",
                            i + 1,
                            total,
                            product.title[:60],
                            product.rating,
                            product.reviews_count,
                            len(product.images),
                        )
                except Exception as e:
                    logger.warning("[%d/%d] FAILED: %s", i + 1, total, e)

        # Sort by original search ranking (Walmart relevance)
        id_order = {sr["pid"]: idx for idx, sr in enumerate(unique)}
        products.sort(key=lambda p: id_order.get(p.walmart_id, 999))

        return products
