#!/usr/bin/env python3
"""
Live draft tracker: polls the Yahoo Fantasy API for new picks and updates
the Google Sheets cheatsheet with "Drafted" (team name) and "Pick" columns.

Usage:
    python draft_tracker.py --setup          # one-time OAuth2 credential setup
    python draft_tracker.py --test           # verify the full pipeline pre-draft
    python draft_tracker.py                  # auto-discover league, start tracking
    python draft_tracker.py --league-id ID   # use a specific league
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import unicodedata

import pandas as pd
from yahoo_oauth import OAuth2
from yahoo_fantasy_api import game as yfa_game

OAUTH_FILE = os.path.join(os.path.dirname(__file__), 'oauth2.json')
SPREADSHEET_ID = '1LRhXDU-cu66YVhGZWZeY9qi1187elU8lcFtS_jVgxXs'
POLL_INTERVAL = 15

TABS = {
    'Hitters': 'data/output/batter_cheatsheet.csv',
    'Pitchers': 'data/output/pitcher_cheatsheet.csv',
}


# ---------------------------------------------------------------------------
# Name normalisation (mirrors batter_cheatsheet.py logic)
# ---------------------------------------------------------------------------

def normalize_name(name):
    if not isinstance(name, str):
        return ''
    name = name.lower()
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    name = re.sub(r'\s+(jr\.?|sr\.?|[ivx]+)$', '', name)
    name = re.sub(r'\s+\([^)]+\)', '', name)
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


# ---------------------------------------------------------------------------
# Google Sheets helpers (reuse gws CLI from upload_to_sheets.py)
# ---------------------------------------------------------------------------

def _run_gws(*args):
    result = subprocess.run(
        ['gws', *args],
        capture_output=True, text=True,
    )
    return result


def sheet_read_header(tab_name):
    """Read the first row of a tab to discover existing columns."""
    result = _run_gws(
        'sheets', 'spreadsheets', 'values', 'get',
        '--params', json.dumps({
            'spreadsheetId': SPREADSHEET_ID,
            'range': f'{tab_name}!1:1',
        }),
    )
    if result.returncode != 0:
        return []
    lines = [l for l in result.stdout.splitlines() if not l.strip().startswith('Using keyring')]
    data = json.loads('\n'.join(lines))
    values = data.get('values', [[]])
    return values[0] if values else []


def col_letter(index):
    """Convert 0-based column index to A, B, ... Z, AA, AB, ..."""
    letters = ''
    while True:
        letters = chr(ord('A') + index % 26) + letters
        index = index // 26 - 1
        if index < 0:
            break
    return letters


_sheet_id_cache = {}


def get_sheet_id(tab_name):
    """Get the numeric sheetId for a given tab name (cached)."""
    if tab_name in _sheet_id_cache:
        return _sheet_id_cache[tab_name]
    result = _run_gws(
        'sheets', 'spreadsheets', 'get',
        '--params', json.dumps({'spreadsheetId': SPREADSHEET_ID}),
    )
    if result.returncode != 0:
        return None
    lines = [l for l in result.stdout.splitlines() if not l.strip().startswith('Using keyring')]
    data = json.loads('\n'.join(lines))
    for sheet in data.get('sheets', []):
        title = sheet['properties']['title']
        _sheet_id_cache[title] = sheet['properties']['sheetId']
    return _sheet_id_cache.get(tab_name)


def ensure_columns(tab_name, needed_cols):
    """Expand the grid if the tab has fewer columns than needed."""
    sheet_id = get_sheet_id(tab_name)
    if sheet_id is None:
        return
    _run_gws(
        'sheets', 'spreadsheets', 'batchUpdate',
        '--params', json.dumps({'spreadsheetId': SPREADSHEET_ID}),
        '--json', json.dumps({'requests': [{
            'updateSheetProperties': {
                'properties': {
                    'sheetId': sheet_id,
                    'gridProperties': {'columnCount': needed_cols},
                },
                'fields': 'gridProperties.columnCount',
            }
        }]}),
    )


def sheet_write_cells(tab_name, cell_range, values):
    """Write a list-of-lists to a specific range."""
    result = _run_gws(
        'sheets', 'spreadsheets', 'values', 'update',
        '--params', json.dumps({
            'spreadsheetId': SPREADSHEET_ID,
            'range': f'{tab_name}!{cell_range}',
            'valueInputOption': 'RAW',
        }),
        '--json', json.dumps({'values': values}),
    )
    if result.returncode != 0:
        stderr = [l for l in result.stderr.splitlines() if 'keyring' not in l.lower()]
        if stderr:
            print(f'  Sheet write error ({tab_name}!{cell_range}): {" ".join(stderr)}')


# ---------------------------------------------------------------------------
# OAuth setup
# ---------------------------------------------------------------------------

def setup_oauth():
    print('=== Yahoo Fantasy API – OAuth2 Setup ===\n')
    print('1. Go to https://developer.yahoo.com/apps/create/')
    print('2. Create an app with "Fantasy Sports" read access.')
    print('3. Copy the Consumer Key and Consumer Secret.\n')

    consumer_key = input('Consumer Key: ').strip()
    consumer_secret = input('Consumer Secret: ').strip()

    if not consumer_key or not consumer_secret:
        print('Error: both key and secret are required.')
        sys.exit(1)

    creds = {'consumer_key': consumer_key, 'consumer_secret': consumer_secret}
    with open(OAUTH_FILE, 'w') as f:
        json.dump(creds, f)
    print(f'\nCredentials saved to {OAUTH_FILE}')

    print('\nAuthenticating with Yahoo (a browser window will open)...')
    OAuth2(None, None, from_file=OAUTH_FILE)
    print('Authentication successful! You can now run: python draft_tracker.py')


def get_oauth():
    if not os.path.exists(OAUTH_FILE):
        print(f'Error: {OAUTH_FILE} not found. Run with --setup first.')
        sys.exit(1)
    return OAuth2(None, None, from_file=OAUTH_FILE)


# ---------------------------------------------------------------------------
# League discovery
# ---------------------------------------------------------------------------

def discover_league(oauth, league_id_override=None):
    gm = yfa_game.Game(oauth, 'mlb')

    if league_id_override:
        lg = gm.to_league(league_id_override)
        settings = lg.settings()
        print(f'Using league: {settings["name"]} ({league_id_override})')
        return lg

    league_ids = gm.league_ids()
    if not league_ids:
        print('Error: no MLB leagues found for your account.')
        sys.exit(1)

    if len(league_ids) == 1:
        lid = league_ids[0]
    else:
        print('Multiple MLB leagues found:')
        for i, lid in enumerate(league_ids):
            lg_tmp = gm.to_league(lid)
            s = lg_tmp.settings()
            print(f'  [{i}] {s["name"]} ({lid})  season={s.get("season")}')
        choice = input('Select league number: ').strip()
        lid = league_ids[int(choice)]

    lg = gm.to_league(lid)
    settings = lg.settings()
    print(f'Using league: {settings["name"]} ({lid})')
    return lg


# ---------------------------------------------------------------------------
# Cheatsheet loading
# ---------------------------------------------------------------------------

def load_cheatsheets():
    """Return (tab_name -> {normalized_name -> row_index (1-based, header=row1)})
    and (tab_name -> list_of_player_names) for both tabs."""
    name_to_row = {}
    player_names = {}

    for tab, csv_path in TABS.items():
        full_path = os.path.join(os.path.dirname(__file__), csv_path)
        if not os.path.exists(full_path):
            print(f'Warning: {full_path} not found, skipping {tab}')
            continue

        df = pd.read_csv(full_path)
        lookup = {}
        names = []
        for i, row in df.iterrows():
            pname = row['PlayerName']
            norm = normalize_name(pname)
            sheet_row = i + 2  # row 1 is header, data starts at row 2
            lookup[pname] = sheet_row
            lookup[norm] = sheet_row
            names.append(pname)

        name_to_row[tab] = lookup
        player_names[tab] = names
        print(f'Loaded {len(names)} players from {tab} tab')

    return name_to_row, player_names


# ---------------------------------------------------------------------------
# Sheet column setup
# ---------------------------------------------------------------------------

def setup_sheet_columns(tabs_to_track):
    """Add 'Drafted' and 'Pick' header columns to each tab.
    Returns {tab_name: drafted_col_letter} so we know where to write."""
    col_info = {}
    for tab in tabs_to_track:
        header = sheet_read_header(tab)
        if 'Drafted' in header:
            drafted_idx = header.index('Drafted')
        else:
            drafted_idx = len(header)
            ensure_columns(tab, drafted_idx + 2)
            dletter = col_letter(drafted_idx)
            pletter = col_letter(drafted_idx + 1)
            sheet_write_cells(tab, f'{dletter}1:{pletter}1', [['Drafted', 'Pick']])
            print(f'  Added Drafted/Pick columns to {tab} at columns {dletter}/{pletter}')
        col_info[tab] = col_letter(drafted_idx)
    return col_info


# ---------------------------------------------------------------------------
# Draft tracking
# ---------------------------------------------------------------------------

def format_pick(pick_num, num_teams):
    """Format overall pick number as 'round.pick_in_round', e.g. '1.03'."""
    rnd = (pick_num - 1) // num_teams + 1
    pick_in_round = (pick_num - 1) % num_teams + 1
    return f'{rnd}.{pick_in_round:02d}'


def collect_player_updates(player_name, team_name, pick_label, name_to_row, col_info,
                           value_updates, format_requests):
    """Find the player in the cheatsheet and queue updates for batching."""
    norm = normalize_name(player_name)
    matched = False

    if '(Batter)' in player_name:
        allowed_tabs = {'Hitters'}
    elif '(Pitcher)' in player_name:
        allowed_tabs = {'Pitchers'}
    else:
        allowed_tabs = None

    for tab, lookup in name_to_row.items():
        if allowed_tabs and tab not in allowed_tabs:
            continue
        row = lookup.get(player_name) or lookup.get(norm)
        if row is None:
            continue
        drafted_col_idx = ord(col_info[tab]) - ord('A')

        sheet_id = get_sheet_id(tab)
        if sheet_id is None:
            continue

        value_updates.append({
            'updateCells': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': row - 1,
                    'endRowIndex': row,
                    'startColumnIndex': drafted_col_idx,
                    'endColumnIndex': drafted_col_idx + 2,
                },
                'rows': [{'values': [
                    {'userEnteredValue': {'stringValue': team_name}},
                    {'userEnteredValue': {'stringValue': pick_label}},
                ]}],
                'fields': 'userEnteredValue',
            }
        })

        format_requests.append(
            _make_style_request(sheet_id, row, drafted_col_idx, drafted=True)
        )
        matched = True

    return matched


def mark_player_on_sheet(player_name, team_name, pick_label, name_to_row, col_info):
    """Single-player write (used by test mode). Batches internally."""
    value_updates = []
    format_requests = []
    matched = collect_player_updates(
        player_name, team_name, pick_label, name_to_row, col_info,
        value_updates, format_requests,
    )
    flush_batch(value_updates, format_requests)
    return matched


def sheet_clear_cells(tab_name, cell_range):
    """Clear values from a specific range."""
    _run_gws(
        'sheets', 'spreadsheets', 'values', 'clear',
        '--params', json.dumps({
            'spreadsheetId': SPREADSHEET_ID,
            'range': f'{tab_name}!{cell_range}',
        }),
    )


GREY = {'red': 0.6, 'green': 0.6, 'blue': 0.6}
BLACK = {'red': 0, 'green': 0, 'blue': 0}


def _make_style_request(sheet_id, row, end_col_index, drafted=True):
    """Build a single repeatCell request dict for batchUpdate."""
    color = GREY if drafted else BLACK
    return {
        'repeatCell': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': row - 1,
                'endRowIndex': row,
                'startColumnIndex': 0,
                'endColumnIndex': end_col_index,
            },
            'cell': {
                'userEnteredFormat': {
                    'textFormat': {
                        'strikethrough': drafted,
                        'foregroundColorStyle': {'rgbColor': color},
                    },
                }
            },
            'fields': 'userEnteredFormat.textFormat(strikethrough,foregroundColorStyle)',
        }
    }


def set_row_drafted_style(tab_name, row, end_col_index, drafted=True):
    """Set or remove strikethrough + grey text on a single row (unbatched)."""
    sheet_id = get_sheet_id(tab_name)
    if sheet_id is None:
        return
    _run_gws(
        'sheets', 'spreadsheets', 'batchUpdate',
        '--params', json.dumps({'spreadsheetId': SPREADSHEET_ID}),
        '--json', json.dumps({'requests': [
            _make_style_request(sheet_id, row, end_col_index, drafted)
        ]}),
    )


def flush_batch(value_updates, format_requests):
    """Send ALL pending value writes and format requests in a single API call."""
    requests = format_requests[:]
    for vu in value_updates:
        requests.append(vu)

    if not requests:
        return

    result = _run_gws(
        'sheets', 'spreadsheets', 'batchUpdate',
        '--params', json.dumps({'spreadsheetId': SPREADSHEET_ID}),
        '--json', json.dumps({'requests': requests}),
    )
    if result.returncode != 0:
        stderr = [l for l in result.stderr.splitlines() if 'keyring' not in l.lower()]
        if stderr:
            print(f'  Sheet batch error: {" ".join(stderr)}')


def run_test(lg, name_to_row, col_info):
    """Validate the full pipeline without a live draft."""
    print('\n=== Test Mode ===\n')

    # 1. League & teams
    teams = lg.teams()
    team_names = {key: info['name'] for key, info in teams.items()}
    print(f'League has {len(team_names)} teams:')
    for tname in team_names.values():
        print(f'  {tname}')

    # 2. Draft status
    settings = lg.settings()
    print(f'\nDraft status: {settings.get("draft_status", "unknown")}')

    results = lg.draft_results()
    print(f'Draft results so far: {len(results)} picks')

    # 3. Cheatsheet stats
    for tab, lookup in name_to_row.items():
        unique_rows = len(set(lookup.values()))
        print(f'\n{tab} tab: {unique_rows} players loaded')

    # 4. Test sheet write with 4 players, then cleanup
    test_players = [
        ('Shohei Ohtani (Batter)', 'Hitters'),
        ('Shohei Ohtani (Pitcher)', 'Pitchers'),
        ('Aaron Judge', 'Hitters'),
        ('Tarik Skubal', 'Pitchers'),
        ('José Ramírez', 'Hitters'),          # accent: é, í
        ('Ronald Acuña Jr.', 'Hitters'),       # accent: ñ + Jr. suffix
        ('Cristopher Sánchez', 'Pitchers'),    # accent: á
        ('Eury Pérez', 'Pitchers'),            # accent: é
    ]
    test_team = list(team_names.values())[0]

    print('\nWriting test picks...')
    for i, (name, expected_tab) in enumerate(test_players):
        pick_label = f'0.{i + 1:02d}'
        matched = mark_player_on_sheet(name, f'[TEST] {test_team}', pick_label, name_to_row, col_info)
        status = 'OK' if matched else 'NOT FOUND'
        print(f'  {name} -> {expected_tab}: {status}')

    print(f'\nCheck the sheet -- you should see {len(test_players)} test picks with strikethrough.')
    input('Press Enter to clear all test data...')

    for name, _ in test_players:
        norm = normalize_name(name)
        for tab, lookup in name_to_row.items():
            row = lookup.get(name) or lookup.get(norm)
            if row:
                dcol = col_info[tab]
                drafted_col_idx = ord(dcol) - ord('A')
                pcol = col_letter(drafted_col_idx + 1)
                sheet_clear_cells(tab, f'{dcol}{row}:{pcol}{row}')
                set_row_drafted_style(tab, row, drafted_col_idx, drafted=False)
    print('Test data cleared.')

    print('\n=== All checks passed. Ready for draft day! ===\n')


def run_tracker(lg, name_to_row, col_info):
    teams = lg.teams()
    team_names = {key: info['name'] for key, info in teams.items()}
    num_teams = len(team_names)

    print(f'\nLeague has {num_teams} teams:')
    for tkey, tname in team_names.items():
        print(f'  {tname}')

    seen_picks = set()
    unmatched = []
    total_tracked = 0

    print(f'\nPolling for draft picks every {POLL_INTERVAL}s  (Ctrl+C to stop)\n')

    try:
        while True:
            try:
                results = lg.draft_results()
            except Exception as e:
                print(f'  API error: {e}, retrying in {POLL_INTERVAL}s...')
                time.sleep(POLL_INTERVAL)
                continue

            new_picks = [p for p in results if p['pick'] not in seen_picks]

            if new_picks:
                new_player_ids = [p['player_id'] for p in new_picks]
                id_to_name = {}
                for i in range(0, len(new_player_ids), 20):
                    chunk = new_player_ids[i:i + 20]
                    try:
                        details = lg.player_details(chunk)
                        for d in details:
                            id_to_name[int(d['player_id'])] = d['name']['full']
                    except Exception as e:
                        print(f'  Error fetching player details (chunk {i}): {e}')

                value_updates = []
                format_requests = []

                for pick in new_picks:
                    pick_num = pick['pick']
                    player_id = pick['player_id']
                    team_key = pick['team_key']
                    rnd = pick.get('round', '?')

                    player_name = id_to_name.get(player_id, f'Player #{player_id}')
                    team_name = team_names.get(team_key, team_key)
                    pick_label = format_pick(pick_num, num_teams)

                    matched = collect_player_updates(
                        player_name, team_name, pick_label, name_to_row, col_info,
                        value_updates, format_requests,
                    )

                    status = '' if matched else '  [NOT ON SHEET]'
                    print(f'  Pick {pick_label} (Rd {rnd}): {player_name} -> {team_name}{status}')

                    if not matched:
                        unmatched.append((pick_label, player_name, team_name))

                    seen_picks.add(pick_num)
                    total_tracked += 1

                flush_batch(value_updates, format_requests)
                print(f'  (flushed {len(value_updates)} sheet updates)')

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print('\n\n=== Draft Tracker Stopped ===')
        print(f'Total picks tracked: {total_tracked}')
        if unmatched:
            print(f'\nUnmatched players ({len(unmatched)}):')
            for pick_label, pname, tname in unmatched:
                print(f'  Pick {pick_label}: {pname} -> {tname}')
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Yahoo Fantasy Draft Tracker')
    parser.add_argument('--setup', action='store_true', help='Set up OAuth2 credentials')
    parser.add_argument('--test', action='store_true', help='Test the full pipeline without a live draft')
    parser.add_argument('--league-id', type=str, default=None, help='Yahoo league ID (auto-discovered if omitted)')
    args = parser.parse_args()

    if args.setup:
        setup_oauth()
        return

    oauth = get_oauth()
    lg = discover_league(oauth, args.league_id)

    name_to_row, _ = load_cheatsheets()
    tabs_to_track = list(name_to_row.keys())

    if not tabs_to_track:
        print('Error: no cheatsheet CSVs found. Run the cheatsheet scripts first.')
        sys.exit(1)

    print('\nPreparing spreadsheet columns...')
    col_info = setup_sheet_columns(tabs_to_track)

    if args.test:
        run_test(lg, name_to_row, col_info)
    else:
        run_tracker(lg, name_to_row, col_info)


if __name__ == '__main__':
    main()
