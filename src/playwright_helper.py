"""Shared Playwright helpers for SPA scrapers (Liiga, SHL, Swiss NL).

Pattern: one browser per scraping session, per-URL HTML cache on disk. Each
fetcher names its own cache directory under data/raw/.cache/{league}/.

Cache-key strategy:
    The cache key is a sanitized version of the URL path + query. Repeated
    runs with the same URL hit the disk cache and never re-render. To force
    re-render, delete the cached HTML file.

Politeness:
    POLITE_SLEEP_S between renders. Adjust per-league if a site is sensitive.
"""

from __future__ import annotations

import hashlib
import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from playwright.sync_api import Browser, Page, sync_playwright

from src import config

LOG = logging.getLogger(__name__)

POLITE_SLEEP_S = 1.5
NAVIGATION_TIMEOUT_MS = 30_000
EXTRA_WAIT_MS = 2_000  # let post-load JS finish


def cache_dir(league: str) -> Path:
    """Return on-disk cache dir for a league's rendered HTML."""
    p = config.RAW_DIR / ".cache" / league
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_path(league: str, cache_key: str) -> Path:
    """Build a deterministic cache file path for a (league, key) pair."""
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in cache_key)
    if len(safe) > 100:
        h = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:10]
        safe = safe[:80] + "_" + h
    return cache_dir(league) / f"{safe}.html"


@contextmanager
def browser_context(headless: bool = True) -> Iterator[Browser]:
    """Single browser instance shared across one scraping session."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            yield browser
        finally:
            browser.close()


def render_url(
    browser: Browser,
    url: str,
    league: str,
    cache_key: str,
    *,
    wait_for_selector: str | None = None,
    extra_wait_ms: int = EXTRA_WAIT_MS,
) -> str:
    """Render one URL through Chromium, cache the rendered HTML, return it.

    Args:
        browser: shared Browser from browser_context().
        url: full URL.
        league: cache dir name (e.g. "liiga").
        cache_key: stable key (typically the URL path+query) used for filename.
        wait_for_selector: optional CSS selector to wait for before extracting.
        extra_wait_ms: ms to wait after page is "ready", for late-loading JS.

    Returns:
        Full rendered HTML as a string.

    Cache hit: returns immediately from disk, no browser touched.
    Cache miss: navigates, waits, caches to disk, returns.
    """
    cp = _cache_path(league, cache_key)
    if cp.exists() and cp.stat().st_size > 1_000:
        LOG.debug("cache hit %s", cp.name)
        return cp.read_text(encoding="utf-8")

    LOG.info("rendering %s", url)
    page: Page = browser.new_page()
    page.set_default_timeout(NAVIGATION_TIMEOUT_MS)
    try:
        page.goto(url, wait_until="networkidle")
        if wait_for_selector:
            page.wait_for_selector(wait_for_selector, timeout=NAVIGATION_TIMEOUT_MS)
        if extra_wait_ms:
            page.wait_for_timeout(extra_wait_ms)
        html = page.content()
    finally:
        page.close()

    cp.write_text(html, encoding="utf-8")
    time.sleep(POLITE_SLEEP_S)
    return html
