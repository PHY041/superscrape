"""Result caching for scraped data."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".superscrape" / "cache"
DEFAULT_TTL = 86400  # 24 hours


def cache_key(keyword: str, top_n: int, platform: str = "amazon") -> str:
    return hashlib.md5(f"{platform}:{keyword}:{top_n}".encode()).hexdigest()


def get_cached(keyword: str, top_n: int, platform: str = "amazon", ttl: int = DEFAULT_TTL) -> dict | None:
    key = cache_key(keyword, top_n, platform)
    path = CACHE_DIR / key / "data.json"
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < ttl:
            return json.loads(path.read_text())
    return None


def save_cache(keyword: str, top_n: int, data: dict, platform: str = "amazon") -> None:
    key = cache_key(keyword, top_n, platform)
    dir_path = CACHE_DIR / key
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "data.json").write_text(json.dumps(data, default=str))
