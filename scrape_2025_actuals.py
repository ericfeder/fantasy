"""Scrape 2025 season actuals from FanGraphs leaderboards.

Used by ``batter_cheatsheet.py`` / ``pitcher_cheatsheet.py`` to compute the
empirical ``2025 Pts/G`` column. The ``/leaders/major-league`` endpoint sits
behind Cloudflare's bot challenge, so plain ``requests`` (and ``pybaseball``)
get back a 403. ``curl_cffi`` impersonates a real Chrome TLS fingerprint,
which gets through.

The leaderboard payload is embedded in the page as ``__NEXT_DATA__`` JSON
rather than served from a public JSON endpoint, so we parse the page HTML
and pull the row array out of the React Query dehydrated cache.

The 2025 season is final, so the CSVs this script writes are checked into
git and re-running it is a one-time / manual operation (e.g. when bumping
to 2026 actuals after that season wraps). It's intentionally not part of
the daily ``update_fantasy.py`` pipeline.
"""
import json
import os
import re
import sys

import pandas as pd
from curl_cffi import requests as cffi_requests

ACTUALS_DIR = 'data/2025/actuals'

# qual=0 → all players, type=8 → "Dashboard" preset (full stat dump),
# pageitems=2000000000 → no pagination.
_BASE = (
    'https://www.fangraphs.com/leaders/major-league'
    '?pos=all&stats={stats}&lg=all&qual=0'
    '&season=2025&season1=2025&pageitems=2000000000&type=8'
)

LEADER_URLS = {
    'batting':  _BASE.format(stats='bat'),
    'pitching': _BASE.format(stats='pit'),
}

OUTPUT_FILES = {
    'batting':  f'{ACTUALS_DIR}/2025_batting_actuals.csv',
    'pitching': f'{ACTUALS_DIR}/2025_pitching_actuals.csv',
}

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
    re.DOTALL,
)
HTML_TAG_RE = re.compile(r'<[^>]+>')

# Keep just the columns the cheatsheets need so the committed CSVs stay
# small (~50 KB instead of ~4 MB). FanGraphs returns ~475 columns total,
# the vast majority of which are pitch-tracking detail we don't use.
KEEP_COLS = {
    'batting': [
        'playerid', 'xMLBAMID', 'PlayerName', 'Team',
        'G', 'AB', 'R', '1B', '2B', '3B', 'HR', 'RBI', 'SB', 'BB', 'HBP',
    ],
    'pitching': [
        'playerid', 'xMLBAMID', 'PlayerName', 'Team',
        'G', 'GS', 'IP', 'W', 'SV', 'HLD', 'H', 'ER', 'BB', 'HBP', 'SO',
    ],
}


def _extract_rows(html, label):
    m = NEXT_DATA_RE.search(html)
    if not m:
        raise RuntimeError(f"Could not find __NEXT_DATA__ in {label} leaders response")

    payload = json.loads(m.group(1))
    queries = payload['props']['pageProps']['dehydratedState']['queries']
    for q in queries:
        data = q.get('state', {}).get('data')
        if isinstance(data, dict) and isinstance(data.get('data'), list):
            rows = data['data']
            if rows and isinstance(rows[0], dict):
                return rows
    raise RuntimeError(f"No leaderboard data array found in {label} leaders response")


def fetch_leaders(label, url):
    print(f"Scraping 2025 {label} actuals from FanGraphs...")
    r = cffi_requests.get(url, impersonate='chrome', timeout=30)
    r.raise_for_status()
    rows = _extract_rows(r.text, label)
    df = pd.DataFrame(rows)

    keep = [c for c in KEEP_COLS[label] if c in df.columns]
    missing = [c for c in KEEP_COLS[label] if c not in df.columns]
    if missing:
        print(f"  Warning: {label} response missing expected columns: {missing}")
    df = df[keep].copy()

    # The leaderboard renderer wraps the Team cell in an <a href="..."> tag
    # for cross-linking. Strip those so the CSV holds plain "DET" instead
    # of '<a href="...">DET</a>'.
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].astype(str).str.replace(HTML_TAG_RE, '', regex=True)

    return df


def main():
    os.makedirs(ACTUALS_DIR, exist_ok=True)

    failures = []
    for label, url in LEADER_URLS.items():
        try:
            df = fetch_leaders(label, url)
        except Exception as e:
            print(f"ERROR scraping 2025 {label} actuals: {e}")
            failures.append(label)
            continue

        path = OUTPUT_FILES[label]
        df.to_csv(path, index=False)
        print(f"Saved {len(df)} {label} rows to {path}")

    if failures:
        print(f"\nFailed to scrape: {', '.join(failures)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
