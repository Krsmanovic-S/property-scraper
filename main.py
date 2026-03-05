"""
Rightmove Scraper Usage examples:
--------------
# Scrape 100 London listings (default):
    python main.py

# Scrape 200 Manchester listings, save to ./output/:
    python main.py --location manchester --count 200 --output ./output

# Use Playwright for all requests (if requests is being blocked):
    python main.py --playwright

# Verbose debug logging:
    python main.py -v
"""

import argparse, logging, sys
from pathlib import Path

from scraper import RightmoveScraper
from settings import LOCATION_IDS, DEFAULT_OUTPUT_DIR
from parser import RightmoveParser
from exporter import Exporter


# Logging setup
def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s  %(levelname)-8s  %(name)s: %(message)s"
    datefmt = "%H:%M:%S"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    # Quiet noisy third-party loggers unless we're in verbose mode.
    if not verbose:
        for lib in ("urllib3", "playwright", "asyncio"):
            logging.getLogger(lib).setLevel(logging.WARNING)


# CLI
def _build_parser() -> argparse.ArgumentParser:
    known_locations = ", ".join(sorted(LOCATION_IDS))

    ap = argparse.ArgumentParser(
        prog="main.py",
        description="Rightmove property-for-sale scraper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Known locations: {known_locations}",
    )
    ap.add_argument(
        "--location",
        default="london",
        metavar="CITY",
        help="City to search (default: london).",
    )
    ap.add_argument(
        "--count",
        type=int,
        default=100,
        metavar="N",
        help="Target number of listings to collect (default: 100).",
    )
    ap.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_DIR,
        metavar="DIR",
        help=f"Directory for output files (default: {DEFAULT_OUTPUT_DIR}).",
    )
    ap.add_argument(
        "--min-delay",
        type=float,
        default=2.0,
        metavar="SECS",
        help="Minimum polite delay between requests (default: 2.0).",
    )
    ap.add_argument(
        "--max-delay",
        type=float,
        default=3.0,
        metavar="SECS",
        help="Maximum polite delay between requests (default: 3.0).",
    )
    ap.add_argument(
        "--playwright",
        action="store_true",
        help="Force Playwright for every request (slower but handles JS pages).",
    )
    ap.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return ap


# Main Program Logic
def main() -> None:
    args = _build_parser().parse_args()

    _setup_logging(args.verbose)
    log = logging.getLogger(__name__)

    _print_banner(log, args)

    # Fetching Pages
    scraper = RightmoveScraper(
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        force_playwright=args.playwright,
    )
    pages = scraper.scrape_pages(location=args.location, target_count=args.count)

    if not pages:
        log.error("No pages were fetched. Check your network connection or try --playwright.")
        sys.exit(1)

    # Parsing Pages
    log.info("Parsing %d page(s)…", len(pages))
    parser = RightmoveParser()
    all_listings: list[dict] = []
    seen_urls: set[str] = set()

    for url, html in pages:
        listings, _ = parser.parse_page(html)
        for listing in listings:
            uid = listing.get("listing_url") or listing.get("address") or ""

            # De-duplicate across pages
            if uid and uid in seen_urls:
                continue  
            seen_urls.add(uid)
            all_listings.append(listing)

    if not all_listings:
        log.error(
            "Parsing produced zero listings. "
            "Rightmove may have changed their page structure — "
            "run with -v for details, or try --playwright."
        )
        sys.exit(1)

    # Trim to requested count if we collected more
    all_listings = all_listings[: args.count]
    log.info("Collected %d unique listings after de-duplication.", len(all_listings))

    # Exporting the Data
    exporter = Exporter(output_dir=args.output)
    paths = exporter.export_all(all_listings)

    # Log Summary
    log.info("")
    log.info("=" * 60)
    log.info("  Scrape complete — %d listings saved to:", len(all_listings))
    for fmt, path in paths.items():
        log.info("    %-6s  %s", fmt.upper(), Path(path).resolve())
    log.info("=" * 60)


# CLI Print for visual feedback
def _print_banner(log: logging.Logger, args: argparse.Namespace) -> None:
    log.info("=" * 60)
    log.info("  Rightmove Property Scraper")
    log.info("  Location : %s", args.location)
    log.info("  Target   : %d listings", args.count)
    log.info("  Output   : %s", Path(args.output).resolve())
    log.info("  Delay    : %.1f – %.1f s", args.min_delay, args.max_delay)
    log.info("  Backend  : %s", "Playwright (forced)" if args.playwright else "requests → Playwright fallback")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
