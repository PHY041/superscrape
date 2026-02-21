"""Instagram scraper — public profiles and posts."""

from __future__ import annotations

from superscrape.core.browser import fresh_browser
from superscrape.output.models import InstagramPost, InstagramProfile

_JS_PROFILE = r"""() => {
    const meta = document.querySelectorAll("meta");
    let description = "";
    meta.forEach(m => {
        if (m.getAttribute("name") === "description" || m.getAttribute("property") === "og:description") {
            description = m.getAttribute("content") || "";
        }
    });

    // Try to parse numbers from description like "1.2M Followers, 200 Following, 500 Posts"
    const numMatch = description.match(/([\d,.]+[KMB]?)\s+Followers.*?([\d,.]+[KMB]?)\s+Following.*?([\d,.]+[KMB]?)\s+Posts/i);

    function parseNum(s) {
        if (!s) return 0;
        s = s.replace(/,/g, "");
        if (s.endsWith("K")) return parseFloat(s) * 1000;
        if (s.endsWith("M")) return parseFloat(s) * 1000000;
        if (s.endsWith("B")) return parseFloat(s) * 1000000000;
        return parseInt(s) || 0;
    }

    const followers = numMatch ? parseNum(numMatch[1]) : 0;
    const following = numMatch ? parseNum(numMatch[2]) : 0;
    const postsCount = numMatch ? parseNum(numMatch[3]) : 0;

    // Bio text from description (after the dash)
    const bioPart = description.split(" - ").slice(1).join(" - ").trim();

    // Profile pic
    const profilePic = document.querySelector('img[alt*="profile picture"]')?.src || "";

    // Full name from header
    const headerEl = document.querySelector("header section span") || document.querySelector("header h2");
    const fullName = headerEl?.textContent?.trim() || "";

    // Verified badge
    const verified = !!document.querySelector('[aria-label="Verified"]');

    // Posts
    const posts = [...document.querySelectorAll("article a[href*='/p/']")].map(a => {
        const img = a.querySelector("img");
        const href = a.getAttribute("href") || "";
        const shortcode = href.match(/\/p\/([^/]+)/)?.[1] || "";

        const altText = img?.getAttribute("alt") || "";
        const likesMatch = altText.match(/([\d,]+)\s+likes?/i);
        const commentsMatch = altText.match(/([\d,]+)\s+comments?/i);

        return {
            shortcode,
            imageUrl: img?.src || "",
            caption: altText,
            likes: likesMatch ? parseInt(likesMatch[1].replace(/,/g, "")) : 0,
            comments: commentsMatch ? parseInt(commentsMatch[1].replace(/,/g, "")) : 0,
            url: "https://www.instagram.com" + href,
            isVideo: !!a.querySelector('[aria-label*="Video"], [aria-label*="Reel"]'),
        };
    }).filter(p => p.shortcode);

    return { followers, following, postsCount, bio: bioPart, profilePic, fullName, verified, posts };
}"""


class Instagram:
    """Instagram public profile scraper."""

    @staticmethod
    def profile(username: str, *, headless: bool = True) -> tuple[InstagramProfile, list[InstagramPost]]:
        """Scrape a public Instagram profile and its recent posts."""
        url = f"https://www.instagram.com/{username}/"
        with fresh_browser(headless=headless) as page:
            page.goto(url, timeout=30000)
            page.wait_for_timeout(4000)

            data = page.evaluate(_JS_PROFILE)

        profile = InstagramProfile(
            username=username,
            full_name=data["fullName"],
            bio=data["bio"],
            followers=data["followers"],
            following=data["following"],
            posts_count=data["postsCount"],
            profile_pic_url=data["profilePic"],
            is_verified=data["verified"],
        )

        posts = [
            InstagramPost(
                shortcode=p["shortcode"],
                image_url=p["imageUrl"],
                caption=p["caption"],
                likes=p["likes"],
                comments=p["comments"],
                url=p["url"],
                is_video=p["isVideo"],
            )
            for p in data["posts"]
        ]

        return profile, posts
