#!/usr/bin/env python3
"""
Master optometry/eyecare scraper runner — mirrors the accounting TAM run_all.py.

Usage:
    python run_all.py                    # Run all scrapers + normalize
    python run_all.py --only vpg
    python run_all.py --normalize        # Re-normalize existing CSVs (no scraping)

Sources (all public, no-login, polite-fetch — same discipline as dental/vet/acct):
    vpg               Visionary Practice Group   ~7 active  (rev + SDE on card; ~90 SOLD dropped)
    practiceconcepts  Practice Concepts          ~3 active  (revenue + state + ref; Sold dropped)
    omni              Omni Optometry Group        ~4 across WA/CA/OR state pages

BLOCKED (never scraped — same blocklist as dental/vet/acct): BizBuySell, BizQuest,
LoopNet, DealStream, BusinessBroker.net, PracticeOrbit, Provide/TUSK, OptiRova.

REJECTED (verified live but NOT scrapeable via plain fetch, or off-doctrine —
documented in broker_codes.json rejected_sources): Optometry Practice Sales
(Duda JS blocks), The Williams Way (FSBO-tagged → FSBO doctrine), Cleinman
(consulting/Canada), state AOA classifieds (too thin after nav noise).

HONEST NOTE: optometry is a THIN direct-broker vertical (~14-17 active listings
network-wide after dropping SOLD/FSBO). See NETWORK-STATUS. This rig captures the
real, honest set and refreshes it daily; it does not pad counts with sold cards.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_all")

# (display_name, module_name)
SCRAPERS = [
    ("Visionary Practice Group", "vpg"),
    ("Practice Concepts", "practiceconcepts"),
    ("Omni Optometry Practice Group", "omni"),
]


def run_scraper(name, module_name):
    logger.info("=" * 60)
    logger.info("STARTING: %s", name)
    logger.info("=" * 60)
    try:
        mod = importlib.import_module(module_name)
        results = mod.run()
        count = len(results) if results else 0
        logger.info("%s: %d listings", name, count)
        return count
    except Exception as e:
        logger.error("%s failed: %s", name, e)
        return 0


def main():
    parser = argparse.ArgumentParser(description="Run optometry listing scrapers")
    parser.add_argument("--only", type=str, help="Run one scraper by module name")
    parser.add_argument("--normalize", action="store_true", help="Only normalize existing CSVs")
    args = parser.parse_args()

    start = time.time()
    results = {}

    if not args.normalize:
        if args.only:
            matched = False
            for name, module_name in SCRAPERS:
                if module_name == args.only:
                    results[name] = run_scraper(name, module_name)
                    matched = True
                    break
            if not matched:
                logger.error("Unknown scraper: %s", args.only)
                logger.info("Available: %s", ", ".join(m for _, m in SCRAPERS))
                return 1
        else:
            for name, module_name in SCRAPERS:
                results[name] = run_scraper(name, module_name)

    logger.info("=" * 60)
    logger.info("STARTING: Normalizer")
    logger.info("=" * 60)
    try:
        import normalizer
        merged = normalizer.run()
        results["normalized"] = len(merged) if merged else 0
    except Exception as e:
        logger.error("Normalizer failed: %s", e)
        results["normalized"] = 0

    elapsed = time.time() - start
    logger.info("=" * 60)
    logger.info("OPTOMETRY SCRAPER RUN COMPLETE — %.1fs", elapsed)
    logger.info("=" * 60)
    for source, count in results.items():
        logger.info("  %-34s %d", source, count)

    total = results.get("normalized", 0)
    print("\nDone. {} total optometry listings in listings.json ({:.1f}s)".format(total, elapsed))
    return 0 if total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
