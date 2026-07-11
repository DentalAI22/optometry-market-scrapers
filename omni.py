"""
Omni Optometry Practice Group — optometry practice listings scraper.

Omni (omnipg-opto.com) is a Weebly site that splits inventory across per-state
pages (washington-listings.html, california-listings.html, oregon-listings.html,
…). Listings are prose blocks, each anchored by an "Omni Practice ID: WAO116"
marker. The pages are static server-rendered HTML (easy fetch) but lightly
structured, so we segment on the Practice-ID markers and pull what's present
(title heading, gross/net figures, state from the page + ID prefix).

Small supplemental source (single digits per state). Omni is the Pacific-NW /
CA specialist; it fills geography VPG + Practice Concepts don't always cover.

Source: https://omnipg-opto.com/<state>-listings.html
Output: output/omni_raw.csv
"""

from __future__ import annotations

import csv
import logging
import os
import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from utils import (get_session, polite_delay, parse_price, clean_text,
                   parse_location, infer_practice_type)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("omni")

BASE_URL = "https://omnipg-opto.com"
# Omni's live per-state pages (the states where Omni actually holds inventory).
STATE_PAGES = {
    "WA": "/washington-listings.html",
    "CA": "/california-listings.html",
    "OR": "/oregon-listings.html",
}
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "omni_raw.csv")

FIELDNAMES = [
    "source_id", "title", "city", "state", "asking_price", "annual_revenue",
    "practice_type", "description", "broker_name", "listing_url",
    "exam_chairs", "listing_code",
]

ID_RE = re.compile(r"Omni Practice ID:\s*([A-Z]{2,4}\d{2,5})", re.I)
GROSS_RE = re.compile(
    r"(?:gross(?:ing)?|revenues?|collections?)\s*(?:of|over|at|about)?\s*"
    r"\$?\s*([\d.,]+\s*(?:mil(?:lion)?|k|K|MM|M)?)", re.I)
NET_RE = re.compile(
    r"(?:adjusted\s+net|net\s+income|SDE|cash\s+flow)\s*(?:of|over|at|about)?\s*"
    r"\$?\s*([\d.,]+\s*(?:mil(?:lion)?|k|K|MM|M)?)", re.I)


def scrape_state(session, state: str, path: str) -> List[Dict]:
    url = BASE_URL + path
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            logger.warning("Omni %s page HTTP %s", state, resp.status_code)
            return []
    except Exception as e:
        logger.warning("Omni %s fetch failed: %s", state, e)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    # Weebly content lives in .wsite-content; flatten to text and segment on IDs.
    content = soup.select_one(".wsite-content") or soup.body or soup
    full = content.get_text("\n")
    full = re.sub(r"\n\s*\n+", "\n", full)

    # split into blocks at each "Omni Practice ID: XXX" marker; the heading that
    # precedes the ID is the practice title.
    ids = list(ID_RE.finditer(full))
    listings: List[Dict] = []
    for i, m in enumerate(ids):
        code = m.group(1).upper()
        start = ids[i - 1].end() if i > 0 else max(0, m.start() - 800)
        block = full[start:m.start() + 200]
        block = clean_text(block)

        # title: the last substantive line before the ID that mentions the state
        # or "practice"/"optometry"
        title = ""
        for line in reversed(re.split(r"(?<=[.!?])\s+|\n", full[start:m.start()])):
            line = clean_text(line)
            if len(line) > 12 and re.search(r"optometry|practice|partnership|optical|eye",
                                            line, re.I):
                title = line[:120]
                break
        if not title:
            title = "{} Optometry Practice".format(state)

        gross = None
        gm = GROSS_RE.search(block)
        if gm:
            v = parse_price(gm.group(1))
            if v and v >= 50_000:
                gross = v

        city, st = parse_location(title)
        if not st:
            st = state

        practice_type = infer_practice_type(title + " " + block)

        listings.append({
            "source_id": "omni-{}".format(code.lower()),
            "title": title,
            "city": city,
            "state": st,
            "asking_price": None,
            "annual_revenue": gross,
            "practice_type": practice_type,
            "description": block[:400],
            "broker_name": "Omni Optometry Practice Group",
            "listing_url": url,
            "exam_chairs": None,
            "listing_code": code,
        })
        logger.info("  %s %s — rev $%s — %s", state, code,
                    gross or "N/A", title[:44])
    return listings


def run() -> List[Dict]:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    session = get_session()
    all_listings, seen = [], set()
    for state, path in STATE_PAGES.items():
        logger.info("Fetching Omni %s: %s%s", state, BASE_URL, path)
        for l in scrape_state(session, state, path):
            if l["source_id"] not in seen:
                seen.add(l["source_id"])
                all_listings.append(l)
        polite_delay(1.5, 3.0)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_listings)
    logger.info("Wrote %d Omni listings to %s", len(all_listings), OUTPUT_FILE)
    return all_listings


if __name__ == "__main__":
    results = run()
    print("Done. {} listings saved to {}".format(len(results), OUTPUT_FILE))
