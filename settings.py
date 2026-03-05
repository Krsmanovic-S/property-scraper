"""
settings.py — Central configuration for the Rightmove scraper.

All shared constants live here so every module imports from a single
source of truth. To add a new location, add its REGION^ id to
LOCATION_IDS (get the value from Rightmove's search URL after
selecting a city in the browser).
"""

# ── URLs ───────────────────────────────────────────────────────────────────

BASE_URL = "https://www.rightmove.co.uk"
SEARCH_PATH = "/property-for-sale/find.html"

# ── HTTP ───────────────────────────────────────────────────────────────────

HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# ── Pagination ─────────────────────────────────────────────────────────────

PAGE_SIZE = 24  # Rightmove returns 24 results per page

# ── Locations ──────────────────────────────────────────────────────────────

# REGION^ ids come from the locationIdentifier query param in Rightmove URLs.
LOCATION_IDS: dict[str, str] = {
    "london": "REGION^87490",
    "manchester": "REGION^904",
    "birmingham": "REGION^162",
    "leeds": "REGION^787",
    "edinburgh": "REGION^475",
    "bristol": "REGION^219",
    "liverpool": "REGION^861",
    "sheffield": "REGION^1259",
    "glasgow": "REGION^550",
    "cardiff": "REGION^270",
}

# ── Output ─────────────────────────────────────────────────────────────────

DEFAULT_OUTPUT_DIR = "output"

# Canonical field order used for CSV columns and the SQLite schema.
LISTING_FIELDS: tuple[str, ...] = (
    "title",
    "price",
    "address",
    "bedrooms",
    "bathrooms",
    "property_type",
    "listing_url",
    "date_scraped",
)
