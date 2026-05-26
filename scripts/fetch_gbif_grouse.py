#!/usr/bin/env python3
"""
fetch_gbif_grouse.py

Pull non-eBird ruffed grouse occurrences for Tennessee from the GBIF API.

GBIF aggregates from many providers; we filter out eBird (we already have
that data via fetch_ebird_grouse.py) so this layer adds records that eBird
alone doesn't have:
  - iNaturalist research-grade observations
  - Great Backyard Bird Count
  - USGS Bird Phenology Program (historic banding records)
  - Museum specimens (e.g. Carnegie vertebrate paleontology)
  - Other state/federal datasets

Output: data/gbif_grouse_tn.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TAXON_KEY = 2473702              # GBIF usageKey for Bonasa umbellus
STATE = "Tennessee"
COUNTRY = "US"
EBIRD_DATASET = "4fa7b334-ce0d-4e88-aaae-2e0c138d049e"  # exclude (already covered)
PAGE_SIZE = 300
HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "..", "data", "gbif_grouse_tn.json")


def gbif_get(offset: int) -> dict:
    params = {
        "taxonKey": TAXON_KEY,
        "country": COUNTRY,
        "stateProvince": STATE,
        "limit": PAGE_SIZE,
        "offset": offset,
    }
    url = f"https://api.gbif.org/v1/occurrence/search?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "tn-grouse-report/0.5"})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError) as e:
            wait = 2 ** attempt
            print(f"  ! retry {attempt+1}/3 after {e}", file=sys.stderr)
            time.sleep(wait)
    sys.exit(f"ERROR: GBIF unreachable at offset {offset}")


def normalize(o: dict) -> dict:
    lat = o.get("decimalLatitude")
    lng = o.get("decimalLongitude")
    return {
        "gbif_key": o.get("key"),
        "dataset": o.get("datasetName") or o.get("datasetKey", ""),
        "basis": o.get("basisOfRecord", ""),
        "date": o.get("eventDate", ""),
        "year": o.get("year"),
        "lat": lat,
        "lng": lng,
        "coord_uncertainty_m": o.get("coordinateUncertaintyInMeters"),
        "loc": o.get("locality") or o.get("county") or "",
        "recorded_by": o.get("recordedBy", ""),
        "institution": o.get("institutionCode", ""),
        "url": o.get("occurrenceID", ""),
    }


def main():
    all_records = []
    offset = 0
    while True:
        page = gbif_get(offset)
        results = page.get("results", [])
        if not results:
            break
        all_records.extend(results)
        offset += len(results)
        print(f"  fetched {offset}/{page.get('count', '?')} so far")
        if page.get("endOfRecords") or offset >= page.get("count", 0):
            break

    # Drop eBird-sourced records (already covered by fetch_ebird_grouse.py)
    non_ebird = [o for o in all_records if o.get("datasetKey") != EBIRD_DATASET]
    print(f"Total: {len(all_records)} GBIF records, of which {len(non_ebird)} are non-eBird")

    # Require lat/lng (some GBIF records are coordinate-less)
    geo = [o for o in non_ebird if o.get("decimalLatitude") and o.get("decimalLongitude")]
    print(f"  with coordinates: {len(geo)}")

    normalized = [normalize(o) for o in geo]
    normalized.sort(key=lambda o: o.get("date") or "", reverse=True)

    # Group by dataset for a quick sanity print
    from collections import Counter
    by_ds = Counter(o["dataset"] for o in normalized)
    print("\nBy dataset:")
    for ds, n in by_ds.most_common():
        print(f"  {n:>4}  {ds}")

    payload = {
        "source": "GBIF",
        "region": f"{COUNTRY}-TN",
        "species": "Bonasa umbellus",
        "fetched_at": date.today().isoformat(),
        "excludes": [EBIRD_DATASET],
        "observations": normalized,
    }
    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nWrote {OUTPUT} ({len(normalized)} observations)")


if __name__ == "__main__":
    main()
