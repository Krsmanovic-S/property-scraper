# Rightmove Property Scraper

A polite, modular Python scraper for **Rightmove property-for-sale** listings.

Extracts title, price, address, bedrooms, bathrooms, property type, and listing URL, then saves results to **CSV**, **JSON**, and **SQLite** simultaneously.

---

## Project layout

```
rightmove-scrapper/
├── main.py          # CLI entry point
├── scraper.py       # HTTP fetching (requests → Playwright fallback)
├── parser.py        # Data extraction (JSON model + BeautifulSoup fallback)
├── exporter.py      # Output: CSV / JSON / SQLite
├── requirements.txt
└── README.md
```

---

## Installation

### 1. Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright browser (optional, only needed if requests is blocked)

```bash
playwright install chromium
```

---

## Usage

### Default run: 100 London listings

```bash
python main.py
```

Output files are written to the current directory:

| File            | Purpose                          |
| --------------- | -------------------------------- |
| `listings.csv`  | Spreadsheet / client delivery    |
| `listings.json` | API / developer use              |
| `listings.db`   | SQLite — query with any SQL tool |

---

### CLI options

| Flag               | Default  | Description                                                                                                                                          |
| ------------------ | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--location CITY`  | `london` | City to search. Known values: `london`, `manchester`, `birmingham`, `leeds`, `edinburgh`, `bristol`, `liverpool`, `sheffield`, `glasgow`, `cardiff`. |
| `--count N`        | `100`    | Number of listings to collect.                                                                                                                       |
| `--output DIR`     | `.`      | Directory for output files.                                                                                                                          |
| `--min-delay SECS` | `2.0`    | Minimum pause between page requests.                                                                                                                 |
| `--max-delay SECS` | `3.0`    | Maximum pause between page requests.                                                                                                                 |
| `--playwright`     | off      | Force Playwright for all requests (useful if `requests` is blocked).                                                                                 |
| `-v / --verbose`   | off      | Enable DEBUG-level logging.                                                                                                                          |

### Examples

```bash
# 200 Manchester listings saved to ./output/
python main.py --location manchester --count 200 --output ./output

# Force Playwright (headless Chromium) for all requests
python main.py --playwright

# Debug mode — see every extraction step
python main.py -v
```

---

## Querying the SQLite database

```bash
# Open with the sqlite3 CLI
sqlite3 listings.db

# Inside sqlite3:
SELECT bedrooms, COUNT(*), AVG(price) FROM properties GROUP BY bedrooms;
SELECT * FROM properties WHERE price < 500000 AND bedrooms >= 3 LIMIT 20;
.quit
```

Or use any SQL client to just open `listings.db`.

---

## How it works

### Scraping strategy

1. **`requests`** fetches each search-results page with a realistic browser `User-Agent`.

2. If the response looks like a bot-block page (missing expected markers), the scraper automatically retries with **Playwright** (headless Chromium), which fully executes JavaScript.

3. A **random 2–3 second delay** is observed between every page request to avoid hammering the server.

### Parsing strategy

1. **`__NEXT_DATA__` JSON** — Rightmove uses Next.js and embeds the full property dataset as JSON in a `<script id="__NEXT_DATA__">` tag. This is parsed directly, giving clean structured data.

2. **`jsonModel` variable** — legacy fallback for older page variants that embed data as `window['jsonModel']`.

3. **BeautifulSoup HTML** — final fallback; scrapes the visible property-card elements from the rendered HTML.

### Data cleaning

- Currency symbols, commas, and frequency suffixes (`pcm`, `pw`) are stripped from prices.
- All string fields are whitespace-normalised.
- Missing fields are stored as `null` / `None`; the scraper never crashes on absent data.
- Duplicate listings (same URL) are de-duplicated before export.

---

## robots.txt compliance

The scraper only accesses `/property-for-sale/find.html`, which is **not disallowed** by Rightmove's `robots.txt` for the generic `User-agent: *`. Paths explicitly disallowed (maps, contact forms, API endpoints, etc.) are never accessed.

---

## Extending the scraper

### Add a new location

Open `scraper.py` and add an entry to `LOCATION_IDS`:

```python
LOCATION_IDS: dict[str, str] = {
    ...
    "oxford": "REGION^1050",   # example — get the real ID from Rightmove's autocomplete
}
```

To find a location's REGION ID, open Rightmove in a browser, search for the city, and copy the `locationIdentifier` value from the URL.

### Add new output fields

1. Extract the field in `parser.py` → `_normalise_json_property` / `_parse_html_card`.
2. Add it to the `FIELDS` tuple in `exporter.py`.
3. Add the column to the `CREATE TABLE` statement in `exporter.py` → `_ensure_schema`.

---
