"""Batch CLIP processing client — optimized for 1M+ images.

Supports multiple tasks via --task flag:
  embed     : Generate 768-dim CLIP embeddings
  score     : Score images against text prompts (similarity)
  classify  : Zero-shot classification with label list

Usage:
    python scripts/clip_batch_client.py --task embed --batch-size 64 --workers 32
    python scripts/clip_batch_client.py --task score --texts "high quality" "low quality" --workers 32
    python scripts/clip_batch_client.py --task classify --labels labels.txt --workers 32

    # Custom data source (default: Supabase image_embeddings table)
    python scripts/clip_batch_client.py --task embed --input urls.txt
    python scripts/clip_batch_client.py --task embed --input data.jsonl --url-field image_url

Output: JSONL file with results per image
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import logging
import os
import time
from pathlib import Path
from threading import Lock

import aiohttp
from PIL import Image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

def get_clip_api() -> str:
    return os.environ.get("CLIP_API_URL", "http://10.96.189.13:30001")
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "projects" / "clothing_images"
MAX_IMAGE_PIXELS = 512 * 512  # Smaller for CLIP (224x224 anyway)


def load_urls_from_supabase() -> list[dict]:
    """Load image URLs from Supabase."""
    try:
        from supabase import create_client
    except ImportError:
        log.error("pip install supabase first")
        raise

    url = os.environ.get("PERSONAL_SUPABASE_URL", "")
    key = os.environ.get("PERSONAL_SUPABASE_KEY", "")
    client = create_client(url, key)

    log.info("Loading URLs from Supabase...")
    all_rows = []
    offset = 0
    batch = 1000
    while True:
        resp = client.table("image_embeddings").select("content_hash,image_url,category").range(offset, offset + batch - 1).execute()
        rows = resp.data
        if not rows:
            break
        all_rows.extend(rows)
        offset += batch
        if len(rows) < batch:
            break

    log.info("Loaded %d URLs from Supabase", len(all_rows))
    return [{"id": r["content_hash"], "url": r["image_url"], "category": r.get("category", "")} for r in all_rows]


def load_urls_from_file(path: str, url_field: str = "url") -> list[dict]:
    """Load URLs from a text file (one per line) or JSONL."""
    items = []
    with open(path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            if line.startswith("{"):
                d = json.loads(line)
                items.append({"id": str(i), "url": d[url_field]})
            else:
                items.append({"id": str(i), "url": line})
    log.info("Loaded %d URLs from %s", len(items), path)
    return items


def load_done_ids(output_file: Path) -> set[str]:
    """Load already-processed IDs."""
    done = set()
    if output_file.exists():
        for line in output_file.read_text().strip().split("\n"):
            if line:
                try:
                    done.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return done


async def download_image(session: aiohttp.ClientSession, url: str) -> str | None:
    """Download and resize image, return base64."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            raw = await resp.read()

        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        if w * h > MAX_IMAGE_PIXELS:
            scale = (MAX_IMAGE_PIXELS / (w * h)) ** 0.5
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


async def process_batch_embed(
    session: aiohttp.ClientSession,
    batch: list[dict],
    images_b64: list[str | None],
) -> list[dict]:
    """Send batch to /embed_images_batch endpoint."""
    valid = [(item, b64) for item, b64 in zip(batch, images_b64) if b64]
    if not valid:
        return []

    payload = {"images": [b64 for _, b64 in valid], "normalize": True}
    try:
        async with session.post(
            f"{get_clip_api()}/embed_images_batch",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception:
        return []

    results = []
    embeddings = data.get("embeddings", [])
    for i, (item, _) in enumerate(valid):
        if i < len(embeddings) and embeddings[i] is not None:
            results.append({
                "id": item["id"],
                "url": item["url"],
                "embedding": embeddings[i],
            })
    return results


async def process_batch_score(
    session: aiohttp.ClientSession,
    batch: list[dict],
    images_b64: list[str | None],
    texts: list[str],
) -> list[dict]:
    """Score each image against text prompts via /similarity."""
    results = []
    for item, b64 in zip(batch, images_b64):
        if not b64:
            continue
        try:
            async with session.post(
                f"{get_clip_api()}/similarity",
                json={"image": b64, "texts": texts},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                scores = {s["text"]: s["score"] for s in data.get("text_scores", [])}
                results.append({"id": item["id"], "url": item["url"], "scores": scores})
        except Exception:
            continue
    return results


async def process_batch_classify(
    session: aiohttp.ClientSession,
    batch: list[dict],
    images_b64: list[str | None],
    labels: list[str],
) -> list[dict]:
    """Zero-shot classify images into labels."""
    results = []
    for item, b64 in zip(batch, images_b64):
        if not b64:
            continue
        try:
            async with session.post(
                f"{get_clip_api()}/similarity",
                json={"image": b64, "texts": labels},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                text_scores = data.get("text_scores", [])
                if text_scores:
                    best = max(text_scores, key=lambda x: x["score"])
                    results.append({
                        "id": item["id"],
                        "url": item["url"],
                        "label": best["text"],
                        "confidence": best["score"],
                        "all_scores": {s["text"]: s["score"] for s in text_scores},
                    })
        except Exception:
            continue
    return results


async def run_pipeline(
    items: list[dict],
    output_file: Path,
    task: str,
    batch_size: int = 64,
    max_concurrent_batches: int = 4,
    texts: list[str] | None = None,
    labels: list[str] | None = None,
):
    """Main async pipeline."""
    done_ids = load_done_ids(output_file)
    remaining = [item for item in items if item["id"] not in done_ids]

    if not remaining:
        log.info("All %d items already processed!", len(items))
        return

    log.info("To process: %d (skipping %d done) | batch=%d | task=%s",
             len(remaining), len(items) - len(remaining), batch_size, task)

    write_lock = Lock()
    total_done = 0
    total_failed = 0
    t_start = time.time()

    connector = aiohttp.TCPConnector(limit=100, limit_per_host=100)
    async with aiohttp.ClientSession(
        connector=connector,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as session:
        semaphore = asyncio.Semaphore(max_concurrent_batches)

        async def process_one_batch(batch_idx: int, batch: list[dict]):
            nonlocal total_done, total_failed

            async with semaphore:
                # Download all images in batch concurrently
                download_tasks = [download_image(session, item["url"]) for item in batch]
                images_b64 = await asyncio.gather(*download_tasks)

                # Process batch
                if task == "embed":
                    results = await process_batch_embed(session, batch, images_b64)
                elif task == "score":
                    results = await process_batch_score(session, batch, images_b64, texts)
                elif task == "classify":
                    results = await process_batch_classify(session, batch, images_b64, labels)
                else:
                    results = []

                # Write results
                if results:
                    with write_lock:
                        with open(output_file, "a") as f:
                            for r in results:
                                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                            if total_done % 500 == 0:
                                f.flush()

                failed = len(batch) - len(results)
                total_done += len(results)
                total_failed += failed

                if total_done % 500 < batch_size or batch_idx < 3:
                    elapsed = time.time() - t_start
                    rate = total_done / (elapsed / 60) if elapsed > 0 else 0
                    eta = (len(remaining) - total_done) / rate if rate > 0 else 0
                    log.info(
                        "[%d/%d] %.0f/min | ETA %.0fm | fails: %d",
                        total_done, len(remaining), rate, eta, total_failed,
                    )

        # Create all batch tasks
        batches = [remaining[i:i + batch_size] for i in range(0, len(remaining), batch_size)]
        tasks = [process_one_batch(i, batch) for i, batch in enumerate(batches)]
        await asyncio.gather(*tasks)

    elapsed = time.time() - t_start
    rate = total_done / (elapsed / 60) if elapsed > 0 else 0
    log.info("Done: %d processed, %d failed in %.0fs (%.0f/min)", total_done, total_failed, elapsed, rate)


def main():
    parser = argparse.ArgumentParser(description="Batch CLIP processing client")
    parser.add_argument("--task", choices=["embed", "score", "classify"], default="embed",
                        help="Task type: embed (embeddings), score (text similarity), classify (zero-shot)")
    parser.add_argument("--input", type=str, default=None,
                        help="Input file (URLs text or JSONL). Default: Supabase")
    parser.add_argument("--url-field", type=str, default="url",
                        help="URL field name in JSONL input")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSONL file. Default: auto-named")
    parser.add_argument("--batch-size", type=int, default=64,
                        help="Images per batch (for embed endpoint)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Max concurrent batches")
    parser.add_argument("--texts", nargs="+", type=str, default=None,
                        help="Text prompts for score task")
    parser.add_argument("--labels", type=str, default=None,
                        help="Labels file for classify task (one per line)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of images (for testing)")
    parser.add_argument("--server", type=str, default="http://10.96.189.13:30001",
                        help="CLIP API URL")
    args = parser.parse_args()

    os.environ["CLIP_API_URL"] = args.server

    # Load data
    if args.input:
        items = load_urls_from_file(args.input, args.url_field)
    else:
        items = load_urls_from_supabase()

    if args.limit > 0:
        items = items[:args.limit]

    # Output file
    if args.output:
        output_file = Path(args.output)
    else:
        output_file = OUTPUT_DIR / f"clip_{args.task}_results.jsonl"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Validate task args
    texts = args.texts
    labels = None
    if args.task == "score" and not texts:
        log.error("--texts required for score task")
        return
    if args.task == "classify":
        if not args.labels:
            log.error("--labels required for classify task")
            return
        labels = Path(args.labels).read_text().strip().split("\n")
        log.info("Classification labels: %s", labels)

    # Health check
    import requests
    try:
        r = requests.get(f"{get_clip_api()}/health", timeout=5)
        log.info("CLIP server: %s", r.json())
    except Exception as e:
        log.error("Cannot connect to CLIP server: %s", e)
        return

    # Run
    asyncio.run(run_pipeline(
        items=items,
        output_file=output_file,
        task=args.task,
        batch_size=args.batch_size,
        max_concurrent_batches=args.workers,
        texts=texts,
        labels=labels,
    ))


if __name__ == "__main__":
    main()
