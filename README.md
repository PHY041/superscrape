# SuperScrape

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CI](https://github.com/PHY041/superscrape/actions/workflows/ci.yml/badge.svg)](https://github.com/PHY041/superscrape/actions)

**Web scraping + AI visual intelligence that just works -- anti-bot era edition.**

SuperScrape uses [Camoufox](https://github.com/daijro/camoufox) (C++ anti-detection Firefox) to scrape sites that block Playwright, Selenium, and curl. Then it analyzes product images with GPT Vision to generate competitive intelligence reports.

```bash
# Scrape Amazon product images + run AI analysis
superscrape amazon visual "portable blender" --top 10
```

## Features

- **Anti-bot scraping** -- Camoufox bypasses Cloudflare, DataDome, and other bot detection
- **Amazon** -- Product pages, search results, image extraction with hi-res upgrade
- **Instagram** -- Public profiles, recent posts, follower counts
- **Reddit** -- Subreddit posts with sorting and filtering
- **eBay, Walmart, Etsy, Shopee** -- Additional e-commerce platforms
- **Visual Intelligence** -- GPT Vision analyzes product images (type, angle, background, text, people)
- **Reports** -- Markdown + JSON reports with category-level insights and recommendations

## Prerequisites

- Python 3.10+
- An OpenAI API key (for Visual Intelligence features)

## Installation

```bash
pip install superscrape

# Install the Camoufox browser binary
python -c "from camoufox.sync_api import Camoufox; print('ready')"
```

Or install from source:

```bash
git clone https://github.com/PHY041/superscrape.git
cd superscrape
pip install -e ".[dev]"
```

## Quick Start

```bash
# 1. Set your OpenAI API key (needed for visual analysis)
export OPENAI_API_KEY="sk-..."

# 2. Scrape a single Amazon product
superscrape amazon product B0CX23V2ZK

# 3. Search Amazon
superscrape amazon search "wireless earbuds" --pages 2

# 4. Run full visual intelligence pipeline
superscrape amazon visual "boys dress shirt" --top 10 --output-dir ./reports

# 5. Scrape Instagram
superscrape instagram natgeo

# 6. Scrape Reddit
superscrape reddit SideProject --sort hot --limit 50
```

## CLI Reference

```
superscrape
  amazon
    product <ASIN>              Scrape a single product
    search <KEYWORD>            Search results with pagination
    visual <KEYWORD>            Full visual intelligence pipeline
  instagram <USERNAME>          Public profile + recent posts
  reddit <SUBREDDIT>            Posts with sorting (hot/new/top)
```

### Options

| Command | Flag | Description |
|---------|------|-------------|
| `amazon product` | `--images-only` | Only output image URLs |
| `amazon search` | `--pages N` | Number of search pages |
| `amazon visual` | `--top N` | Number of products to analyze |
| `amazon visual` | `--no-cache` | Bypass cached results |
| `amazon visual` | `--output-dir DIR` | Output directory |
| `reddit` | `--sort hot\|new\|top` | Sort order |
| `reddit` | `--limit N` | Max posts to fetch |
| All commands | `--output json\|table` | Output format |

## Python API

```python
from superscrape.sites.amazon import Amazon
from superscrape.analyzers.vision import batch_analyze_first_images
from superscrape.reporters.visual_report import aggregate_report, render_markdown

# Scrape
products = Amazon.search_images("portable blender", top_n=10)

# Analyze with GPT Vision
analyses = batch_analyze_first_images(products)

# Generate report
report = aggregate_report("portable blender", products, analyses)
markdown = render_markdown(report)
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | For visual analysis | OpenAI API key for GPT Vision |
| `BYTEPLUSES_API_KEY` | Optional | BytePlus API key for lifestyle image generation |

## API Server (Optional)

SuperScrape includes an optional FastAPI server with real-time job tracking:

```bash
# Install API dependencies
pip install "superscrape[api]"

# Start the server
uvicorn api.main:app --host 0.0.0.0 --port 8001

# Or use Docker
docker compose up --build
```

API endpoints:
- `POST /jobs` -- Submit a scraping + analysis job
- `GET /jobs/{id}` -- Job status
- `GET /jobs/{id}/stream` -- SSE real-time progress
- `GET /reports` -- List generated reports
- `GET /health` -- Health check

## Architecture

```
CLI / API Request
    |
    v
+---------------------------+
|  Scraping Layer            |
|  sites/amazon.py           |
|  sites/instagram.py        |
|  sites/reddit.py           |
+------------+--------------+
             |
             v
      Camoufox Browser
      (C++ anti-detection)
             |
             v
+---------------------------+
|  AI Analysis               |
|  analyzers/vision.py       |
|  (OpenAI GPT Vision)       |
+------------+--------------+
             |
             v
+---------------------------+
|  Reports                   |
|  reporters/visual_report   |
|  Markdown + JSON + HTML    |
+---------------------------+
```

## Anti-Bot Test Results

Tested with Camoufox against major platforms:

| Platform | Status | Notes |
|----------|--------|-------|
| Amazon | Pass | Search, product pages, images |
| Instagram | Pass | Public profiles, no login required |
| Reddit | Pass | Playwright+stealth gets blocked, Camoufox passes |
| eBay | Pass | Product listings, prices |
| Walmart | Pass | Product pages |
| Etsy | Pass | Listings, prices |
| Cloudflare Challenge | Pass | Generic CF challenge page |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

MIT License -- see [LICENSE](LICENSE) for details.

Powered by [CanMarket](https://canmarket.ai).
