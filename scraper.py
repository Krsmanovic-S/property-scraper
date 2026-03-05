"""
scraper.py
--------------
# HTTP fetching layer

Tries requests first for speed, but falls back to Playwright when the response.
"""

import logging, random, time, requests
from typing import Optional
from urllib.parse import urlencode

from settings import BASE_URL, SEARCH_PATH, LOCATION_IDS, HEADERS, PAGE_SIZE

logger = logging.getLogger(__name__)


# ── scraper class ──────────────────────────────────────────────────────────

class RightmoveScraper:
    """
    Fetches Rightmove search-results pages and returns raw HTML.

    Usage
    -----
    >>> scraper = RightmoveScraper()
    >>> pages = scraper.scrape_pages("london", target_count=100)
    >>> # pages is a list of (url, html) tuples
    """

    def __init__(
        self,
        min_delay: float = 2.0,
        max_delay: float = 3.0,
        force_playwright: bool = False,
    ) -> None:
        
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.force_playwright = force_playwright

        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    # Public Interface
    def build_search_url(
        self, location: str = "london", 
        index: int = 0
    ) -> str:
        """
        Return the Rightmove search URL for *location* at page-offset *index*.
        """

        location_id = LOCATION_IDS.get(location.lower())
        if location_id is None:
            logger.warning(
                "Unknown location '%s'. Defaulting to London. "
                "Add its REGION^ id to LOCATION_IDS in settings.py.",
                location,
            )

            location_id = LOCATION_IDS["london"]

        params = {
            "searchType": "SALE",
            "locationIdentifier": location_id,
            "numberOfPropertiesPerPage": str(PAGE_SIZE),
            "index": str(index),
            "includeSSTC": "false",
        }
        return f"{BASE_URL}{SEARCH_PATH}?{urlencode(params)}"

    def scrape_pages(
        self,
        location: str = "london",
        target_count: int = 100,
    ) -> list[tuple[str, str]]:
        """
        Paginate through search results until *target_count* listings have been
        seen (or there are no more pages).

        Returns a list of ``(url, html)`` tuples — one per fetched page.
        """

        pages: list[tuple[str, str]] = []
        seen = 0
        index = 0

        logger.info(
            "Starting scrape — location=%s  target=%d",
            location,
            target_count,
        )

        while seen < target_count:
            url = self.build_search_url(location, index)
            logger.info("Fetching page index=%d  url=%s", index, url)

            html = self.fetch_page(url)
            if not html:
                logger.error("Failed to fetch page at index %d — stopping.", index)
                break

            pages.append((url, html))

            # Peek at how many results this page contains so we know when to stop
            from parser import RightmoveParser

            _listings, total_available = RightmoveParser.quick_count(html)
            page_count = _listings

            if page_count == 0:
                logger.warning("No listings detected on page at index %d; stopping.", index)
                break

            seen += page_count
            logger.info(
                "Page %d: found %d listings  (running total: %d / %s)",
                index // PAGE_SIZE + 1,
                page_count,
                seen,
                str(total_available) if total_available else "?",
            )

            # Stop if Rightmove says there are no more results
            if total_available is not None and (index + PAGE_SIZE) >= total_available:
                logger.info("Reached the last page of results.")
                break

            if seen >= target_count:
                break

            index += PAGE_SIZE
            self._polite_delay()

        logger.info("Fetched %d page(s) covering ~%d listings.", len(pages), seen)
        return pages

    def fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch *url* and return HTML, or ``None`` on failure.

        Tries requests first; falls back to Playwright when the response
        looks like a bot-detection page or is missing expected content.
        """

        if self.force_playwright:
            return self._playwright_fetch(url)

        html = self._requests_fetch(url)

        # A real Rightmove page will contain one of these markers
        if html and self._looks_valid(html):
            return html

        if html:
            logger.info(
                "Response from requests looks like a bot-block — trying Playwright."
            )
        else:
            logger.info("requests returned nothing — trying Playwright.")

        return self._playwright_fetch(url)

    def _requests_fetch(self, url: str) -> Optional[str]:
        try:
            resp = self._session.get(url, timeout=30)

            resp.raise_for_status()
            return resp.text
        
        except requests.RequestException as exc:
            logger.warning("requests.get failed: %s", exc)
            return None

    def _playwright_fetch(self, url: str) -> Optional[str]:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.set_extra_http_headers(HEADERS)
                    page.goto(url, wait_until="networkidle", timeout=45_000)

                    # Give JS-rendered cards a moment to appear
                    try:
                        page.wait_for_selector(
                            '[data-test="propertyCard"], .l-searchResult',
                            timeout=10_000,
                        )
                    except Exception:
                        pass

                    return page.content()
                finally:
                    browser.close()

        except ImportError:
            logger.error("Playwright is not installed. ")
            return None
        except Exception as exc:
            logger.warning("Playwright fetch failed: %s", exc)
            return None

    @staticmethod
    def _looks_valid(html: str) -> bool:
        """
        Return True if *html* appears to be a real Rightmove search page.
        """

        markers = (
            "__NEXT_DATA__",
            "jsonModel",
            "propertyCard",
            "property-for-sale",
        )
        return any(m in html for m in markers)

    def _polite_delay(self) -> None:
        delay = random.uniform(self.min_delay, self.max_delay)
        logger.debug("Polite delay: %.1fs", delay)
        time.sleep(delay)
