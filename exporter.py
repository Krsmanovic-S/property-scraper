"""
exporter.py 
--------------
# Save scraped listings to CSV, JSON, and SQLite

All three formats are written every run, making the data immediately usable
for spreadsheets (CSV), APIs (JSON), and direct SQL queries (SQLite).
"""

import csv, json, logging, sqlite3
from pathlib import Path
from typing import Optional

from settings import LISTING_FIELDS, DEFAULT_OUTPUT_DIR

logger = logging.getLogger(__name__)


class Exporter:
    """
    Writes a list of listing dicts to three output files.

    Parameters
    ----------
    output_dir : str | Path
        Directory where output files are written.  Created if absent.

    Example
    -------
    >>> exporter = Exporter("output")
    >>> paths = exporter.export_all(listings)
    >>> print(paths["csv"])
    """

    def __init__(self, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # Public API
    def export_all(
        self,
        listings: list[dict],
        base_name: str = "listings",
    ) -> dict[str, Path]:
        """
        Export *listings* to all three formats.

        Returns a ``{format: path}`` dict so callers can report locations.
        """
        paths: dict[str, Path] = {}

        paths["csv"] = self.to_csv(listings, self.output_dir / f"{base_name}.csv")
        paths["json"] = self.to_json(listings, self.output_dir / f"{base_name}.json")
        paths["db"] = self.to_sqlite(listings, self.output_dir / f"{base_name}.db")

        return paths

    # CSV Data
    def to_csv(
        self, 
        listings: list[dict], 
        filepath: str | Path
    ) -> Path:
        
        filepath = Path(filepath)
        with filepath.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=list(LISTING_FIELDS),
                extrasaction="ignore",
                quoting=csv.QUOTE_MINIMAL,
            )
            writer.writeheader()
            writer.writerows(listings)

        logger.info("CSV  → %s  (%d rows)", filepath, len(listings))
        return filepath

    # JSON Data
    def to_json(
        self, 
        listings: list[dict], 
        filepath: str | Path
    ) -> Path:
        
        filepath = Path(filepath)
        payload = {
            "count": len(listings),
            "listings": listings,
        }

        with filepath.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)

        logger.info("JSON → %s  (%d entries)", filepath, len(listings))
        return filepath

    # Data inside SQLite Database
    def to_sqlite(
        self, 
        listings: list[dict], 
        filepath: str | Path
    ) -> Path:
        
        filepath = Path(filepath)
        connection = sqlite3.connect(filepath)

        try:
            self._ensure_schema(connection)
            inserted, skipped = self._insert_listings(connection, listings)
            connection.commit()
        finally:
            connection.close()

        logger.info(
            "DB   → %s  (%d inserted, %d skipped as duplicates)",
            filepath,
            inserted,
            skipped,
        )
        return filepath

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        # SQL schema with appropriate types and constraints
        connection.execute("""
            CREATE TABLE IF NOT EXISTS properties (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                title         TEXT,
                price         INTEGER,
                address       TEXT,
                bedrooms      INTEGER,
                bathrooms     INTEGER,
                property_type TEXT,
                listing_url   TEXT UNIQUE,
                date_scraped  TEXT
            )
        """)

        # Index the columns most likely used in WHERE / ORDER BY clauses.
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_price ON properties (price)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_bedrooms ON properties (bedrooms)"
        )

    @staticmethod
    def _insert_listings(
        connection: sqlite3.Connection,
        listings: list[dict],
    ) -> tuple[int, int]:
        
        inserted = skipped = 0
        for listing in listings:
            price_int = _to_int_or_none(listing.get("price"))

            try:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO properties
                        (title, price, address, bedrooms, bathrooms,
                         property_type, listing_url, date_scraped)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        listing.get("title"),
                        price_int,
                        listing.get("address"),
                        listing.get("bedrooms"),
                        listing.get("bathrooms"),
                        listing.get("property_type"),
                        listing.get("listing_url"),
                        listing.get("date_scraped"),
                    ),
                )

                if connection.execute("SELECT changes()").fetchone()[0]:
                    inserted += 1
                else:
                    skipped += 1

            except sqlite3.Error as exc:
                logger.warning("DB insert error (skipping row): %s", exc)
                skipped += 1

        return inserted, skipped


# Module level helpers

def _to_int_or_none(value) -> Optional[int]:
    """
    Coerce *value* to int, returning None on failure (for price storage).
    """

    if value is None:
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None
