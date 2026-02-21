"""eBay scraper -- search results and product images."""

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

_BASE = "https://www.ebay.com"


class EbayProduct(ScrapedItem):
    """An eBay listing with images."""

    platform: str = "ebay"
    ebay_id: str = ""
    condition: str = ""
    seller_name: str = ""
    shipping: str = ""

    @model_validator(mode="after")
    def _sync_ids(self) -> "EbayProduct":
        if self.ebay_id and not self.item_id:
            self.item_id = self.ebay_id
        elif self.item_id and not self.ebay_id:
            self.ebay_id = self.item_id
        return self


def _extract_ebay_id(url: str) -> str:
    """Extract eBay item ID from /itm/{id} URL."""
    match = re.search(r"/itm/(\d+)", url)
    return match.group(1) if match else ""


def _make_product_images(urls: list[str]) -> list[ProductImage]:
    """Deduplicate and convert eBay image URLs to hi-res."""
    seen: set[str] = set()
    images: list[ProductImage] = []
    for url in urls:
        if not url or "ebayimg" not in url:
            continue
        # Normalize to hi-res: replace s-l140/s-l300/s-l500 with s-l1600
        hi_res = re.sub(r"s-l\d+", "s-l1600", url)
        base = hi_res.split("?")[0]
        if base in seen:
            continue
        seen.add(base)
        img_match = re.search(r"/([^/]+)\.\w+$", base)
        image_id = img_match.group(1) if img_match else str(len(images))
        images.append(ProductImage(url=url, image_id=image_id, hi_res_url=hi_res))
    return images


_JS_SEARCH = r"""() => {
    const links = document.querySelectorAll('a[href*="/itm/"]');
    const seen = new Set();
    const items = [];
    links.forEach(a => {
        const href = a.getAttribute('href') || '';
        const match = href.match(/\/itm\/(\d+)/);
        if (!match) return;
        const eid = match[1];
        if (seen.has(eid)) return;
        seen.add(eid);

        const img = a.querySelector('img');
        const imgSrc = img?.src || '';
        const title = img?.alt || a.textContent?.trim()?.substring(0, 120) || '';
        if (!title || title === 'Shop on eBay') return;

        // Try to find price from parent list item
        const li = a.closest('li');
        const priceEl = li?.querySelector('.s-item__price, [class*="price"]');
        const price = priceEl?.textContent?.trim() || '';

        items.push({href: href.split('?')[0], title: title.substring(0, 120), price, img: imgSrc, eid});
    });
    return items;
}"""

_JS_PRODUCT = r"""() => {
    const title = document.querySelector('h1.x-item-title__mainTitle span, h1[class*="title"]')?.textContent?.trim() || '';
    const priceEl = document.querySelector('.x-price-primary span, [itemprop="price"], .vi-price');
    const price = priceEl?.textContent?.trim() || '';
    const conditionEl = document.querySelector('.x-item-condition-text span, [class*="condition"]');
    const condition = conditionEl?.textContent?.trim() || '';
    const ratingEl = document.querySelector('[class*="star-rating"] span');
    const ratingText = ratingEl?.textContent || '';
    const ratingMatch = ratingText.match(/([\d.]+)/);
    const rating = ratingMatch ? parseFloat(ratingMatch[1]) : 0;
    const sellerEl = document.querySelector('.x-sellercard-atf__info__about-seller a, [class*="seller-name"]');
    const sellerName = sellerEl?.textContent?.trim() || '';

    const imgs = new Set();
    // Main image + thumbnails
    document.querySelectorAll('img[src*="ebayimg"]').forEach(img => {
        const src = img.src || '';
        if (src && !src.includes('s-l64') && !src.includes('icon') && img.width > 40) {
            imgs.add(src);
        }
    });
    // Also check data-src for lazy-loaded images
    document.querySelectorAll('img[data-src*="ebayimg"]').forEach(img => {
        const src = img.getAttribute('data-src') || '';
        if (src) imgs.add(src);
    });

    return {title, price, condition, rating, sellerName, imageUrls: Array.from(imgs)};
}"""


class Ebay:
    """eBay product and search scraper using Camoufox."""

    @staticmethod
    def search(keyword: str, *, headless: bool = True) -> list[dict]:
        """Search eBay and return raw result dicts."""
        search_url = f"{_BASE}/sch/i.html?_nkw={urllib.parse.quote_plus(keyword)}"

        def _scrape() -> list[dict]:
            with fresh_browser(headless=headless) as page:
                page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(1500)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)
                return page.evaluate(_JS_SEARCH)

        return retry_with_backoff(_scrape, description=f"ebay_search({keyword})")

    @staticmethod
    def product(url: str, *, headless: bool = True) -> EbayProduct:
        """Scrape a single eBay product page."""
        ebay_id = _extract_ebay_id(url)

        def _scrape() -> EbayProduct:
            with fresh_browser(headless=headless) as page:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                data = page.evaluate(_JS_PRODUCT)

            images = _make_product_images(data.get("imageUrls", []))
            return EbayProduct(
                ebay_id=ebay_id,
                title=data.get("title", ""),
                price=data.get("price", ""),
                condition=data.get("condition", ""),
                rating=data.get("rating", 0),
                seller_name=data.get("sellerName", ""),
                images=images,
                url=url,
            )

        return retry_with_backoff(_scrape, description=f"ebay_product({ebay_id})")

    @staticmethod
    def search_images(
        keyword: str,
        *,
        top_n: int = 50,
        headless: bool = True,
    ) -> list[EbayProduct]:
        """Search -> get top N products -> scrape all their images."""
        raw_results = Ebay.search(keyword, headless=headless)

        seen: set[str] = set()
        unique: list[dict] = []
        for r in raw_results:
            eid = r.get("eid", "")
            if not eid or eid in seen:
                continue
            seen.add(eid)
            unique.append(r)
            if len(unique) >= top_n:
                break

        logger.info("eBay search '%s': %d unique products", keyword, len(unique))
        products: list[EbayProduct] = []
        total = len(unique)

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures: dict = {}
            for i, sr in enumerate(unique):
                href = sr.get("href", "")
                futures[executor.submit(Ebay.product, href, headless=headless)] = (i, sr)
                time.sleep(0.5)

            for future in as_completed(futures):
                i, sr = futures[future]
                try:
                    product = future.result()
                    products.append(product)
                    logger.info(
                        "[%d/%d] %s... (%d images)",
                        i + 1,
                        total,
                        product.title[:60],
                        len(product.images),
                    )
                except Exception as e:
                    logger.warning("[%d/%d] FAILED: %s", i + 1, total, e)

        return products
