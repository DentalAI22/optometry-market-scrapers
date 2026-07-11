# optometry-market-scrapers

Public scraper rig for **The Optometry Market** network vertical. Aggregates
real, public-source optometry/eyecare-practice-for-sale listings from dedicated
optometry practice-sales brokers and publishes a single canonical `listings.json`
that the live sites consume.

**Sites fed by this repo (when activated):**
- https://theoptometrymarket.com (Vercel project `optometry`)
- https://theoptometrypracticemarket.com (Vercel project `optometrypractice`)

Everything in this repo is scraper code + public listing data. **No secrets, no
tokens, no seller PII.** Practice names are generically redacted (`Optometry
Practice`, `Full-Scope Optometry Practice`, …); broker contact strings (phones,
emails, license numbers) are scrubbed; the final dataset contains 0 emails /
0 phones.

## ⚠️ Honest inventory note

Optometry is a **THIN direct-broker vertical.** After dropping SOLD social-proof
cards and FSBO-tagged owner listings (per the network's FSBO doctrine), the real
active broker-repped US inventory is **~13 listings network-wide** across 3 clean
plain-fetch sources. This rig captures the honest set and refreshes it daily — it
does **not** pad the count with sold cards (the way the source sites do on their
own pages). See `../NETWORK-STATUS-2026-07-10.md` for the full source audit and
why optometry stays a staged shell (not a flagship launch) until the vertical
deepens.

## What it does

```
run_all.py  ->  per-source scrapers (vpg, practiceconcepts, omni)
             ->  output/*_raw.csv  ->  normalizer.py
             ->  listings.json  (canonical, TOM-XXXXX siteIds, deduped)
```

- `utils.py` — real UA + polite 1.5–3.5s delays + price/state helpers +
  `infer_practice_type()` + `scrub_pii()`.
- `broker_codes.json` — source registry, `site_prefix = TOM`; also documents the
  verified-but-rejected sources and why (Optometry Practice Sales = JS blocks;
  The Williams Way = FSBO; Cleinman = consulting/Canada; OptiRova = aggregator).
- `site_id_registry.json` — persistent TOM- id map. **Never renumber.** Never
  collides with dental TDPM-, veterinary TVM-, or accounting TAM-.
- `listings.json` — the canonical dataset (~13 active listings, 3 brokers:
  Visionary Practice Group, Practice Concepts, Omni Optometry Practice Group).
  Tracked on purpose; the daily Action regenerates and commits it back here.

### Sources (all public, no-login, polite-fetch)

| Source | Module | Active | Notes |
|---|---|---|---|
| **Visionary Practice Group** | `vpg` | ~7 | Category leader. WordPress/Elementor `type-listing` grid; revenue + SDE right on the card. ~90 SOLD cards on the page are dropped (honest active only). Richest source. |
| **Practice Concepts** | `practiceconcepts` | ~3–4 | Server-rendered `<li>` rows with REVENUE / STATE / REFERENCE / Active\|Sold labels. CA-heavy. Sold dropped. |
| **Omni Optometry Practice Group** | `omni` | ~2 | Weebly per-state pages (WA/CA/OR), prose blocks keyed by "Omni Practice ID". Pacific-NW / CA specialist. Broker contact PII scrubbed. |

## Auto-refresh pipeline (refresh -> live)

`.github/workflows/scrape-optometry.yml` runs **daily at 09:15 UTC** (staggered
off dental/vet 08:30 and accounting 09:00; plus manual `workflow_dispatch`). This
repo is **PUBLIC**, so GitHub Actions minutes are unlimited/free.

The Action is **self-contained — it only ever writes to THIS repo:**

1. checkout -> install deps -> `python run_all.py` (scrape + normalize).
2. **Sanity guard:** if `listings.json` collapses below 4 listings, the job
   **fails and refuses to commit**, preserving the last-good dataset. The live
   sites never get wiped by a bad scrape. (Floor is low because the vertical is
   thin — it only trips on a near-total collapse, letting real churn flow.)
3. commit `listings.json` + `output/*.csv` + `site_id_registry.json` back to this
   repo using the default `GITHUB_TOKEN` (`permissions: contents: write`). No PAT.

**Why no cross-repo push:** the two site repos are SEPARATE git repos. Each
**site pulls `listings.json` from this repo's public raw URL at build time**:

```
https://raw.githubusercontent.com/DentalAI22/optometry-market-scrapers/main/listings.json
```

So the refresh-to-live path is:

```
daily Action scrapes  ->  commits listings.json to THIS repo
       ->  a site rebuild (`vercel --prod`, or a site-side prebuild fetch step)
           pulls the fresh raw listings.json  ->  republishes.
```

## Re-run locally

```bash
pip install -r requirements.txt
python run_all.py                        # scrape all 3 sources + normalize
python run_all.py --only vpg             # one source
python run_all.py --normalize            # re-normalize existing CSVs (no network)
```

## Constraints honored

- Read-only against public broker pages only; real browser UA; 1.5–3.5s delays.
- Blocked aggregators (BizBuySell / BizQuest / LoopNet / DealStream / Provide /
  PracticeOrbit / OptiRova) are **never** scraped.
- **FSBO doctrine:** FSBO-tagged owner listings (The Williams Way marketplace)
  are excluded on principle — the network steers clear of FSBOs everywhere;
  seller-side intent routes to a broker-finder, not an owner listing.
- SOLD cards dropped (honest active counts). Deduped; practice names redacted;
  contact PII scrubbed; 0 emails/phones/license#s in the final dataset.
