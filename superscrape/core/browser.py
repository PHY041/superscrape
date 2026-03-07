"""Camoufox browser pool — the anti-detection engine behind SuperScrape.

Supports:
- Automatic headless mode selection (virtual Xvfb on Linux for WebGL)
- Residential proxy via PROXY_URL env var
- Custom Camoufox binary via CAMOUFOX_PATH env var
"""

from __future__ import annotations

import atexit
import logging
import os
import platform
from contextlib import contextmanager
from typing import Generator

from camoufox.sync_api import Camoufox
from playwright.sync_api import BrowserContext, Page

logger = logging.getLogger(__name__)

# On Linux (Docker), use 'virtual' headless for full WebGL/GLX support.
# Native headless=True lacks WebGL and gets detected by Amazon.
_DEFAULT_HEADLESS: bool | str = "virtual" if platform.system() == "Linux" else True


def _camoufox_kwargs() -> dict:
    """Build shared kwargs for all Camoufox launches from env vars."""
    kwargs: dict = {}

    # Proxy support: set PROXY_URL to a residential proxy endpoint
    # e.g. "http://user:pass@gate.smartproxy.com:7000"
    proxy_url = os.environ.get("PROXY_URL")
    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}
        # Auto-detect geolocation through the proxy to avoid fingerprint leak
        kwargs["geoip"] = True
        logger.info("Camoufox using proxy: %s", proxy_url.split("@")[-1])

    # Custom binary: set CAMOUFOX_PATH to use a specific Camoufox build
    # e.g. "/opt/camoufox/camoufox-bin" for a manually compiled FF146 binary
    custom_path = os.environ.get("CAMOUFOX_PATH")
    if custom_path:
        kwargs["executable_path"] = custom_path
        logger.info("Camoufox using custom binary: %s", custom_path)

    return kwargs


class BrowserPool:
    """Manages a pool of Camoufox browser instances."""

    _instance: BrowserPool | None = None
    _context: BrowserContext | None = None
    _camoufox: object | None = None

    def __init__(self, headless: bool | str = _DEFAULT_HEADLESS):
        self.headless = headless
        self._cm = None

    @classmethod
    def get(cls, headless: bool | str = _DEFAULT_HEADLESS) -> BrowserPool:
        if cls._instance is None:
            cls._instance = cls(headless=headless)
        return cls._instance

    def _ensure_browser(self) -> BrowserContext:
        if self._context is None:
            self._cm = Camoufox(headless=self.headless, **_camoufox_kwargs())
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
def browser_page(headless: bool | str = _DEFAULT_HEADLESS) -> Generator[Page, None, None]:
    """Context manager that yields a fresh Camoufox page and closes it after."""
    pool = BrowserPool.get(headless=headless)
    page = pool.new_page()
    try:
        yield page
    finally:
        page.close()


@contextmanager
def fresh_browser(headless: bool | str = _DEFAULT_HEADLESS) -> Generator[Page, None, None]:
    """One-shot browser — opens and closes a full Camoufox instance."""
    with Camoufox(headless=headless, **_camoufox_kwargs()) as browser:
        page = browser.new_page()
        try:
            yield page
        finally:
            page.close()
