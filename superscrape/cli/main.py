"""SuperScrape CLI — scrape anything from the command line."""

from __future__ import annotations

import json
import logging

import click
from rich.console import Console
from rich.table import Table

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

console = Console()


@click.group()
@click.version_option(package_name="superscrape")
def cli():
    """SuperScrape — Web scraping that just works in the anti-bot era."""


# ─────────────────────────── Amazon ───────────────────────────


@cli.group()
def amazon():
    """Amazon product scraping."""


@amazon.command()
@click.argument("asin")
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table")
@click.option("--images-only", is_flag=True, help="Only output image URLs")
def product(asin: str, output: str, images_only: bool):
    """Scrape a single Amazon product by ASIN."""
    from superscrape.sites.amazon import Amazon

    console.print(f"[bold]Scraping Amazon product {asin}...[/bold]")
    p = Amazon.product(asin)

    if images_only:
        for img in p.images:
            click.echo(img.hi_res_url)
        return

    if output == "json":
        click.echo(p.model_dump_json(indent=2))
    else:
        table = Table(title=f"Amazon Product: {asin}")
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        table.add_row("Title", p.title[:80])
        table.add_row("Price", p.price)
        table.add_row("Rating", f"{p.rating} ({p.reviews_count} reviews)")
        table.add_row("Brand", p.brand)
        table.add_row("Images", str(len(p.images)))
        table.add_row("Category", p.category[:60] if p.category else "")
        console.print(table)


@amazon.command()
@click.argument("keyword")
@click.option("--pages", "-p", default=1, help="Number of search pages")
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table")
def search(keyword: str, pages: int, output: str):
    """Search Amazon for products."""
    from superscrape.sites.amazon import Amazon

    console.print(f"[bold]Searching Amazon for '{keyword}'...[/bold]")
    results = Amazon.search(keyword, pages=pages)

    if output == "json":
        click.echo(json.dumps([r.model_dump() for r in results], indent=2))
    else:
        table = Table(title=f"Amazon Search: '{keyword}' ({len(results)} results)")
        table.add_column("#", style="dim")
        table.add_column("ASIN", style="cyan")
        table.add_column("Title")
        table.add_column("Price", style="green")
        table.add_column("Rating")
        table.add_column("Reviews")
        for i, r in enumerate(results, 1):
            table.add_row(
                str(i), r.asin, r.title[:50], r.price,
                str(r.rating), str(r.reviews_count),
            )
        console.print(table)


# ─────────────────────── Visual Intelligence ───────────────────────


@amazon.command("visual")
@click.argument("keyword")
@click.option("--top", "-n", default=10, help="Number of top products to analyze")
@click.option("--output-dir", "-d", default=".", help="Output directory for report")
@click.option("--no-cache", is_flag=True, help="Bypass cached results and re-scrape")
def visual(keyword: str, top: int, output_dir: str, no_cache: bool):
    """Run Amazon Visual Intelligence analysis on a product category."""
    import os

    from superscrape.analyzers.vision import batch_analyze_first_images
    from superscrape.core.cache import get_cached, save_cache
    from superscrape.output.models import AmazonProduct
    from superscrape.reporters.visual_report import aggregate_report, render_markdown
    from superscrape.sites.amazon import Amazon

    console.print("\n[bold cyan]Amazon Visual Intelligence[/bold cyan]")
    console.print(f"Keyword: [bold]{keyword}[/bold]")
    console.print(f"Top products: {top}\n")

    # Check cache first (unless --no-cache)
    cached = None if no_cache else get_cached(keyword, top)
    if cached is not None:
        console.print("[dim]Using cached scrape results (pass --no-cache to re-scrape)[/dim]\n")
        products = [AmazonProduct(**p) for p in cached["products"]]
    else:
        # Step 1: Search and scrape
        console.print("[bold]Step 1/3: Scraping product images...[/bold]")
        products = Amazon.search_images(keyword, top_n=top)
        total_images = sum(len(p.images) for p in products)
        console.print(f"  Scraped {len(products)} products, {total_images} total images\n")
        save_cache(keyword, top, {"products": [p.model_dump() for p in products]})

    # Step 2: AI Analysis
    console.print("[bold]Step 2/3: Analyzing main images with GPT Vision...[/bold]")
    analyses = batch_analyze_first_images(products)
    console.print(f"  Analyzed {len(analyses)} images\n")

    # Step 3: Generate report
    console.print("[bold]Step 3/3: Generating visual intelligence report...[/bold]")
    report = aggregate_report(keyword, products, analyses)
    markdown = render_markdown(report)

    # Save
    safe_keyword = keyword.replace(" ", "_").replace("/", "_")
    report_path = os.path.join(output_dir, f"visual_report_{safe_keyword}.md")
    json_path = os.path.join(output_dir, f"visual_report_{safe_keyword}.json")

    with open(report_path, "w") as f:
        f.write(markdown)
    with open(json_path, "w") as f:
        f.write(report.model_dump_json(indent=2))

    console.print("\n[bold green]Done![/bold green]")
    console.print(f"  Report: {report_path}")
    console.print(f"  Data:   {json_path}")
    console.print("\n[dim]Preview:[/dim]\n")
    # Print first 30 lines of the report
    for line in markdown.split("\n")[:30]:
        console.print(line)


# ─────────────────────────── Instagram ───────────────────────────


@cli.command()
@click.argument("username")
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table")
def instagram(username: str, output: str):
    """Scrape a public Instagram profile."""
    from superscrape.sites.instagram import Instagram

    console.print(f"[bold]Scraping Instagram @{username}...[/bold]")
    profile, posts = Instagram.profile(username)

    if output == "json":
        click.echo(json.dumps({
            "profile": profile.model_dump(),
            "posts": [p.model_dump() for p in posts],
        }, indent=2))
    else:
        table = Table(title=f"Instagram: @{username}")
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        table.add_row("Name", profile.full_name)
        table.add_row("Bio", profile.bio[:80] if profile.bio else "")
        table.add_row("Followers", f"{profile.followers:,}")
        table.add_row("Following", f"{profile.following:,}")
        table.add_row("Posts", str(profile.posts_count))
        table.add_row("Verified", "Yes" if profile.is_verified else "No")
        table.add_row("Recent Posts", str(len(posts)))
        console.print(table)


# ─────────────────────────── Reddit ───────────────────────────


@cli.command()
@click.argument("subreddit")
@click.option("--sort", "-s", type=click.Choice(["hot", "new", "top"]), default="hot")
@click.option("--limit", "-l", default=25)
@click.option("--output", "-o", type=click.Choice(["json", "table"]), default="table")
def reddit(subreddit: str, sort: str, limit: int, output: str):
    """Scrape posts from a subreddit."""
    from superscrape.sites.reddit import Reddit

    console.print(f"[bold]Scraping r/{subreddit} ({sort})...[/bold]")
    posts = Reddit.subreddit(subreddit, sort=sort, limit=limit)

    if output == "json":
        click.echo(json.dumps([p.model_dump() for p in posts], indent=2))
    else:
        table = Table(title=f"r/{subreddit} \u2014 {sort} ({len(posts)} posts)")
        table.add_column("#", style="dim")
        table.add_column("Score", style="green")
        table.add_column("Title")
        table.add_column("Author", style="cyan")
        table.add_column("Comments")
        for i, p in enumerate(posts, 1):
            table.add_row(
                str(i), str(p.score), p.title[:60],
                p.author, str(p.num_comments),
            )
        console.print(table)


if __name__ == "__main__":
    cli()
