"""
Visionary Practice Group (VPG) — optometry practice listings scraper.

VPG (visionarypracticegroup.com) is the category leader for optometry-practice
transitions and by far our richest source. Its /listings/ page is a WordPress +
Elementor grid of <article> posts of CSS class 'type-listing'. Each post carries:
    - a status class: 'listings-item-sold' (DROP), 'listings-item-pending-offer'
      (keep, flag pending), or plain (active).
    - a detail URL: /listing/{slug}/  (the state is usually in the slug/title).
    - card text with 'Revenues over $750k' + 'discretionary net income $270k'
      right on the card — no detail fetch required for the load-bearing numbers.

⚠️ HONEST COUNT: VPG keeps ~90 SOLD listings on the page as social proof (same
pattern as accounting's APS 22-of-147). Only ~7 are ACTIVE. We drop every
'listings-item-sold' card → the honest active set. Do NOT count sold cards.

Source: https://visionarypracticegroup.com/listings/
Output: output/vpg_raw.csv
"""

from __future__ import annotations

import csv
import logging
import os
import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from utils import (get_session, parse_price, clean_text, parse_location,
                   infer_practice_type)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("vpg")

BASE_URL = "https://visionarypracticegroup.com"
LISTINGS_URL = "{}/listings/".format(BASE_URL)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "vpg_raw.csv")

FIELDNAMES = [
    "source_id", "title", "city", "state", "asking_price", "annual_revenue",
    "practice_type", "description", "broker_name", "listing_url",
    "exam_chairs", "listing_code",
]

REV_RE = re.compile(
    r"[Rr]evenues?\s+(?:over|of|at|about|approximately|around)?\s*"
    r"\$?\s*([\d.,]+\s*(?:MM|M|mil(?:lion)?|k|K)?)")
SDE_RE = re.compile(
    r"(?:discretionary\s+net\s+income|net\s+income|SDE|cash\s+flow)\s*"
    r"(?:over|of|at|about|approximately|around)?\s*\$?\s*([\d.,]+\s*(?:MM|M|k|K)?)",
    re.I)
GROSS_RE = re.compile(
    r"[Gg]ross(?:\s+revenues?)?\s+(?:over|of|at|about)?\s*\$?\s*"
    r"([\d.,]+\s*(?:MM|M|mil(?:lion)?|k|K)?)")


def code_from_url(url: str) -> str:
    """VPG detail slugs sometimes end in a numeric id, e.g.
    /listing/arizona-optometry-practice-for-sale-489479/ -> 489479."""
    m = re.search(r"-(\d{4,7})/?$", url)
    return m.group(1) if m else ""


def parse_card(art) -> Optional[Dict]:
    cls = " ".join(art.get("class", []))
    if "listings-item-sold" in cls:
        return None  # honest: drop SOLD social-proof cards

    is_pending = "listings-item-pending-offer" in cls

    # title from the heading
    h = art.find(["h1", "h2", "h3", "h4"])
    title = clean_text(h.get_text()) if h else ""
    if not title:
        return None

    # detail URL
    a = art.find("a", href=True)
    listing_url = ""
    for link in art.find_all("a", href=True):
        if "/listing/" in link["href"]:
            listing_url = link["href"].split("?")[0]
            break
    if listing_url and not listing_url.startswith("http"):
        listing_url = BASE_URL + listing_url

    card_text = clean_text(art.get_text(" "))

    annual_revenue = None
    for rx in (REV_RE, GROSS_RE):
        m = rx.search(card_text)
        if m:
            v = parse_price(m.group(1))
            if v and v >= 50_000:
                annual_revenue = v
                break

    asking_price = None  # VPG rarely publishes asking on the card (SDE-led pitch)

    # state/city from the title first (states are named in VPG titles)
    city, state = parse_location(title)
    if not state:
        _, state = parse_location(card_text)

    # a clean description: the card body sans the title, trimmed
    desc = card_text
    if title and desc.startswith(title):
        desc = desc[len(title):].strip()
    desc = desc[:600]

    practice_type = infer_practice_type(title + " " + desc)

    code = code_from_url(listing_url)
    source_id = "vpg-{}".format(code) if code else "vpg-{}".format(
        re.sub(r"[^a-z0-9]+", "-", listing_url.rstrip("/").split("/")[-1].lower())[:48])

    if is_pending:
        desc = "[Pending offer] " + desc

    return {
        "source_id": source_id,
        "title": title,
        "city": city,
        "state": state,
        "asking_price": asking_price,
        "annual_revenue": annual_revenue,
        "practice_type": practice_type,
        "description": desc,
        "broker_name": "Visionary Practice Group",
        "listing_url": listing_url or LISTINGS_URL,
        "exam_chairs": None,
        "listing_code": code,
    }


def run() -> List[Dict]:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    session = get_session()
    logger.info("Fetching VPG listings: %s", LISTINGS_URL)
    try:
        resp = session.get(LISTINGS_URL, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error("Failed to fetch VPG index: %s", e)
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    articles = soup.select("article.type-listing, article.elementor-post.listing")
    logger.info("Found %d VPG listing articles (active + sold)", len(articles))

    all_listings, seen = [], set()
    for art in articles:
        listing = parse_card(art)
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
    logger.info("Wrote %d ACTIVE VPG listings (dropped SOLD) to %s",
                len(all_listings), OUTPUT_FILE)
    return all_listings


if __name__ == "__main__":
    results = run()
    print("Done. {} listings saved to {}".format(len(results), OUTPUT_FILE))
