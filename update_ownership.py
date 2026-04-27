#!/usr/bin/env python3
"""
update_ownership.py

Refreshes the Status column in the cheatsheet's Hitters and Pitchers tabs
based on Yahoo Fantasy ownership data. Replaces the Apps Script doGet
webhook that ran from GitHub Actions and kept hitting the undocumented
Apps Script "Bandwidth quota exceeded" limit.

Usage:
    python update_ownership.py [--league-key 469.l.12345]

Env vars (preferred over local files when set):
    YAHOO_OAUTH_JSON_B64        base64-encoded oauth2.json (yahoo_oauth format)
    YAHOO_LEAGUE_KEY            Yahoo league key (e.g. "469.l.94637")
    GOOGLE_SERVICE_ACCOUNT_KEY  service account JSON for Sheets API (read by
                                upload_to_sheets.get_sheets_service())

Falls back to local oauth2.json + service-account.json when env vars unset.
"""

import argparse
import base64
import json
import os
import re
import sys
import tempfile
import unicodedata

from yahoo_oauth import OAuth2

from upload_to_sheets import SPREADSHEET_ID, get_sheets_service

YAHOO_API_BASE = 'https://fantasysports.yahooapis.com/fantasy/v2'
TAB_NAMES = ['Hitters', 'Pitchers']
PAGE_SIZE = 25
STATUS_TAKEN = 'T'
STATUS_WAIVERS = 'W'
STATUS_HEADER = 'Status'
PLAYER_HEADER = 'Player'

CF_BG_MY_TEAM = '#c9daf8'
CF_BG_FA = '#d9ead3'
CF_BG_WAIVERS = '#fce5cd'
CF_FG_ROSTERED = '#999999'


def normalize_name(name):
    """Mirror normalize_name in upload_to_sheets.py / batter_cheatsheet.py.

    Duplicated intentionally to keep update_ownership.py free of operational
    coupling on upload_to_sheets.py beyond the SPREADSHEET_ID/service helpers.
    """
    if not isinstance(name, str):
        return ''
    name = name.lower()
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    name = re.sub(r'\s+(jr\.?|sr\.?|[ivx]+)$', '', name)
    name = re.sub(r'\s+\([^)]+\)', '', name)
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def col_letter(index):
    """0-based column index -> spreadsheet column letter (A, B, ..., AA, ...)."""
    letters = ''
    n = index
    while True:
        letters = chr(ord('A') + n % 26) + letters
        n = n // 26 - 1
        if n < 0:
            return letters


def hex_to_rgb_dict(hex_str):
    h = hex_str.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return {'red': r, 'green': g, 'blue': b}


# ---------------------------------------------------------------------------
# Yahoo OAuth + API
# ---------------------------------------------------------------------------

def load_oauth():
    """Load Yahoo OAuth2 credentials, preferring YAHOO_OAUTH_JSON_B64."""
    encoded = os.environ.get('YAHOO_OAUTH_JSON_B64')
    if encoded:
        try:
            decoded = base64.b64decode(encoded).decode('utf-8')
            json.loads(decoded)
        except Exception as e:
            print(f"ERROR: YAHOO_OAUTH_JSON_B64 is malformed: {e}", file=sys.stderr)
            sys.exit(2)

        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, prefix='yahoo_oauth_'
        )
        tmp.write(decoded)
        tmp.close()
        return OAuth2(None, None, from_file=tmp.name)

    local_path = os.path.join(os.path.dirname(__file__) or '.', 'oauth2.json')
    if os.path.exists(local_path):
        return OAuth2(None, None, from_file=local_path)

    print(
        "ERROR: Yahoo OAuth credentials not found. Set YAHOO_OAUTH_JSON_B64 "
        "or place oauth2.json next to this script.",
        file=sys.stderr,
    )
    sys.exit(2)


def get_league_key(args):
    if args.league_key:
        return args.league_key.strip()
    env = os.environ.get('YAHOO_LEAGUE_KEY')
    if env:
        return env.strip()
    print(
        "ERROR: Yahoo league key not configured. Set YAHOO_LEAGUE_KEY env var "
        "or pass --league-key.",
        file=sys.stderr,
    )
    sys.exit(2)


def yahoo_get(oauth, url):
    """GET against the Yahoo API, refreshing the access token if needed."""
    if not oauth.token_is_valid():
        oauth.refresh_access_token()
    return oauth.session.get(url, params={'format': 'json'})


def fetch_my_team_name(oauth, league_key):
    url = f'{YAHOO_API_BASE}/league/{league_key}/teams'
    r = yahoo_get(oauth, url)
    if r.status_code != 200:
        print(f"  Warning: /teams returned HTTP {r.status_code}; my-team detection skipped.")
        return ''
    try:
        league = r.json()['fantasy_content']['league']
        teams_obj = league[1]['teams']
        count = int(teams_obj.get('count', 0))
    except (KeyError, IndexError, TypeError, ValueError) as e:
        print(f"  Warning: unexpected /teams response shape: {e}")
        return ''

    for i in range(count):
        team_entry = teams_obj.get(str(i), {}).get('team')
        if not team_entry:
            continue
        info = team_entry[0]
        team_name = ''
        is_owned = False
        for item in info:
            if not isinstance(item, dict):
                continue
            if 'name' in item:
                team_name = item['name']
            if 'is_owned_by_current_login' in item:
                is_owned = str(item['is_owned_by_current_login']) == '1'
        if is_owned:
            return team_name
    return ''


def parse_player(player_array):
    info_array = player_array[0]
    name, player_id, owner_team, waiver_date = '', '', '', ''
    for item in info_array:
        if not isinstance(item, dict):
            continue
        if 'name' in item:
            full = item['name'].get('full', '') if isinstance(item['name'], dict) else ''
            name = full or name
        if 'player_id' in item:
            player_id = str(item['player_id'])
        if 'ownership' in item and isinstance(item['ownership'], dict):
            ownership = item['ownership']
            owner_team = owner_team or ownership.get('owner_team_name', '')
            waiver_date = waiver_date or ownership.get('waiver_date', '')
    if len(player_array) > 1 and isinstance(player_array[1], dict):
        ownership = player_array[1].get('ownership')
        if isinstance(ownership, dict):
            owner_team = owner_team or ownership.get('owner_team_name', '')
            waiver_date = waiver_date or ownership.get('waiver_date', '')
    if not name:
        return None
    return {
        'name': name,
        'player_id': player_id,
        'owner_team': owner_team,
        'waiver_date': waiver_date,
    }


def fetch_players(oauth, league_key, status):
    """Paginated fetch of all players with a given Yahoo ownership status."""
    out = []
    start = 0
    pages = 0
    while True:
        url = (
            f'{YAHOO_API_BASE}/league/{league_key}/players'
            f';status={status};start={start};count={PAGE_SIZE}'
            f';out=ownership'
        )
        r = yahoo_get(oauth, url)
        if r.status_code == 400 and start > 0:
            break
        if r.status_code != 200:
            print(
                f"  Yahoo API error (HTTP {r.status_code}) at start={start}: "
                f"{r.text[:300]}"
            )
            break
        try:
            data = r.json()
            league = data['fantasy_content']['league']
            players_obj = league[1].get('players')
        except (KeyError, IndexError, ValueError) as e:
            print(f"  Warning: failed to parse players response at start={start}: {e}")
            break

        if not players_obj:
            break
        try:
            count = int(players_obj.get('count', 0))
        except (TypeError, ValueError):
            count = 0
        if count == 0:
            break

        for i in range(count):
            entry = players_obj.get(str(i))
            if not entry or 'player' not in entry:
                continue
            parsed = parse_player(entry['player'])
            if parsed:
                out.append(parsed)

        pages += 1
        start += PAGE_SIZE
        if count < PAGE_SIZE:
            break

    print(f"  Fetched status={status}: {len(out)} players across {pages} page(s)")
    return out


# ---------------------------------------------------------------------------
# Sheet writes
# ---------------------------------------------------------------------------

def get_tab_metadata(svc, tab_name):
    """Return (sheet_id, header_row, num_rows, num_cols)."""
    meta = svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheet_id = None
    num_rows, num_cols = 0, 0
    for sheet in meta.get('sheets', []):
        if sheet['properties']['title'] == tab_name:
            sheet_id = sheet['properties']['sheetId']
            grid = sheet['properties'].get('gridProperties', {})
            num_rows = grid.get('rowCount', 0)
            num_cols = grid.get('columnCount', 0)
            break
    if sheet_id is None:
        return None, [], 0, 0

    values_resp = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f'{tab_name}!1:1',
    ).execute()
    rows = values_resp.get('values', [])
    header = rows[0] if rows else []
    return sheet_id, header, num_rows, num_cols


def read_player_column(svc, tab_name, player_col_letter):
    resp = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f'{tab_name}!{player_col_letter}2:{player_col_letter}',
    ).execute()
    rows = resp.get('values', [])
    return [row[0] if row else '' for row in rows]


def ensure_status_column(svc, tab_name, sheet_id, header):
    """Insert a Status column right after Player if missing.

    Returns (new_header, status_col_idx, inserted_bool).
    """
    if PLAYER_HEADER not in header:
        raise RuntimeError(f"{tab_name}: no Player column found")
    if STATUS_HEADER in header:
        return header, header.index(STATUS_HEADER), False

    player_idx = header.index(PLAYER_HEADER)
    insert_idx = player_idx + 1

    svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={'requests': [{
            'insertDimension': {
                'range': {
                    'sheetId': sheet_id,
                    'dimension': 'COLUMNS',
                    'startIndex': insert_idx,
                    'endIndex': insert_idx + 1,
                },
                'inheritFromBefore': False,
            }
        }]},
    ).execute()

    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f'{tab_name}!{col_letter(insert_idx)}1',
        valueInputOption='RAW',
        body={'values': [[STATUS_HEADER]]},
    ).execute()

    new_header = header[:insert_idx] + [STATUS_HEADER] + header[insert_idx:]
    return new_header, insert_idx, True


def compute_status(player_name, taken_map, waiver_map, my_team):
    norm = normalize_name(player_name)
    if not norm:
        return ''
    owner = taken_map.get(norm)
    if owner:
        return 'My Team' if my_team and owner == my_team else owner
    waiver = waiver_map.get(norm)
    if waiver:
        if isinstance(waiver, str) and waiver:
            try:
                _, m, d = waiver.split('-')
                return f'Waivers ({int(m)}/{int(d)})'
            except ValueError:
                return 'Waivers'
        return 'Waivers'
    if player_name:
        return 'FA'
    return ''


def write_status_column(svc, tab_name, status_col_idx, statuses):
    if not statuses:
        return
    letter = col_letter(status_col_idx)
    range_a1 = f'{tab_name}!{letter}2:{letter}{1 + len(statuses)}'
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=range_a1,
        valueInputOption='RAW',
        body={'values': [[s] for s in statuses]},
    ).execute()


def replace_conditional_formatting(svc, tab_name, sheet_id, status_col_idx,
                                   num_rows, num_cols):
    """Delete this tab's conditional format rules and replace with the standard 4.

    Idempotent: rules don't accumulate across runs.
    """
    cf_resp = svc.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        fields='sheets(properties(sheetId,title),conditionalFormats)',
    ).execute()

    requests_payload = []
    for sheet in cf_resp.get('sheets', []):
        if sheet['properties']['sheetId'] != sheet_id:
            continue
        existing = sheet.get('conditionalFormats', [])
        for _ in existing:
            requests_payload.append({
                'deleteConditionalFormatRule': {
                    'sheetId': sheet_id,
                    'index': 0,
                }
            })

    sl = col_letter(status_col_idx)
    full_range = {
        'sheetId': sheet_id,
        'startRowIndex': 1,
        'endRowIndex': max(num_rows, 2),
        'startColumnIndex': 0,
        'endColumnIndex': max(num_cols, status_col_idx + 1),
    }

    def add_rule(formula, *, background=None, font_color=None):
        rule = {
            'ranges': [full_range],
            'booleanRule': {
                'condition': {
                    'type': 'CUSTOM_FORMULA',
                    'values': [{'userEnteredValue': formula}],
                },
                'format': {},
            },
        }
        if background is not None:
            rule['booleanRule']['format']['backgroundColor'] = hex_to_rgb_dict(background)
        if font_color is not None:
            rule['booleanRule']['format']['textFormat'] = {
                'foregroundColor': hex_to_rgb_dict(font_color),
            }
        return {'addConditionalFormatRule': {'rule': rule, 'index': 0}}

    requests_payload.append(add_rule(f'=${sl}2="My Team"', background=CF_BG_MY_TEAM))
    requests_payload.append(add_rule(f'=${sl}2="FA"', background=CF_BG_FA))
    requests_payload.append(add_rule(f'=LEFT(${sl}2,7)="Waivers"', background=CF_BG_WAIVERS))
    requests_payload.append(
        add_rule(
            f'=AND(LEN(${sl}2)>0,${sl}2<>"FA",LEFT(${sl}2,7)<>"Waivers",${sl}2<>"My Team")',
            font_color=CF_FG_ROSTERED,
        )
    )

    if not requests_payload:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={'requests': requests_payload},
    ).execute()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def update_tab(svc, tab_name, taken_map, waiver_map, my_team):
    sheet_id, header, num_rows, num_cols = get_tab_metadata(svc, tab_name)
    if sheet_id is None:
        print(f"  {tab_name}: tab not found, skipping.")
        return False
    if PLAYER_HEADER not in header:
        print(f"  {tab_name}: no Player column found, skipping.")
        return False

    header, status_col_idx, inserted = ensure_status_column(
        svc, tab_name, sheet_id, header
    )
    if inserted:
        _, _, num_rows, num_cols = get_tab_metadata(svc, tab_name)

    player_idx = header.index(PLAYER_HEADER)
    player_names = read_player_column(svc, tab_name, col_letter(player_idx))

    statuses = []
    matched = 0
    for name in player_names:
        s = compute_status(str(name), taken_map, waiver_map, my_team)
        if s:
            matched += 1
        statuses.append(s)

    write_status_column(svc, tab_name, status_col_idx, statuses)
    replace_conditional_formatting(
        svc, tab_name, sheet_id, status_col_idx, num_rows, num_cols
    )
    print(f"  {tab_name}: {matched}/{len(statuses)} players tagged.")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    parser.add_argument('--league-key', help='Yahoo league key (e.g. 469.l.94637)')
    args = parser.parse_args()

    league_key = get_league_key(args)
    print(f"Updating ownership status for league {league_key}")

    oauth = load_oauth()
    if not oauth.token_is_valid():
        try:
            oauth.refresh_access_token()
        except Exception as e:
            print(
                f"ERROR: Yahoo OAuth refresh failed: {e}\n"
                f"Rotate YAHOO_OAUTH_JSON_B64 by running "
                f"`python draft_tracker.py --setup` locally and re-uploading.",
                file=sys.stderr,
            )
            return 1

    my_team = fetch_my_team_name(oauth, league_key)
    print(f"  My team: {my_team or '(unknown)'}")

    taken = fetch_players(oauth, league_key, STATUS_TAKEN)
    waivers = fetch_players(oauth, league_key, STATUS_WAIVERS)

    taken_map = {
        normalize_name(p['name']): (p['owner_team'] or 'Rostered')
        for p in taken if p['name']
    }
    waiver_map = {
        normalize_name(p['name']): (p['waiver_date'] or True)
        for p in waivers if p['name']
    }

    svc = get_sheets_service()
    all_ok = True
    for tab in TAB_NAMES:
        try:
            ok = update_tab(svc, tab, taken_map, waiver_map, my_team)
            all_ok = all_ok and ok
        except Exception as e:
            print(f"  ERROR updating {tab}: {e}")
            all_ok = False

    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
