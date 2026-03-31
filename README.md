# Fantasy Baseball Projections

Tools for generating fantasy baseball cheatsheets using Rest of Season (RoS) projections from FanGraphs, Yahoo position eligibility, and a live draft tracker via the Yahoo Fantasy API.

## Quick Start

```bash
pip install -r requirements.txt
python update_fantasy.py
```

Or use the shell wrapper:

```bash
./update_fantasy.sh
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scrape_projections.py` | Scrapes batting projections from FanGraphs |
| `scrape_pitching_projections.py` | Scrapes pitching projections from FanGraphs |
| `fetch_positions.py` | Downloads Yahoo player position eligibility from Google Sheets |
| `batter_cheatsheet.py` | Generates a batter cheatsheet with fantasy point projections and VORP |
| `pitcher_cheatsheet.py` | Generates a pitcher cheatsheet with fantasy point projections and VORP |
| `upload_to_sheets.py` | Uploads cheatsheets to Google Sheets |
| `draft_tracker.py` | Live draft tracker using the Yahoo Fantasy API |
| `update_fantasy.py` | Orchestrates scraping, cheatsheet generation, and upload |
| `update_fantasy.sh` | Shell wrapper for `update_fantasy.py` |

## Apps Script

The `apps_script/` directory contains Google Apps Script code that adds live ownership status (rostered / waivers / free agent) to the cheatsheet spreadsheet. See [`apps_script/README.md`](apps_script/README.md) for setup instructions.

## Directory Structure

```
fantasy/
├── apps_script/         # Google Apps Script for ownership status
│   ├── Code.gs
│   ├── OAuth.gs
│   └── README.md
├── data/                # (gitignored) scraped & generated data
│   ├── <year>/projections/
│   ├── positions/
│   └── output/
├── scrape_projections.py
├── scrape_pitching_projections.py
├── fetch_positions.py
├── batter_cheatsheet.py
├── pitcher_cheatsheet.py
├── upload_to_sheets.py
├── draft_tracker.py
├── update_fantasy.py
└── update_fantasy.sh
```

## Fantasy Scoring System

### Batting
| Category | Points |
|----------|--------|
| Runs | 2 |
| Singles | 3 |
| Doubles | 5 |
| Triples | 8 |
| Home Runs | 10 |
| RBIs | 4 |
| Stolen Bases | 5 |
| Walks | 2 |
| Hit By Pitch | 2 |

## VORP

Value Over Replacement Player. Replacement levels:
- **C, 1B, 2B, 3B, SS**: 12th best at position
- **OF**: 36th best
- **Util**: 1300 points

Players eligible at multiple positions are assigned the position that maximizes their VORP.
