"""
parser.py 
--------------
# HTML / JSON extraction layer

Rightmove uses Next.js, so the full property dataset is embedded in a
<script id="__NEXT_DATA__"> tag as JSON.  That is tried first because it
is both faster and more accurate than scraping the rendered HTML.

If the JSON model is absent, we fall back to BeautifulSoup HTML parsing.
"""

import json, logging, re
from datetime import datetime, timezone
from typing import Optional
from bs4 import BeautifulSoup, Tag

from settings import BASE_URL

logger = logging.getLogger(__name__)


# ── public interface ───────────────────────────────────────────────────────

class RightmoveParser:
    """
    Parses raw Rightmove search-page HTML into clean listing dicts.

    Typical flow
    ------------
    >>> parser = RightmoveParser()
    >>> listings, total = parser.parse_page(html)
    """

    def parse_page(self, html: str) -> tuple[list[dict], Optional[int]]:
        """
        Parse one search-results page.

        Returns
        -------
        listings : list[dict]
            One dict per property, with keys from ``LISTING_FIELDS``.
        total : int | None
            Total results Rightmove reports for the query (not just this page).
        """

        # Next.js __NEXT_DATA__ JSON blob
        listings, total = self._parse_next_data(html)
        if listings:
            return listings, total

        # Legacy window['jsonModel'] script variable
        listings, total = self._parse_json_model(html)
        if listings:
            return listings, total

        # BeautifulSoup HTML parsing
        logger.info("JSON extraction found nothing. Falling back to HTML parsing.")
        listings = self._parse_html_cards(html)
        return listings, None

    @staticmethod
    def quick_count(html: str) -> tuple[int, Optional[int]]:
        """
        Lightweight helper used by the scraper to count listings on a page
        without building the full dict list.

        Returns (listing_count_on_page, total_available).
        """

        parser = RightmoveParser()
        listings, total = parser.parse_page(html)

        return len(listings), total

    # Next.js extraction
    def _parse_next_data(self, html: str) -> tuple[list[dict], Optional[int]]:
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if not tag or not tag.string:
            return [], None

        try:
            data = json.loads(tag.string)
        except json.JSONDecodeError as exc:
            logger.debug("__NEXT_DATA__ JSON parse error: %s", exc)
            return [], None

        # Navigate the nested structure; paths vary between page versions
        props_list: Optional[list] = None
        pagination: Optional[dict] = None

        # Common path: props → pageProps → searchPageProps
        search_props = (
            data.get("props", {})
            .get("pageProps", {})
            .get("searchPageProps", {})
        )
        if search_props:
            props_list = search_props.get("properties") or search_props.get("results")
            pagination = search_props.get("pagination", {})

        # Alternate path some A/B variants use
        if not props_list:
            props_list = self._deep_find(data, "properties")
            pagination = self._deep_find(data, "pagination") or {}

        if not props_list:
            return [], None

        total = None
        if pagination:
            total = pagination.get("total") or pagination.get("totalCount")

        listings = [self._normalise_json_property(p) for p in props_list]
        listings = [l for l in listings if l is not None]

        logger.info(
            "Extracted %d listings from __NEXT_DATA__ (total reported: %s)",
            len(listings),
            total,
        )
        return listings, total

    # Legacy jsonModel extraction
    def _parse_json_model(self, html: str) -> tuple[list[dict], Optional[int]]:
        patterns = [
            r"window\[.jsonModel.\]\s*=\s*(\{[\s\S]*?\});\s*(?:window|</script>)",
            r"window\.jsonModel\s*=\s*(\{[\s\S]*?\});\s*(?:window|</script>)",
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if not match:
                continue
            try:
                data = json.loads(match.group(1))
                props_list = data.get("properties", [])
                total = data.get("pagination", {}).get("total")

                listings = [self._normalise_json_property(p) for p in props_list]
                listings = [l for l in listings if l is not None]

                if listings:
                    logger.info(
                        "Extracted %d listings from jsonModel (total: %s)",
                        len(listings),
                        total,
                    )
                    return listings, total
            except json.JSONDecodeError:
                continue
        return [], None

    # HTML extraction
    def _parse_html_cards(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")

        # Try several selector strategies in order of specificity
        cards: list[Tag] = []
        for selector in (
            '[data-test="propertyCard"]',
            "article.propertyCard",
            ".l-searchResult",
            "[class*='propertyCard-']",
        ):
            cards = soup.select(selector)
            if cards:
                logger.info(
                    "HTML fallback: found %d cards via selector '%s'",
                    len(cards),
                    selector,
                )
                break

        if not cards:
            logger.warning("HTML fallback: no property cards found in page.")
            return []

        listings = [self._parse_html_card(c) for c in cards]
        return [l for l in listings if l is not None]

    def _parse_html_card(self, card: Tag) -> Optional[dict]:
        try:
            # Price
            price_el = (
                card.select_one("[data-test='property-price']")
                or card.select_one(".propertyCard-priceValue")
                or card.select_one("[class*='price']")
            )
            price_raw = price_el.get_text() if price_el else None
            price = _clean_price(price_raw)

            # Address
            addr_el = (
                card.select_one("[data-test='address-label']")
                or card.select_one(".propertyCard-address")
                or card.select_one("address")
            )
            address = _clean_text(addr_el.get_text() if addr_el else None)

            # Bedrooms
            bed_el = (
                card.select_one("[data-test='property-bedroom']")
                or card.select_one(".property-information li:first-child")
            )
            bedrooms = _extract_int(bed_el.get_text() if bed_el else None)

            # Bathrooms
            bath_el = card.select_one("[data-test='property-bathroom']")
            bathrooms = _extract_int(bath_el.get_text() if bath_el else None)

            # Property type
            type_el = (
                card.select_one("[data-test='property-type']")
                or card.select_one(".propertyCard-type")
            )
            property_type = _clean_text(type_el.get_text() if type_el else None)

            # Listing URL
            link_el = card.select_one("a[href*='/properties/']") or card.select_one(
                "a.propertyCard-link"
            )
            listing_url: Optional[str] = None
            if link_el:
                href = link_el.get("href", "")
                listing_url = href if href.startswith("http") else f"{BASE_URL}{href}"

            # Title (synthesised from bedrooms + type)
            title = _build_title(bedrooms, property_type)

            return _make_listing(
                title=title,
                price=price,
                address=address,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                property_type=property_type,
                listing_url=listing_url,
            )
        except Exception as exc:
            logger.debug("Error parsing HTML card: %s", exc)
            return None

    # JSON property normalisation
    def _normalise_json_property(self, prop: dict) -> Optional[dict]:
        """
        Convert a raw property dict from the JSON model into a clean listing.
        Handles both the newer Next.js shape and the older jsonModel shape.
        """

        try:
            prop_id = prop.get("id") or prop.get("propertyId")

            # Price may be a nested dict or a plain value
            price: Optional[str] = None
            price_info = prop.get("price", {})

            if isinstance(price_info, dict):
                amount = price_info.get("amount") or price_info.get("displayPrices", [{}])[0].get("displayPrice")
                
                if amount is not None:
                    # Strip any currency formatting if it arrived as a string
                    price = _clean_price(str(amount)) if isinstance(amount, str) else str(int(amount))
            elif price_info:
                price = _clean_price(str(price_info))

            # Address
            address = _clean_text(
                prop.get("displayAddress")
                or prop.get("address")
            )

            # Bedrooms 
            bedrooms = _to_int(prop.get("bedrooms"))
            bathrooms = _to_int(prop.get("bathrooms"))

            # Property type
            property_type = _clean_text(
                prop.get("propertySubType")
                or prop.get("propertyTypeFullDescription")
                or prop.get("propertyType")
            )

            # Listing URL
            listing_url: Optional[str] = None
            if prop_id:
                listing_url = f"{BASE_URL}/properties/{prop_id}"

            # Title
            title = _build_title(bedrooms, property_type)

            return _make_listing(
                title=title,
                price=price,
                address=address,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                property_type=property_type,
                listing_url=listing_url,
            )
        except Exception as exc:
            logger.debug("Error normalising JSON property: %s", exc)
            return None

    
    @staticmethod
    def _deep_find(data: dict | list, key: str):
        """
        Recursively search a nested structure for *key*.
        """

        if isinstance(data, dict):
            if key in data:
                return data[key]
            
            for v in data.values():
                result = RightmoveParser._deep_find(v, key)
                if result is not None:
                    return result
                    
        elif isinstance(data, list):
            for item in data:
                result = RightmoveParser._deep_find(item, key)
                if result is not None:
                    return result
        return None


def _make_listing(
    *,
    title: Optional[str],
    price: Optional[str],
    address: Optional[str],
    bedrooms: Optional[int],
    bathrooms: Optional[int],
    property_type: Optional[str],
    listing_url: Optional[str],
) -> dict:
    """
    Return a listing dict with every expected field present (None if missing).
    """

    return {
        "title": title,
        "price": price,
        "address": address,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "property_type": property_type,
        "listing_url": listing_url,
        "date_scraped": datetime.now(timezone.utc).isoformat(),
    }


def _clean_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = " ".join(text.split()).strip()
    return cleaned or None


def _clean_price(text: Optional[str]) -> Optional[str]:
    """
    Strip currency symbols / commas and return the bare numeric string.
    """

    if not text:
        return None
    
    # Remove £ $ € and thousands separators
    stripped = re.sub(r"[£$€,\s]", "", text)

    # Drop frequency suffixes (pcm, pw, per month …)
    stripped = re.sub(r"(?i)(pcm|pw|per\s*month|per\s*week|guide\s*price|offers?\s*over)", "", stripped)
    
    # Extract the first run of digits
    match = re.search(r"\d+", stripped)

    return match.group(0) if match else None


def _extract_int(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else None


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _build_title(bedrooms: Optional[int], property_type: Optional[str]) -> str:
    parts = []
    if bedrooms is not None:
        parts.append(f"{bedrooms} bedroom")
    if property_type:
        parts.append(property_type)
    return " ".join(parts) if parts else "Property"
