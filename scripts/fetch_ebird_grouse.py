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

import json
import os
import sys
import time
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
API_KEY = os.environ.get("EBIRD_API_KEY", "")  # or hardcode: API_KEY = "abc123..."
REGION = "US-TN"
SPECIES = "rufgro"  # eBird species code for Ruffed Grouse

# How far back to fetch historic observations (years).
# Historic endpoint is one-date-per-call, so this affects runtime:
#   1 year  ≈  365 calls  ≈  ~6 min at 1s/call
#   3 years ≈ 1100 calls  ≈  ~18 min
YEARS_BACK = 3

# Rate-limit pacing — eBird is generous but be polite
SLEEP_BETWEEN_CALLS = 0.5  # seconds

OUTPUT_FILE = "../data/ebird_grouse_tn.json"

# ─────────────────────────────────────────────────────────────
# API helpers
# ─────────────────────────────────────────────────────────────
def ebird_get(path: str, params: dict | None = None) -> list | dict:
    if not API_KEY:
        sys.exit("ERROR: Set EBIRD_API_KEY environment variable or hardcode it in the script.")
    qs = f"?{urlencode(params)}" if params else ""
    url = f"https://api.ebird.org/v2{path}{qs}"
    req = Request(url, headers={"x-ebirdapitoken": API_KEY})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 404:
            return []  # no observations that day
        print(f"  ! HTTP {e.code} for {url}", file=sys.stderr)
        return []
    except URLError as e:
        print(f"  ! Network error: {e}", file=sys.stderr)
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

def fetch_historic_range(years_back: int) -> list:
    """
    Iterate day-by-day. The historic endpoint returns all species, so we
    filter client-side for rufgro. Slow but thorough.
    """
    today = date.today()
    start = today - timedelta(days=365 * years_back)
    end = today - timedelta(days=31)  # skip days covered by recent_30_days

    all_obs = []
    cur = start
    total_days = (end - start).days
    print(f"Fetching historic range: {start} → {end} ({total_days} days)")
    print(f"  Estimated runtime: ~{total_days * SLEEP_BETWEEN_CALLS / 60:.1f} minutes")

    days_done = 0
    while cur <= end:
        day_obs = ebird_get(
            f"/data/obs/{REGION}/historic/{cur.year}/{cur.month}/{cur.day}",
            {"cat": "species", "maxResults": 10000}
        )
        # filter to ruffed grouse
        grouse_obs = [o for o in day_obs if o.get("speciesCode") == SPECIES]
        if grouse_obs:
            print(f"  {cur}: {len(grouse_obs)} grouse")
        all_obs.extend(grouse_obs)

        days_done += 1
        if days_done % 50 == 0:
            print(f"  ... {days_done}/{total_days} days, {len(all_obs)} grouse so far")

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
# Main
# ─────────────────────────────────────────────────────────────
def main():
    print(f"eBird API fetch — Ruffed Grouse, {REGION}\n")
    if not API_KEY:
        print("ERROR: Set EBIRD_API_KEY environment variable, e.g.:")
        print('  export EBIRD_API_KEY="your-key-here"')
        sys.exit(1)

    all_observations = []
    all_observations.extend(fetch_recent_30_days())
    all_observations.extend(fetch_historic_range(YEARS_BACK))

    normalized = normalize(all_observations)
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
