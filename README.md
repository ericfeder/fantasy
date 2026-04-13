# Fantasy Baseball Projections

Tools for generating fantasy baseball cheatsheets using Rest of Season (RoS) projections from FanGraphs, Yahoo position eligibility, Eno Sarris pitcher rankings, and a live draft tracker via the Yahoo Fantasy API. Cheatsheets are uploaded to Google Sheets with ownership status powered by Google Apps Script.

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

| Script                           | Purpose                                                                              |
| -------------------------------- | ------------------------------------------------------------------------------------ |
| `scrape_projections.py`          | Scrapes batting projections from FanGraphs                                           |
| `scrape_pitching_projections.py` | Scrapes pitching projections from FanGraphs                                          |
| `fetch_positions.py`             | Downloads Yahoo player position eligibility from Google Sheets                       |
| `batter_cheatsheet.py`           | Generates a batter cheatsheet with fantasy point projections (ATC + OOPSY)           |
| `pitcher_cheatsheet.py`          | Generates a pitcher cheatsheet with projections, Eno rankings, and probable starts   |
| `upload_to_sheets.py`            | Uploads cheatsheets to Google Sheets with formatting and Status column preservation  |
| `draft_tracker.py`               | Live draft tracker using the Yahoo Fantasy API                                       |
| `update_fantasy.py`              | Orchestrates scraping, cheatsheet generation, and upload                             |
| `update_fantasy.sh`              | Shell wrapper for `update_fantasy.py`                                                |

## Apps Script

The `apps_script/` directory contains Google Apps Script code that adds live ownership status to the cheatsheet spreadsheet. Each player gets a **Status** column showing their team name (rostered), waiver date (e.g. "Waivers (4/15)"), "FA" (free agent), or "My Team". Color-coded with conditional formatting. See [`apps_script/README.md`](apps_script/README.md) for setup instructions.

## Directory Structure

```
fantasy/
├── apps_script/         # Google Apps Script for ownership status
│   ├── .clasp.json
│   ├── appsscript.json
│   ├── Code.gs
│   ├── OAuth.gs
│   └── README.md
├── data/                # (gitignored) scraped & generated data
│   ├── <year>/projections/
│   ├── <year>/eno_pitch_report.csv
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

## Projection Sources

### Batters

Two RoS projection systems, merged by player:

- **ATC** — consensus Rest of Season projections
- **OOPSY** — another RoS system from FanGraphs

Output columns: `Player`, `Position`, `ATC Pts`, `OOPSY Pts`, `ATC Pts/G`, `OOPSY Pts/G`. Players with fewer than 10 projected games in all systems are filtered out.

### Pitchers

- **THE BAT X** — Rest of Season pitching projections
- **OOPSY** — Rest of Season pitching projections
- **Eno Sarris Pitch Report** — expert pitcher rankings (downloaded from Google Sheets)
- **FanGraphs Probables Grid** — upcoming probable start schedule

Pitchers are sorted by Eno rank. Output columns include points per game from each system, projected games (with GS breakdown), Eno rank, and schedule columns with date-based headers.

## Fantasy Scoring System

### Batting

| Category     | Points |
| ------------ | ------ |
| Runs         | 2      |
| Singles      | 3      |
| Doubles      | 5      |
| Triples      | 8      |
| Home Runs    | 10     |
| RBIs         | 4      |
| Stolen Bases | 5      |
| Walks        | 2      |
| Hit By Pitch | 2      |

### Pitching

| Category         | Points |
| ---------------- | ------ |
| Innings Pitched  | 2.25   |
| Wins             | 4      |
| Saves            | 2      |
| Holds            | 1      |
| Strikeouts       | 2      |
| Hits Allowed     | −0.6   |
| Earned Runs      | −2     |
| Walks Allowed    | −0.6   |
| Hit By Pitch     | −0.6   |

CG (2.5), SHO (2.5), and NH (5) are part of the scoring but not projected by any system (too rare to meaningfully affect rankings).

## Pitcher Probable Starts

The pitcher cheatsheet includes upcoming probable start data from the FanGraphs Probables Grid API. Five schedule columns are added with date-based headers:

| Column             | Header Example | Description                            | Value Example           |
| ------------------ | -------------- | -------------------------------------- | ----------------------- |
| `start_today`      | `4/13 (Mon)`   | Starting today?                        | `vs HOU` or `@ SEA`    |
| `start_tomorrow`   | `4/14 (Tue)`   | Starting tomorrow?                     | `@ MIN`                 |
| `start_day_after`  | `4/15 (Wed)`   | Starting day after tomorrow?           | `vs CHC`                |
| `starts_this_week` | `4/13-4/19`    | All starts this fantasy week (Mon–Sun) | `Mon vs HOU, Thu @ LAD` |
| `starts_next_week` | `4/20-4/26`    | All starts next fantasy week (Mon–Sun) | `Tue vs NYM, Sun @ CHC` |

`vs` = home game, `@` = away game. Data covers ~2 weeks out with near-complete rotation projections.

## Google Sheets Upload

`upload_to_sheets.py` handles uploading cheatsheets to Google Sheets with:

- Frozen header row and first column
- Bold, centered headers with auto-resized column widths (plus configurable padding)
- **Status column preservation** — reads the existing Status column before upload and restores it afterward, so ownership data from the Apps Script isn't lost on refresh
