"""Amazon scraper — products, search results, and images."""

from __future__ import annotations

import logging
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

from superscrape.core.browser import fresh_browser
from superscrape.core.retry import retry_with_backoff
from superscrape.output.models import (
    AmazonProduct,
    AmazonSearchResult,
    ProductImage,
)

logger = logging.getLogger(__name__)

_BASE = "https://www.amazon.com"


def _extract_image_ids(raw_urls: list[str]) -> list[ProductImage]:
    """Deduplicate and upgrade Amazon image URLs to hi-res."""
    seen: dict[str, ProductImage] = {}
    for url in raw_urls:
        match = re.search(r"/images/I/([A-Za-z0-9+_-]+)\.", url)
        if not match:
            continue
        img_id = match.group(1)
        if img_id in seen:
            continue
        hi_res = f"https://m.media-amazon.com/images/I/{img_id}._AC_SL1500_.jpg"
        seen[img_id] = ProductImage(url=url, image_id=img_id, hi_res_url=hi_res)
    return list(seen.values())


_JS_EXTRACT_PRODUCT = r"""() => {
    const $ = s => document.querySelector(s);
    const $$ = s => [...document.querySelectorAll(s)];

    // Title
    const title = $("#productTitle")?.textContent?.trim() || "";

    // Price
    const priceEl = $(".a-price .a-offscreen") || $("#priceblock_ourprice") || $("#priceblock_dealprice");
    const price = priceEl?.textContent?.trim() || "";

    // Rating
    const ratingEl = $("span[data-hook='rating-out-of-text']") || $(".a-icon-alt");
    const ratingText = ratingEl?.textContent || "";
    const ratingMatch = ratingText.match(/([\d.]+)/);
    const rating = ratingMatch ? parseFloat(ratingMatch[1]) : 0;

    // Reviews count
    const reviewsEl = $("#acrCustomerReviewCount");
    const reviewsText = reviewsEl?.textContent || "";
    const reviewsMatch = reviewsText.replace(/,/g, "").match(/(\d+)/);
    const reviewsCount = reviewsMatch ? parseInt(reviewsMatch[1]) : 0;

    // Brand
    const brandEl = $("#bylineInfo") || $("a#brand");
    const brand = brandEl?.textContent?.replace(/^(Visit the |Brand: )/, "").trim() || "";

    // Features
    const features = $$("#feature-bullets li span.a-list-item")
        .map(el => el.textContent.trim())
        .filter(t => t.length > 5);

    // Description
    const descEl = $("#productDescription p") || $("#productDescription");
    const description = descEl?.textContent?.trim() || "";

    // BSR
    const bsrEl = $$("#detailBulletsWrapper_feature_div li, #prodDetails td")
        .find(el => el.textContent.includes("Best Sellers Rank"));
    const bsr = bsrEl?.textContent?.trim() || "";

    // Category
    const breadcrumbs = $$("#wayfinding-breadcrumbs_container li a");
    const category = breadcrumbs.map(a => a.textContent.trim()).join(" > ");

    // Images - extract ALL from page
    const imgUrls = new Set();
    $$("img").forEach(img => {
        [img.src, img.getAttribute("data-old-hires")].forEach(u => {
            if (u && u.includes("images/I/")) imgUrls.add(u);
        });
        const dyn = img.getAttribute("data-a-dynamic-image");
        if (dyn) {
            try { Object.keys(JSON.parse(dyn)).forEach(u => imgUrls.add(u)); } catch(e) {}
        }
    });
    // colorImages JS variable
    const scripts = $$("script[type='text/javascript']");
    for (const s of scripts) {
        const text = s.textContent;
        if (text.includes("colorImages") || text.includes("imageGalleryData")) {
            const matches = text.match(/https:\/\/m\.media-amazon\.com\/images\/I\/[^"'\s]+/g);
            if (matches) matches.forEach(u => imgUrls.add(u));
        }
    }
    // innerHTML fallback
    const allMatches = document.body.innerHTML.match(
        /https:\/\/m\.media-amazon\.com\/images\/I\/[A-Za-z0-9+_-]+\.[^"'\s<)]+/g
    );
    if (allMatches) allMatches.forEach(u => {
        if (!u.includes("sprite") && !u.includes("play-button") && !u.includes("icon"))
            imgUrls.add(u);
    });

    return {
        title, price, rating, reviewsCount, brand,
        features, description, bsr, category,
        imageUrls: Array.from(imgUrls),
    };
}"""

_JS_SEARCH_RESULTS = r"""() => {
    return [...document.querySelectorAll('[data-component-type="s-search-result"]')].map(el => {
        const asin = el.getAttribute("data-asin") || "";
        if (!asin) return null;

        const titleEl = el.querySelector("h2 a span") || el.querySelector("h2 span");
        const title = titleEl?.textContent?.trim() || "";

        const priceEl = el.querySelector(".a-price .a-offscreen");
        const price = priceEl?.textContent?.trim() || "";

        // Rating: try aria-label first, then icon alt text
        let rating = 0;
        const ariaEls = el.querySelectorAll("[aria-label]");
        for (const ae of ariaEls) {
            const al = ae.getAttribute("aria-label") || "";
            const m = al.match(/([\d.]+)\s*out of\s*5/);
            if (m) { rating = parseFloat(m[1]); break; }
        }
        if (!rating) {
            const ratingEl = el.querySelector(".a-icon-alt");
            const ratingText = ratingEl?.textContent || "";
            const ratingMatch = ratingText.match(/([\d.]+)/);
            if (ratingMatch) rating = parseFloat(ratingMatch[1]);
        }

        // Reviews: try aria-label "X ratings", then link text "(X)"
        let reviewsCount = 0;
        for (const ae of ariaEls) {
            const al = ae.getAttribute("aria-label") || "";
            if (/\d+\s*ratings?/i.test(al)) {
                const m = al.match(/(\d[\d,]*)\s*ratings?/i);
                if (m) { reviewsCount = parseInt(m[1].replace(/,/g, "")); break; }
            }
        }
        if (!reviewsCount) {
            // Fallback: link text like "(1,234)" near rating stars
            const links = el.querySelectorAll("a");
            for (const link of links) {
                const t = link.textContent.trim();
                const m2 = t.match(/^\(?([\d,]+)\)?$/);
                if (m2 && parseInt(m2[1].replace(/,/g, "")) > 0) {
                    reviewsCount = parseInt(m2[1].replace(/,/g, ""));
                    break;
                }
            }
        }

        const imgEl = el.querySelector(".s-image");
        const imageUrl = imgEl?.src || "";

        const linkEl = el.querySelector("h2 a");
        const href = linkEl?.getAttribute("href") || "";
        const url = href.startsWith("http") ? href : "https://www.amazon.com" + href;

        const sponsored = !!el.querySelector(".puis-sponsored-label-text, .s-label-popover-default");

        return { asin, title, price, rating, reviews_count: reviewsCount, image_url: imageUrl, url, sponsored };
    }).filter(Boolean);
}"""


class Amazon:
    """Amazon product and search scraper."""

    @staticmethod
    def product(asin: str, *, headless: bool = True) -> AmazonProduct:
        """Scrape a single Amazon product by ASIN."""
        url = f"{_BASE}/dp/{asin}"

        def _scrape() -> AmazonProduct:
            with fresh_browser(headless=headless) as page:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                data = page.evaluate(_JS_EXTRACT_PRODUCT)

            images = _extract_image_ids(data["imageUrls"])
            return AmazonProduct(
                asin=asin,
                title=data["title"],
                price=data["price"],
                rating=data["rating"],
                reviews_count=data["reviewsCount"],
                brand=data["brand"],
                features=data["features"],
                description=data["description"],
                bsr=data["bsr"],
                category=data["category"],
                images=images,
                url=url,
            )

        return retry_with_backoff(_scrape, description=f"product({asin})")

    @staticmethod
    def search(
        keyword: str,
        *,
        pages: int = 1,
        headless: bool = True,
    ) -> list[AmazonSearchResult]:
        """Search Amazon and return product listings."""
        results: list[AmazonSearchResult] = []
        with fresh_browser(headless=headless) as page:
            for page_num in range(1, pages + 1):
                search_url = f"{_BASE}/s?k={urllib.parse.quote_plus(keyword)}&page={page_num}"
                page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)

                items = page.evaluate(_JS_SEARCH_RESULTS)
                if not items:
                    title = page.title()
                    logger.warning(
                        "Amazon search page %d returned 0 results (title=%r, url=%s)",
                        page_num,
                        title[:80],
                        page.url[:120],
                    )
                for item in items:
                    results.append(AmazonSearchResult(**item))

                if page_num < pages:
                    time.sleep(2)  # rate limit between pages

        return results

    @staticmethod
    def search_images(
        keyword: str,
        *,
        top_n: int = 50,
        headless: bool = True,
    ) -> list[AmazonProduct]:
        """Search keyword → get top N products → scrape all their images.

        This is the core method for Amazon Visual Intelligence.
        """
        search_results = Amazon.search(keyword, pages=(top_n // 20) + 1, headless=headless)

        # Deduplicate and limit
        seen_asins: set[str] = set()
        unique: list[AmazonSearchResult] = []
        for r in search_results:
            if r.asin and r.asin not in seen_asins and not r.sponsored:
                seen_asins.add(r.asin)
                unique.append(r)
            if len(unique) >= top_n:
                break

        products: list[AmazonProduct] = []
        total = len(unique)

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures: dict = {}
            for i, sr in enumerate(unique):
                futures[executor.submit(Amazon.product, sr.asin, headless=headless)] = (i, sr)
                time.sleep(0.5)  # stagger submissions

            for future in as_completed(futures):
                i, sr = futures[future]
                try:
                    product = future.result()
                    # Merge search result metadata as fallback
                    # (product page sometimes fails to render reviews/rating)
                    if product.reviews_count == 0 and sr.reviews_count > 0:
                        product.reviews_count = sr.reviews_count
                    if product.rating == 0 and sr.rating > 0:
                        product.rating = sr.rating
                    if not product.price and sr.price:
                        product.price = sr.price
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
                    logger.warning("[%d/%d] FAILED %s: %s", i + 1, total, sr.asin, e)

        return products
