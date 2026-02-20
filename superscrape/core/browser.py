"""Camoufox browser pool — the anti-detection engine behind SuperScrape."""

from __future__ import annotations

import atexit
from contextlib import contextmanager
from typing import Generator

from camoufox.sync_api import Camoufox
from playwright.sync_api import BrowserContext, Page


class BrowserPool:
    """Manages a pool of Camoufox browser instances."""

    _instance: BrowserPool | None = None
    _context: BrowserContext | None = None
    _camoufox: object | None = None

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._cm = None

    @classmethod
    def get(cls, headless: bool = True) -> BrowserPool:
        if cls._instance is None:
            cls._instance = cls(headless=headless)
        return cls._instance

    def _ensure_browser(self) -> BrowserContext:
        if self._context is None:
            self._cm = Camoufox(headless=self.headless)
            browser = self._cm.__enter__()
            self._context = browser
            atexit.register(self.close)
        return self._context

    def new_page(self) -> Page:
        ctx = self._ensure_browser()
        return ctx.new_page()

    def close(self) -> None:
        if self._cm is not None:
            try:
                self._cm.__exit__(None, None, None)
            except Exception:
                pass
            self._cm = None
            self._context = None
            BrowserPool._instance = None


@contextmanager
def browser_page(headless: bool = True) -> Generator[Page, None, None]:
    """Context manager that yields a fresh Camoufox page and closes it after."""
    pool = BrowserPool.get(headless=headless)
    page = pool.new_page()
    try:
        yield page
    finally:
        page.close()


@contextmanager
def fresh_browser(headless: bool = True) -> Generator[Page, None, None]:
    """One-shot browser — opens and closes a full Camoufox instance."""
    with Camoufox(headless=headless) as browser:
        page = browser.new_page()
        try:
            yield page
        finally:
            page.close()
