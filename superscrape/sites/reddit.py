"""Reddit scraper — subreddits and posts (no login needed)."""

from __future__ import annotations

from superscrape.core.browser import fresh_browser
from superscrape.output.models import RedditPost

_JS_POSTS = r"""() => {
    // Reddit's old.reddit.com is easier to parse
    const posts = [...document.querySelectorAll(".thing.link")].map(el => {
        const id = (el.getAttribute("data-fullname") || "").replace("t3_", "");
        const titleEl = el.querySelector("a.title");
        const title = titleEl?.textContent?.trim() || "";
        const url = titleEl?.getAttribute("href") || "";

        const author = el.getAttribute("data-author") || "";
        const score = parseInt(el.getAttribute("data-score") || "0");

        const commentsEl = el.querySelector(".comments");
        const commentsText = commentsEl?.textContent || "0";
        const commentsMatch = commentsText.match(/(\d+)/);
        const numComments = commentsMatch ? parseInt(commentsMatch[1]) : 0;

        const timeEl = el.querySelector("time");
        const createdUtc = timeEl ? new Date(timeEl.getAttribute("datetime")).getTime() / 1000 : 0;

        const selftext = el.querySelector(".md")?.textContent?.trim() || "";

        return {
            id, title, author, score, numComments,
            url: url.startsWith("http") ? url : "https://www.reddit.com" + url,
            selftext, createdUtc,
        };
    });
    return posts;
}"""


class Reddit:
    """Reddit subreddit scraper (uses old.reddit.com for cleaner HTML)."""

    @staticmethod
    def subreddit(
        name: str,
        *,
        sort: str = "hot",
        limit: int = 25,
        headless: bool = True,
    ) -> list[RedditPost]:
        """Scrape posts from a subreddit."""
        url = f"https://old.reddit.com/r/{name}/{sort}/"
        all_posts: list[RedditPost] = []

        with fresh_browser(headless=headless) as page:
            page.goto(url, timeout=30000)
            page.wait_for_timeout(3000)

            items = page.evaluate(_JS_POSTS)
            for item in items:
                all_posts.append(RedditPost(subreddit=name, **item))
                if len(all_posts) >= limit:
                    break

        return all_posts[:limit]
