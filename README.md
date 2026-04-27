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
| `scrape_2025_actuals.py`         | Scrapes 2025 batting + pitching actuals from FanGraphs (via curl_cffi)               |
| `fetch_positions.py`             | Downloads Yahoo player position eligibility from Google Sheets                       |
| `batter_cheatsheet.py`           | Generates a batter cheatsheet with fantasy point projections (ATC + OOPSY)           |
| `pitcher_cheatsheet.py`          | Generates a pitcher cheatsheet with projections, Eno rankings, and probable starts   |
| `upload_to_sheets.py`            | Uploads cheatsheets to Google Sheets with formatting and Status column preservation  |
| `draft_tracker.py`               | Live draft tracker using the Yahoo Fantasy API                                       |
| `update_ownership.py`            | Refreshes Yahoo ownership Status column on the Hitters/Pitchers tabs                 |
| `yahoo_client.py`                | Shared Yahoo Fantasy API client (OAuth + paginated `/players` reads)                 |
| `update_fantasy.py`              | Orchestrates scraping, cheatsheet generation, upload, and ownership refresh          |
| `update_fantasy.sh`              | Shell wrapper for `update_fantasy.py`                                                |

## Ownership Status Column

Each player gets a **Status** column showing their team name (rostered), waiver date (e.g. "Waivers (4/15)"), "FA" (free agent), or "My Team", color-coded with conditional formatting.

The scheduled GitHub Action refreshes the Status column via `update_ownership.py` (Python, runs on the runner) which talks to the Yahoo Fantasy API directly. The earlier Apps Script `doGet` webhook was retired because it kept hitting Google Apps Script's undocumented `UrlFetchApp` bandwidth limit.

The `apps_script/` directory still contains the Apps Script project, but it's now only used for the manual `Fantasy Tools > Update Ownership Status` menu inside the spreadsheet UI. See [`apps_script/README.md`](apps_script/README.md) for setup instructions for that path.

### GitHub Actions secrets

The daily workflow needs these repo secrets:

| Secret                        | Purpose                                                                |
|-------------------------------|------------------------------------------------------------------------|
| `GOOGLE_SERVICE_ACCOUNT_KEY`  | Service account JSON for the Sheets API                                |
| `YAHOO_OAUTH_JSON_B64`        | base64 of `oauth2.json` (Yahoo OAuth2 creds for `update_ownership.py`) |
| `YAHOO_LEAGUE_KEY`            | Yahoo league key, e.g. `469.l.94637`                                    |

To populate `YAHOO_OAUTH_JSON_B64` from a working local `oauth2.json`:

```bash
base64 -i oauth2.json | tr -d '\n' | pbcopy
```

If Yahoo refresh tokens ever expire (rare, but possible), regenerate `oauth2.json` locally with `python draft_tracker.py --setup` and re-upload the secret.

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
│   ├── 2025/actuals/    # 2025 batting/pitching actuals (for 2025 Pts/G)
│   ├── positions/
│   └── output/
├── scrape_projections.py
├── scrape_pitching_projections.py
├── scrape_2025_actuals.py
├── fetch_positions.py
├── batter_cheatsheet.py
├── pitcher_cheatsheet.py
├── upload_to_sheets.py
├── draft_tracker.py
├── update_ownership.py
├── yahoo_client.py
├── update_fantasy.py
└── update_fantasy.sh
```

## Projection Sources

### Batters

Two RoS projection systems, merged by player:

- **ATC** — consensus Rest of Season projections
- **OOPSY** — another RoS system from FanGraphs

Output columns: `Player`, `Position`, `ATC Pts`, `OOPSY Pts`, `ATC Pts/G`, `OOPSY Pts/G`, `2025 Pts/G` (empirical). Players whose max projected games (across ATC and OOPSY) is below 60% of the league-wide max projected games are filtered out.

### Pitchers

- **THE BAT X** — Rest of Season pitching projections
- **OOPSY** — Rest of Season pitching projections
- **Eno Sarris Pitch Report** — expert pitcher rankings (downloaded from Google Sheets)
- **FanGraphs Probables Grid** — upcoming probable start schedule

Pitchers are sorted by Eno rank. Output columns include points per game from each projection system, empirical `2025 Pts/G`, projected games (with GS breakdown), Eno rank, and schedule columns with date-based headers.

#### Inclusion filter

To keep the Pitchers tab focused on relevant arms, a pitcher is included only if they match **at least one** of:

1. Owned by a Yahoo team or on waivers (looked up live via the Yahoo API)
2. Ranked by Eno (in the Pitch Report, Injured, or Prospect tables)
3. Projected to start at least `max(projected GS) / 3` games rest-of-season across THE BAT X / OOPSY
4. Probable starter in any game this fantasy week or next

If Yahoo ownership data can't be fetched (missing `YAHOO_LEAGUE_KEY`, OAuth failure, etc.), the filter is skipped entirely so legitimately rostered pitchers aren't dropped on a transient outage.

### Empirical 2025 Pts/G

Both cheatsheets include a `2025 Pts/G` column showing each player's actual fantasy Pts/G from the 2025 season, scored using the league rules below. The 2025 season is final, so the underlying CSVs are checked into the repo at `data/2025/actuals/2025_{batting,pitching}_actuals.csv` and the daily pipeline just reads them; nothing re-scrapes on each run.

To regenerate (e.g. when bumping to 2026 actuals after that season ends):

```bash
python scrape_2025_actuals.py
```

The `/leaders/major-league` endpoint (unlike `/projections/`) is behind Cloudflare's bot challenge, so plain `requests` and `pybaseball` both 403. The scraper uses `curl_cffi` to impersonate a real Chrome TLS fingerprint and parses the leaderboard JSON out of the page's `__NEXT_DATA__` script tag, then trims the response down to just the columns the cheatsheets need (`playerid`, `G`, scoring counting stats) so the committed CSVs stay small.

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
