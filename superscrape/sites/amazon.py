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
    AplusImage,
    ProductImage,
    Review,
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

    // Images - ONLY from product gallery (not the whole page)
    const imgUrls = new Set();

    // Source 1 (BEST): colorImages JS variable — the actual product gallery data
    const scripts = $$("script[type='text/javascript']");
    for (const s of scripts) {
        const text = s.textContent;
        // colorImages contains: 'colorImages': { 'initial': [{ hiRes: "...", large: "...", ... }] }
        if (text.includes("colorImages")) {
            const hiResMatches = text.match(/"hiRes"\s*:\s*"(https:\/\/m\.media-amazon\.com\/images\/I\/[^"]+)"/g);
            if (hiResMatches) {
                hiResMatches.forEach(m => {
                    const url = m.match(/"(https:\/\/[^"]+)"/);
                    if (url) imgUrls.add(url[1]);
                });
            }
            // Also grab "large" as fallback
            const largeMatches = text.match(/"large"\s*:\s*"(https:\/\/m\.media-amazon\.com\/images\/I\/[^"]+)"/g);
            if (largeMatches && imgUrls.size === 0) {
                largeMatches.forEach(m => {
                    const url = m.match(/"(https:\/\/[^"]+)"/);
                    if (url) imgUrls.add(url[1]);
                });
            }
        }
        // imageGalleryData fallback
        if (text.includes("imageGalleryData") && imgUrls.size === 0) {
            const matches = text.match(/https:\/\/m\.media-amazon\.com\/images\/I\/[^"'\s]+/g);
            if (matches) matches.forEach(u => imgUrls.add(u));
        }
    }

    // Source 2: #imageBlock / #altImages container — thumbnail strip (scoped to gallery only)
    if (imgUrls.size === 0) {
        const galleryContainer = $("#imageBlock") || $("#altImages");
        if (galleryContainer) {
            galleryContainer.querySelectorAll("img").forEach(img => {
                [img.src, img.getAttribute("data-old-hires")].forEach(u => {
                    if (u && u.includes("images/I/")) imgUrls.add(u);
                });
                const dyn = img.getAttribute("data-a-dynamic-image");
                if (dyn) {
                    try { Object.keys(JSON.parse(dyn)).forEach(u => imgUrls.add(u)); } catch(e) {}
                }
            });
        }
    }

    // Source 3: main image element only (last resort)
    if (imgUrls.size === 0) {
        const mainImg = $("#landingImage") || $("#imgBlkFront");
        if (mainImg) {
            const src = mainImg.src || mainImg.getAttribute("data-old-hires") || "";
            if (src.includes("images/I/")) imgUrls.add(src);
            const dyn = mainImg.getAttribute("data-a-dynamic-image");
            if (dyn) {
                try { Object.keys(JSON.parse(dyn)).forEach(u => imgUrls.add(u)); } catch(e) {}
            }
        }
    }

    // --- A+ / Enhanced Brand Content images (deduplicated) ---
    const aplusImages = [];
    const aplusSeenUrls = new Set();
    const aplusSelectors = [
        "#aplus", "#aplusBrand_feature_div", "#aplus_feature_div",
        "[id*='aplus']", ".aplus-module", ".apm-wrap",
        "#productDescription_feature_div .aplus-v2",
    ];
    const aplusContainers = new Set();
    for (const sel of aplusSelectors) {
        document.querySelectorAll(sel).forEach(el => aplusContainers.add(el));
    }
    for (const container of aplusContainers) {
        container.querySelectorAll("img").forEach(img => {
            const src = img.src || img.getAttribute("data-src") || "";
            if (!src || src.length < 20) return;
            // Only A+ media library images (ignore product gallery images in A+ area)
            if (!src.includes("aplus-media")) return;
            // Deduplicate by base URL (strip size suffixes like __CR0,0,1464,600_...)
            const baseUrl = src.replace(/\.__[^.]+\.(jpg|png|webp)/i, "");
            if (aplusSeenUrls.has(baseUrl)) return;
            aplusSeenUrls.add(baseUrl);
            // Skip tiny icons/sprites
            const w = img.naturalWidth || parseInt(img.getAttribute("width") || "0");
            const h = img.naturalHeight || parseInt(img.getAttribute("height") || "0");
            if (w > 0 && w < 50) return;
            // Detect module type from parent classes
            const parentClasses = (img.closest("[class*='aplus']") || img.parentElement)?.className || "";
            let moduleType = "unknown";
            if (parentClasses.includes("brand-story")) moduleType = "brand-story";
            else if (parentClasses.includes("comparison")) moduleType = "comparison";
            else if (parentClasses.includes("standard-image") || parentClasses.includes("hero")) moduleType = "standard-image";
            else if (parentClasses.includes("four-image") || parentClasses.includes("three-image")) moduleType = "multi-image";
            else moduleType = "standard";
            aplusImages.push({
                url: src,
                module_type: moduleType,
                alt_text: (img.alt || "").substring(0, 200),
                width: w,
                height: h,
            });
        });
    }

    // --- Top Reviews ---
    const reviews = [];
    const reviewCards = $$("[data-hook='review']");
    for (const card of reviewCards.slice(0, 10)) {
        const starsEl = card.querySelector("[data-hook='review-star-rating'] .a-icon-alt, .review-rating .a-icon-alt");
        const starsText = starsEl?.textContent || "";
        const starsMatch = starsText.match(/([\d.]+)/);
        const stars = starsMatch ? parseFloat(starsMatch[1]) : 0;
        const textEl = card.querySelector("[data-hook='review-body'] span");
        const text = textEl?.textContent?.trim() || "";
        const authorEl = card.querySelector(".a-profile-name");
        const author = authorEl?.textContent?.trim() || "";
        const dateEl = card.querySelector("[data-hook='review-date']");
        const date = dateEl?.textContent?.trim() || "";
        const verified = !!card.querySelector("[data-hook='avp-badge']");
        if (text.length > 10) {
            reviews.push({ text: text.substring(0, 500), stars, author, date, verified });
        }
    }

    return {
        title, price, rating, reviewsCount, brand,
        features, description, bsr, category,
        imageUrls: Array.from(imgUrls),
        aplusImages,
        reviews,
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
                page.goto(url, timeout=60000, wait_until="networkidle")

                # Wait for product title to appear (up to 10s)
                try:
                    page.wait_for_selector("#productTitle, #title_feature_div", timeout=10000)
                except Exception:
                    pass  # Fall through to validation below

                # Detect bot/CAPTCHA pages — raise so retry_with_backoff can retry
                page_title = page.title() or ""
                page_url = page.url or ""
                if any(s in page_title.lower() for s in ["robot", "captcha", "verify", "sorry"]):
                    raise RuntimeError(f"Bot detection page for {asin}: title={page_title!r}")
                if "validateCaptcha" in page_url or "/errors/" in page_url:
                    raise RuntimeError(f"CAPTCHA redirect for {asin}: url={page_url}")

                # Check that the product page actually loaded
                has_product = page.evaluate("!!document.querySelector('#productTitle, #title, #dp-container')")
                if not has_product:
                    raise RuntimeError(f"Product page did not load for {asin}: title={page_title!r}")

                # Scroll down to load lazy A+ content
                for _ in range(6):
                    page.evaluate("window.scrollBy(0, window.innerHeight)")
                    page.wait_for_timeout(800)
                # Scroll back to top
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(500)

                data = page.evaluate(_JS_EXTRACT_PRODUCT)

            images = _extract_image_ids(data["imageUrls"])
            aplus_images = [
                AplusImage(**img) for img in data.get("aplusImages", [])
            ]
            reviews = [
                Review(**r) for r in data.get("reviews", [])
            ]
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
                aplus_images=aplus_images,
                reviews=reviews,
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
    def bestsellers(
        node_id: str,
        *,
        headless: bool = True,
    ) -> list[AmazonSearchResult]:
        """Scrape Best Seller page for a category node ID.

        Returns up to 50 products (page 1 of best sellers).
        """
        url = f"{_BASE}/Best-Sellers/zgbs/fashion/{node_id}"
        results: list[AmazonSearchResult] = []

        js_extract = """() => {
            const items = [];
            const seen = new Set();
            const cards = document.querySelectorAll("[data-asin]");
            cards.forEach(card => {
                const asin = card.getAttribute("data-asin") || "";
                if (!asin || seen.has(asin)) return;
                seen.add(asin);
                const link = card.querySelector("a.a-link-normal");
                const href = link ? link.getAttribute("href") || "" : "";
                const titleEl = card.querySelector("[class*='line-clamp'], .p13n-sc-truncate, .zg-text-center-align");
                const title = titleEl ? titleEl.textContent.trim() : (link ? link.textContent.trim() : "");
                const priceEl = card.querySelector(".a-price .a-offscreen, [class*='price']");
                const price = priceEl ? priceEl.textContent.trim() : "";
                const rankEl = card.querySelector(".zg-bdg-text");
                const rank = rankEl ? rankEl.textContent.trim().replace("#", "") : "";
                const imgEl = card.querySelector("img");
                const image_url = imgEl ? imgEl.src : "";
                const fullUrl = href.startsWith("http") ? href : "https://www.amazon.com" + href;
                items.push({asin, title: title.substring(0, 200), price, rank, image_url, url: fullUrl, sponsored: false, reviews_count: 0, rating: 0});
            });
            return items;
        }"""

        with fresh_browser(headless=headless) as page:
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            # Scroll to load lazy items
            for _ in range(4):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(600)

            items = page.evaluate(js_extract)
            for item in items:
                item.pop("rank", None)
                results.append(AmazonSearchResult(**item))

        logger.info("bestsellers(%s): %d products found", node_id, len(results))
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
