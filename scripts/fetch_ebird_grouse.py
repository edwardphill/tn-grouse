#!/usr/bin/env python3
"""
fetch_ebird_grouse.py

Pulls Ruffed Grouse observations from the eBird API for Tennessee over a
configurable date range, dedupes them, and writes ebird_grouse_tn.json
ready to drop into the TN grouse report.

Setup:
    1. Get a free eBird API key:  https://ebird.org/api/keygen
    2. Export it:                  export EBIRD_API_KEY="your-key-here"
    3. Run:                        python3 fetch_ebird_grouse.py

How it works:
    - Calls /v2/data/obs/US-TN/recent/rufgro for the last 30 days (one call,
      species-filtered).
    - Then iterates day-by-day through /v2/data/obs/US-TN/historic/{y}/{m}/{d}
      for older data, filtering to speciesCode='rufgro' client-side. (The
      historic endpoint returns all species; species-filtering isn't supported
      server-side for historic.)
    - Sleeps 0.5s between calls to stay polite to the API.

Runtime:
    1 year back  ≈   365 calls  ≈  ~6 minutes
    3 years back ≈  1100 calls  ≈  ~18 minutes

Output:
    ebird_grouse_tn.json — array of {lat, lng, loc, date, year, count}
"""

from __future__ import annotations  # PEP 604 unions on Python <3.10

import json
import os
import socket
import sys
import time
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ─────────────────────────────────────────────────────────────
# .env loader (stdlib only — avoids a python-dotenv dependency)
# ─────────────────────────────────────────────────────────────
def _load_dotenv(path: str) -> None:
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except FileNotFoundError:
        pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_load_dotenv(os.path.join(_HERE, "..", ".env"))  # project root
_load_dotenv(".env")                              # current working dir

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
API_KEY = os.environ.get("EBIRD_API_KEY", "")  # or hardcode: API_KEY = "abc123..."
REGION = "US-TN"
SPECIES = "rufgro"  # eBird species code for Ruffed Grouse

# Historic window. Two ways to set:
#   1) START_DATE / END_DATE env vars (YYYY-MM-DD) — precise control, used for
#      incremental backfills (e.g. pull 2006–2016 without re-fetching 2016+).
#   2) YEARS_BACK fallback — fetches the last N years ending 31 days ago.
YEARS_BACK = 10

# Rate-limit pacing — eBird is generous but be polite
SLEEP_BETWEEN_CALLS = 0.5  # seconds

# Whether to also pull the species-filtered recent-30-day endpoint (1 call).
# Disable when doing a historical backfill that ends before "today − 30".
FETCH_RECENT = os.environ.get("FETCH_RECENT", "1") != "0"

# Whether to merge new observations with whatever's already in OUTPUT_FILE
# (deduped). On by default so backfills append, not overwrite.
MERGE_EXISTING = os.environ.get("MERGE_EXISTING", "1") != "0"

OUTPUT_FILE = "../data/ebird_grouse_tn.json"

# ─────────────────────────────────────────────────────────────
# API helpers
# ─────────────────────────────────────────────────────────────
def ebird_get(path: str, params: dict | None = None, max_retries: int = 3) -> list | dict:
    """Hit the eBird API with retry-with-backoff. Returns [] on any error after retries."""
    if not API_KEY:
        sys.exit("ERROR: Set EBIRD_API_KEY environment variable or hardcode it in the script.")
    qs = f"?{urlencode(params)}" if params else ""
    url = f"https://api.ebird.org/v2{path}{qs}"
    req = Request(url, headers={"x-ebirdapitoken": API_KEY})
    for attempt in range(max_retries):
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            if e.code == 404:
                return []  # no observations that day
            print(f"  ! HTTP {e.code} for {url}", file=sys.stderr)
            return []
        except (URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
            wait = 2 ** attempt
            print(f"  ! network error (attempt {attempt+1}/{max_retries}): {e} — retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
        except Exception as e:
            print(f"  ! unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
            return []
    print(f"  ! gave up after {max_retries} retries on {url}", file=sys.stderr)
    return []

# ─────────────────────────────────────────────────────────────
# Fetchers
# ─────────────────────────────────────────────────────────────
def fetch_recent_30_days() -> list:
    """Last 30 days, species-filtered. Single call."""
    print("Fetching last 30 days (species-filtered endpoint)...")
    obs = ebird_get(f"/data/obs/{REGION}/recent/{SPECIES}", {"back": 30, "maxResults": 10000})
    print(f"  → {len(obs)} observations")
    return obs

def fetch_historic_window(start: date, end: date) -> list:
    """
    Iterate day-by-day from start to end (inclusive). The historic endpoint
    returns all species, so we filter client-side for rufgro. Slow but thorough.
    """
    if end < start:
        print(f"  (empty window: {start} → {end} — skipping)")
        return []

    all_obs = []
    cur = start
    total_days = (end - start).days + 1
    print(f"Fetching historic window: {start} → {end} ({total_days} days)")
    print(f"  Estimated runtime: ~{total_days * SLEEP_BETWEEN_CALLS / 60:.1f} minutes")

    days_done = 0
    while cur <= end:
        try:
            day_obs = ebird_get(
                f"/data/obs/{REGION}/historic/{cur.year}/{cur.month}/{cur.day}",
                {"cat": "species", "maxResults": 10000}
            )
            grouse_obs = [o for o in day_obs if o.get("speciesCode") == SPECIES]
            if grouse_obs:
                print(f"  {cur}: {len(grouse_obs)} grouse")
            all_obs.extend(grouse_obs)
        except Exception as e:
            print(f"  ! skipping {cur}: {type(e).__name__}: {e}", file=sys.stderr)

        days_done += 1
        if days_done % 50 == 0:
            print(f"  ... {days_done}/{total_days} days, {len(all_obs)} grouse so far", flush=True)

        cur += timedelta(days=1)
        time.sleep(SLEEP_BETWEEN_CALLS)

    print(f"  → {len(all_obs)} historic observations")
    return all_obs

# ─────────────────────────────────────────────────────────────
# Dedupe + shape
# ─────────────────────────────────────────────────────────────
def normalize(obs_list: list) -> list:
    """Reduce to the fields we need, dedupe by (locId, obsDt, howMany)."""
    seen = set()
    out = []
    for o in obs_list:
        key = (o.get("locId"), o.get("obsDt"), o.get("howMany"))
        if key in seen:
            continue
        seen.add(key)
        # year from obsDt like "2024-10-14 09:23"
        obs_dt = o.get("obsDt", "")
        year = int(obs_dt[:4]) if len(obs_dt) >= 4 and obs_dt[:4].isdigit() else None
        out.append({
            "lat": o.get("lat"),
            "lng": o.get("lng"),
            "loc": o.get("locName"),
            "date": obs_dt,
            "year": year,
            "count": o.get("howMany"),  # may be None for "X" (present, count unknown)
        })
    return out

# ─────────────────────────────────────────────────────────────
# Existing-data merge (for incremental backfills)
# ─────────────────────────────────────────────────────────────
def load_existing(path: str) -> list:
    try:
        with open(path) as f:
            return json.load(f).get("observations", [])
    except FileNotFoundError:
        return []

def merge_dedupe(existing: list, new: list) -> list:
    """Merge two normalized lists, dedupe by (date, lat, lng, count)."""
    seen = set()
    out = []
    for o in existing + new:
        key = (o.get("date"), o.get("lat"), o.get("lng"), o.get("count"))
        if key in seen:
            continue
        seen.add(key)
        out.append(o)
    return out

# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def resolve_window() -> tuple:
    """Return (start_date, end_date) for the historic fetch."""
    today = date.today()
    start_env = os.environ.get("START_DATE")
    end_env = os.environ.get("END_DATE")
    if start_env:
        start = date.fromisoformat(start_env)
    else:
        start = today - timedelta(days=365 * YEARS_BACK)
    if end_env:
        end = date.fromisoformat(end_env)
    else:
        end = today - timedelta(days=31)  # avoid overlap with recent-30-day
    return start, end

def main():
    print(f"eBird API fetch — Ruffed Grouse, {REGION}\n")
    if not API_KEY:
        print("ERROR: Set EBIRD_API_KEY environment variable, e.g.:")
        print('  export EBIRD_API_KEY="your-key-here"')
        sys.exit(1)

    start, end = resolve_window()
    print(f"Window: {start} → {end}   (FETCH_RECENT={FETCH_RECENT}, MERGE_EXISTING={MERGE_EXISTING})\n")

    all_observations = []
    if FETCH_RECENT:
        all_observations.extend(fetch_recent_30_days())
    all_observations.extend(fetch_historic_window(start, end))

    normalized = normalize(all_observations)

    if MERGE_EXISTING:
        existing = load_existing(OUTPUT_FILE)
        before = len(existing)
        normalized = merge_dedupe(existing, normalized)
        added = len(normalized) - before
        print(f"\nMerged with existing snapshot: {before} prior + {added} new = {len(normalized)} unique")

    normalized.sort(key=lambda o: o["date"], reverse=True)

    print(f"\nTotal unique observations: {len(normalized)}")
    if normalized:
        print(f"Date range: {normalized[-1]['date']} → {normalized[0]['date']}")
        years = sorted({o["year"] for o in normalized if o["year"]})
        print(f"Years with sightings: {years}")

    payload = {
        "source": "eBird API 2.0",
        "region": REGION,
        "species": SPECIES,
        "fetched_at": date.today().isoformat(),
        "observations": normalized,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n✓ Wrote {OUTPUT_FILE} ({len(normalized)} observations)")
    print(f"\nNext: drop the JSON into the report, or share {OUTPUT_FILE} back.")

if __name__ == "__main__":
    main()
