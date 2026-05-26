#!/usr/bin/env python3
"""
build_grouse_csv.py

Combine the three data sources used in the TN ruffed grouse report into a
single downloadable CSV: data/grouse_observations.csv

Sources:
  - CBC: Christmas Bird Count detections (1966–2024) at six TN circles
  - eBird: API observations (loaded from data/ebird_grouse_tn.json)
  - field-sighting: personal observations + forum-reported locations

Run from the scripts/ directory:
    python3 build_grouse_csv.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "..", "data", "grouse_observations.csv")
EBIRD_JSON = os.path.join(HERE, "..", "data", "ebird_grouse_tn.json")

# ─────────────────────────────────────────────────────────────
# CBC circles + counts (mirrors the JS data structure in index.html)
# ─────────────────────────────────────────────────────────────
CBC_CIRCLES = [
    {"name": "Fish Springs",   "code": "82042", "lat": 36.317, "lng": -82.058, "range": (1966, 2023)},
    {"name": "Allens Bridge",  "code": "82041", "lat": 36.260, "lng": -82.140, "range": (1966, 2023)},
    {"name": "Newfound Gap",   "code": "82903", "lat": 35.611, "lng": -83.425, "range": (1990, 2024)},
    {"name": "Tellico",        "code": "82902", "lat": 35.363, "lng": -84.294, "range": (1995, 2024)},
    {"name": "Mecca",          "code": "82901", "lat": 35.300, "lng": -84.320, "range": (1994, 2023)},
    {"name": "Oliver Springs", "code": "82034", "lat": 36.045, "lng": -84.344, "range": (1966, 2022)},
]

# year → count. Missing year defaults to 0 (count conducted, no birds).
# None means count was not conducted that year.
CBC_COUNTS = {
    "Fish Springs":  {1972: 1, 1982: None, 1988: None, 1989: None, 1990: None, 2020: None, 2023: None},
    "Allens Bridge": {1985: 1, 1995: None, 1998: None, 2000: None, 2020: None, 2023: None},
    "Tellico":       {2005: 1, 1996: None, 2018: None, 2020: None, 2023: None, 2024: None},
    "Mecca":         {1997: 1, 2004: 1, 2019: 1, 2020: None, 2022: None, 2023: None},
    "Newfound Gap":  {2004: 1, 2021: 2},
    "Oliver Springs":{1969: 1, 2020: None},
}

FIELD_SIGHTINGS = [
    {"date": "2025-03-24", "year": 2025, "name": "OnX sighting 3/24/25",
     "lat": 36.0514, "lng": -84.7395,
     "note": "Confirmed sighting near Catoosa WMA"},
    {"date": "2023",       "year": 2023, "name": "Lancing area",
     "lat": 36.116,  "lng": -84.689,
     "note": "Forum reports of birds, just north of Catoosa"},
]

FIELDS = ["source", "date", "year", "location_name", "lat", "lng", "count", "notes"]


def cbc_rows():
    for circle in CBC_CIRCLES:
        y_start, y_end = circle["range"]
        counts = CBC_COUNTS.get(circle["name"], {})
        for year in range(y_start, y_end + 1):
            v = counts.get(year, 0)
            base = {
                "source": "CBC",
                "date": str(year),
                "year": year,
                "location_name": circle["name"],
                "lat": circle["lat"],
                "lng": circle["lng"],
            }
            if v is None:
                yield {**base, "count": "", "notes": f"CBC circle {circle['code']}; no count conducted"}
            else:
                note = f"CBC circle {circle['code']}"
                if v > 0:
                    note += "; detection"
                yield {**base, "count": v, "notes": note}


def sighting_rows():
    for s in FIELD_SIGHTINGS:
        yield {
            "source": "field-sighting",
            "date": s["date"],
            "year": s["year"],
            "location_name": s["name"],
            "lat": s["lat"],
            "lng": s["lng"],
            "count": 1,
            "notes": s["note"],
        }


def ebird_rows():
    try:
        with open(EBIRD_JSON) as f:
            payload = json.load(f)
    except FileNotFoundError:
        print(f"  ! eBird JSON not found at {EBIRD_JSON} — skipping eBird rows", file=sys.stderr)
        return
    for o in payload.get("observations", []):
        cnt = o.get("count")
        yield {
            "source": "eBird",
            "date": o.get("date", ""),
            "year": o.get("year", ""),
            "location_name": o.get("loc", ""),
            "lat": o.get("lat", ""),
            "lng": o.get("lng", ""),
            "count": cnt if cnt is not None else "",
            "notes": "eBird observation",
        }


def main():
    rows = list(cbc_rows()) + list(sighting_rows()) + list(ebird_rows())
    # Sort: source, then date (string sort; CBC years and eBird ISO dates both work).
    rows.sort(key=lambda r: (r["source"], str(r["date"])))

    with open(OUTPUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    counts = Counter(r["source"] for r in rows)
    print(f"Wrote {OUTPUT} — {len(rows)} rows")
    for src, n in counts.items():
        print(f"  {src}: {n}")


if __name__ == "__main__":
    main()
