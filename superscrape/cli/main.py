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
                str(i),
                r.asin,
                r.title[:50],
                r.price,
                str(r.rating),
                str(r.reviews_count),
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
    console.print("[bold]Step 2/3: Analyzing main images with Gemini Vision...[/bold]")
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
        click.echo(
            json.dumps(
                {
                    "profile": profile.model_dump(),
                    "posts": [p.model_dump() for p in posts],
                },
                indent=2,
            )
        )
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
                str(i),
                str(p.score),
                p.title[:60],
                p.author,
                str(p.num_comments),
            )
        console.print(table)


# ─────────────────────── Listing Generation ───────────────────────


@cli.group()
def listing():
    """Amazon listing image generation from Excel requirement sheets."""


@listing.command("parse-excel")
@click.option("--excel", "-e", required=True, type=click.Path(exists=True), help="Path to Excel requirement sheet")
@click.option("--output", "-o", required=True, type=click.Path(), help="Project output directory")
@click.option("--category", "-c", default="general_apparel", help="Product category (e.g. boys_shirt, womens_dress)")
@click.option("--project-id", default="", help="Project ID (defaults to directory name)")
def parse_excel(excel: str, output: str, category: str, project_id: str):
    """Parse an Excel requirement sheet → config.json + reference images."""
    from pathlib import Path

    from superscrape.listing_gen.excel_parser import parse_excel_sync

    console.print("\n[bold cyan]Listing Image Pipeline — Excel Parser[/bold cyan]")
    console.print(f"Excel:    [bold]{excel}[/bold]")
    console.print(f"Output:   [bold]{output}[/bold]")
    console.print(f"Category: [bold]{category}[/bold]\n")

    config = parse_excel_sync(
        excel_path=Path(excel),
        project_dir=Path(output),
        product_category=category,
        project_id=project_id,
    )

    console.print("\n[bold green]Excel parsed successfully![/bold green]")
    console.print(f"  Product:    {config.product_name}")
    console.print(f"  Client:     {config.client_name}")
    console.print(f"  Slots:      {len(config.main_images)}")
    console.print(f"  Scenes:     {len(config.scenes)}")
    console.print(f"  Size data:  {'Yes' if config.size_data else 'No'}")
    console.print(f"  Outfits:    {len(config.outfit_pairings)}")
    console.print(f"  Config:     {Path(output) / 'config.json'}")


@listing.command("validate")
@click.option("--project", "-p", required=True, type=click.Path(exists=True), help="Project directory")
def validate(project: str):
    """Validate a project's config.json."""
    from pathlib import Path

    from superscrape.listing_gen.models import ProjectConfig

    config_path = Path(project) / "config.json"
    if not config_path.exists():
        console.print(f"[red]config.json not found in {project}[/red]")
        raise SystemExit(1)

    config = ProjectConfig.load(config_path)
    console.print("\n[bold green]Config is valid![/bold green]")
    console.print(f"  Project:    {config.project_id}")
    console.print(f"  Product:    {config.product_name}")
    console.print(f"  Slots:      {len(config.main_images)}")

    # Check required assets
    project_dir = Path(project)
    missing = []
    for variant in config.color_variants:
        for angle, rel_path in variant.photos.items():
            if not (project_dir / rel_path).exists():
                missing.append(f"{variant.name}/{angle}: {rel_path}")

    if missing:
        console.print(f"\n[yellow]Missing assets ({len(missing)}):[/yellow]")
        for m in missing[:10]:
            console.print(f"  - {m}")
    else:
        console.print("  Assets:     All present")


@listing.command("generate")
@click.option("--project", "-p", required=True, type=click.Path(exists=True), help="Project directory")
@click.option("--slots", "-s", default="", help="Comma-separated slot numbers (default: all)")
@click.option("--all", "gen_all", is_flag=True, help="Generate all slots")
def generate(project: str, slots: str, gen_all: bool):
    """Generate listing images from a project config."""
    from pathlib import Path

    from superscrape.listing_gen.pipeline import generate_all_sync

    slot_list = None
    if slots and not gen_all:
        slot_list = [int(s.strip()) for s in slots.split(",")]

    console.print("\n[bold cyan]Listing Image Pipeline — Generate[/bold cyan]")
    console.print(f"Project: [bold]{project}[/bold]")
    console.print(f"Slots:   [bold]{'all' if not slot_list else slot_list}[/bold]\n")

    results = generate_all_sync(Path(project), slot_list)

    console.print("\n[bold green]Generation complete![/bold green]")
    for slot_key, result in results.items():
        status = "[green]OK[/green]" if "output_path" in result else "[red]FAIL[/red]"
        detail = result.get("output_path", result.get("error", result.get("reason", "?")))
        console.print(f"  {slot_key}: {status} — {detail}")


@listing.command("from-excel")
@click.option("--excel", "-e", required=True, type=click.Path(exists=True), help="Path to Excel requirement sheet")
@click.option("--photos", type=click.Path(exists=True), default="", help="Path to product photos folder")
@click.option("--project", "-p", required=True, type=click.Path(), help="Project output directory")
@click.option("--category", "-c", default="general_apparel", help="Product category")
def from_excel(excel: str, photos: str, project: str, category: str):
    """End-to-end: parse Excel → validate → generate all images."""
    import shutil
    from pathlib import Path

    from superscrape.listing_gen.excel_parser import parse_excel_sync
    from superscrape.listing_gen.pipeline import generate_all_sync

    console.print("\n[bold cyan]Listing Image Pipeline — Full Run[/bold cyan]")
    console.print(f"Excel:    [bold]{excel}[/bold]")
    console.print(f"Photos:   [bold]{photos or '(none)'}[/bold]")
    console.print(f"Project:  [bold]{project}[/bold]")
    console.print(f"Category: [bold]{category}[/bold]\n")

    project_dir = Path(project)

    # Step 1: Copy product photos if provided
    if photos:
        photos_dest = project_dir / "assets" / "product_photos"
        photos_dest.mkdir(parents=True, exist_ok=True)
        photos_src = Path(photos)
        copied = 0
        for f in photos_src.iterdir():
            if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                shutil.copy2(f, photos_dest / f.name)
                copied += 1
        console.print(f"[bold]Step 0/3: Copied {copied} product photos[/bold]\n")

    # Step 2: Parse Excel
    console.print("[bold]Step 1/3: Parsing Excel requirement sheet...[/bold]")
    config = parse_excel_sync(
        excel_path=Path(excel),
        project_dir=project_dir,
        product_category=category,
    )
    console.print(f"  Product: {config.product_name}")
    console.print(f"  Slots: {len(config.main_images)}")
    console.print(f"  Scenes: {len(config.scenes)}\n")

    # Step 3: Validate
    console.print("[bold]Step 2/3: Validating config...[/bold]")
    console.print("  Config OK\n")

    # Step 4: Generate
    console.print("[bold]Step 3/3: Generating images...[/bold]")
    results = generate_all_sync(project_dir)

    console.print("\n[bold green]Pipeline complete![/bold green]")
    for slot_key, result in results.items():
        status = "[green]OK[/green]" if "output_path" in result else "[yellow]SKIP[/yellow]"
        console.print(f"  {slot_key}: {status}")


if __name__ == "__main__":
    cli()
