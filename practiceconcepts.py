"""
Practice Concepts — optometry practice listings scraper.

Practice Concepts (practiceconcepts.com) lists on a single server-rendered page:
    https://practiceconcepts.com/pages/practices-for-sale

Each listing is an <li class='element_rowNNNNN'> with a details <ul> exposing:
    REVENUE  -> "$1,000,000"      (captured)
    STATE    -> "California"      (captured; sometimes blank on the card)
    REFERENCE-> "CA-76747"        (broker code; leading 2 letters = state)
    status   -> "Active" | "Sold" (we keep only Active)
    a "More Info >>" link to /listings/{slug}

⚠️ HONEST COUNT: the page shows ~14 listings but only ~3 are Active (rest Sold,
kept as social proof). We keep only Active.

Source: https://practiceconcepts.com/pages/practices-for-sale
Output: output/practiceconcepts_raw.csv
"""

from __future__ import annotations

import csv
import logging
import os
import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from utils import (get_session, parse_price, clean_text, parse_location,
                   state_from_code, infer_practice_type, STATE_NAME_TO_ABBR)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("practiceconcepts")

BASE_URL = "https://practiceconcepts.com"
LISTINGS_URL = "{}/pages/practices-for-sale".format(BASE_URL)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "practiceconcepts_raw.csv")

FIELDNAMES = [
    "source_id", "title", "city", "state", "asking_price", "annual_revenue",
    "practice_type", "description", "broker_name", "listing_url",
    "exam_chairs", "listing_code",
]


def field_value(li_text: str, label: str) -> str:
    """Pull the value that follows a label in the flattened <li> text, e.g.
    'REVENUE $1,000,000 STATE California REFERENCE CA-76747 Active ...'."""
    # value runs until the next known label or end
    m = re.search(
        label + r"\s*(.*?)(?:\s*(?:REVENUE|STATE|REFERENCE|Active|Sold)\b|$)",
        li_text, re.S)
    return clean_text(m.group(1)) if m else ""


def parse_li(li) -> Optional[Dict]:
    text = clean_text(li.get_text(" "))

    status = ""
    m = re.search(r"\b(Active|Sold)\b", text)
    if m:
        status = m.group(1)
    if status == "Sold":
        return None  # honest: keep only Active

    revenue = parse_price(field_value(text, "REVENUE"))
    state_raw = field_value(text, "STATE")
    ref = field_value(text, "REFERENCE")

    # title = the practice link/anchor text (first non-"More Info" anchor)
    title = ""
    href = ""
    for a in li.find_all("a", href=True):
        t = clean_text(a.get_text())
        if "/listings/" in a["href"]:
            href = a["href"].split("?")[0]
            if t and "more info" not in t.lower():
                title = t
    if not title:
        # derive from the listing slug
        if href:
            title = href.rstrip("/").split("/")[-1].replace("-", " ").title()
    if not title:
        return None

    if href and not href.startswith("http"):
        href = BASE_URL + href

    # state: explicit STATE field -> abbr, else the REFERENCE code prefix, else title
    state = ""
    if state_raw:
        state = STATE_NAME_TO_ABBR.get(state_raw.strip().lower(), "")
        if not state and len(state_raw.strip()) == 2:
            state = state_raw.strip().upper()
    if not state:
        state = state_from_code(ref)
    city = ""
    if not state:
        city, state = parse_location(title)

    practice_type = infer_practice_type(title)

    source_id = "pc-{}".format(re.sub(r"[^a-z0-9]+", "-", ref.lower())) if ref \
        else "pc-{}".format(re.sub(r"[^a-z0-9]+", "-", href.rstrip("/").split("/")[-1].lower())[:48])

    return {
        "source_id": source_id,
        "title": title,
        "city": city,
        "state": state,
        "asking_price": None,           # Practice Concepts publishes REVENUE, not asking
        "annual_revenue": revenue,
        "practice_type": practice_type,
        "description": "",              # cards are metric-only; no prose on the index
        "broker_name": "Practice Concepts",
        "listing_url": href or LISTINGS_URL,
        "exam_chairs": None,
        "listing_code": ref,
    }


def run() -> List[Dict]:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    session = get_session()
    logger.info("Fetching Practice Concepts: %s", LISTINGS_URL)
    try:
        resp = session.get(LISTINGS_URL, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error("Failed to fetch Practice Concepts: %s", e)
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    # each listing row is <li class="element_row...">
    rows = soup.select("li[class*='element_row']")
    # keep only optometry rows (the page is optometry-only, but guard anyway)
    logger.info("Found %d Practice Concepts listing rows", len(rows))

    all_listings, seen = [], set()
    for li in rows:
        listing = parse_li(li)
        if listing and listing["source_id"] not in seen:
            seen.add(listing["source_id"])
            all_listings.append(listing)
            logger.info("  ACTIVE %s — %s — rev $%s — %s",
                        listing["source_id"], listing["state"] or "?",
                        listing.get("annual_revenue") or "N/A",
                        listing["title"][:44])

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_listings)
    logger.info("Wrote %d ACTIVE Practice Concepts listings to %s",
                len(all_listings), OUTPUT_FILE)
    return all_listings


if __name__ == "__main__":
    results = run()
    print("Done. {} listings saved to {}".format(len(results), OUTPUT_FILE))
