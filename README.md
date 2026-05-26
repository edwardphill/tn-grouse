# Ruffed Grouse in Tennessee — Field Report

A living field report on the range, numbers, habitat, and hunting prospects of *Bonasa umbellus* in Tennessee. Anchored in Christmas Bird Count data, hunter reports, eBird observations, and the long arc of the Southern Appalachian decline.

**Live site:** https://edwardphill.github.io/tn-grouse/

## Repo structure

```
.
├── index.html                      ← the report (open in a browser to preview locally)
├── data/
│   └── ebird_grouse_tn.json        ← eBird snapshot, written by the fetcher script (not committed if empty)
├── scripts/
│   └── fetch_ebird_grouse.py       ← pulls TN ruffed grouse observations from the eBird API 2.0
├── .gitignore
└── README.md
```

The report is a single, self-contained HTML file. No build step. The only runtime dependency is fetching `data/ebird_grouse_tn.json` if present; the report degrades gracefully when it's missing (the eBird layer button shows `(no data)` and stays disabled).

## Local preview

Just open `index.html` in a browser, **or** serve it locally to enable the eBird fetch (which won't work from `file://`):

```bash
python3 -m http.server 8000
# then open http://localhost:8000
```

## Refreshing the eBird data

The eBird layer is a pre-fetched snapshot, not a live API call (keys can't safely live in client-side code on a public Pages site). To update it:

1. **Get an eBird API key** (free): https://ebird.org/api/keygen
2. **Export the key**:
   ```bash
   export EBIRD_API_KEY="your-key-here"
   ```
3. **Run the fetcher** from the `scripts/` directory:
   ```bash
   cd scripts
   python3 fetch_ebird_grouse.py
   ```
   This writes `../data/ebird_grouse_tn.json` and takes ~18 minutes for 3 years of data.
4. **Commit and push** the updated JSON:
   ```bash
   git add data/ebird_grouse_tn.json
   git commit -m "Refresh eBird ruffed grouse snapshot"
   git push
   ```
   GitHub Pages picks up the change in ~1 minute.

Tune `YEARS_BACK` in the script to pull more or less history.

## Deploying to GitHub Pages

This repo is structured for a **user/org Pages site** (`<username>.github.io`).

```bash
# 1. Create the repo on GitHub named exactly: <your-username>.github.io
# 2. From this directory:
git init
git add .
git commit -m "Initial commit: TN grouse field report v0.4"
git branch -M main
git remote add origin git@github.com:<your-username>/<your-username>.github.io.git
git push -u origin main
```

GitHub auto-publishes `main` for user/org Pages sites — no extra setup needed. Site goes live at `https://<your-username>.github.io/` within a minute.

**Note:** if you already have a `<username>.github.io` repo with other content, this will overwrite it. Better to drop `index.html`, `data/`, and `scripts/` into a subfolder (e.g. `tn-grouse/`) of your existing site repo, and the report will live at `https://<your-username>.github.io/tn-grouse/`.

## Data sources

| Source | What | Where |
|---|---|---|
| TWRA Gamebird Reports | CBC counts at 6 TN circles, 1966–2024 | embedded in `index.html` |
| Ruffed Grouse Society (Eastern Grouse Working Group, 2020) | 71% Southern Appalachian decline figure | cited inline |
| eBird API 2.0 | Recent + historic TN observations | `data/ebird_grouse_tn.json` |
| OnX field sighting (3/24/25) | Personal observation near Catoosa | embedded in `index.html` |
| TWRA Watchable Wildlife | Range, status, 1989–90 harvest figures | cited inline |

## License

Field report content: CC BY 4.0. Code: MIT.

eBird data is © Cornell Lab of Ornithology, used under the [eBird Terms of Use](https://www.birds.cornell.edu/home/ebird-terms-of-use/).

## Versions

- **v0.4** — GitHub Pages structure, eBird layer scaffolding, fetcher script
- **v0.3** — Real Tennessee outline, controls moved above map
- **v0.2** — Field sightings layer, layer toggles, TJH credit, MN/VT comparative notes, Catoosa callout
- **v0.1** — Initial report with CBC year slider
