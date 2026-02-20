"""Base protocol for Scout platform scrapers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from superscrape.output.models import ScrapedItem


@runtime_checkable
class ScraperProtocol(Protocol):
    """Structural type for platform scrapers.

    Any class with a static `search_images` method matching this signature
    is automatically compatible -- no inheritance required.
    """

    @staticmethod
    def search_images(
        keyword: str,
        *,
        top_n: int = 50,
        headless: bool = True,
    ) -> list[ScrapedItem]: ...
