"""Yahoo Fantasy API client helpers.

Lives in its own module so both update_ownership.py (which writes the
Status column into the cheatsheet) and pitcher_cheatsheet.py (which uses
ownership data to filter the Pitchers tab) can reuse the same OAuth
loading + paginated player-fetch logic.

The functions here only know about Yahoo. Player-name normalization
(used to match Yahoo names against projection / sheet names) lives
alongside the consumers so this module stays focused on API concerns.
"""

import base64
import json
import os
import tempfile

from yahoo_oauth import OAuth2

YAHOO_API_BASE = 'https://fantasysports.yahooapis.com/fantasy/v2'
PAGE_SIZE = 25
STATUS_TAKEN = 'T'
STATUS_WAIVERS = 'W'
STATUS_FREEAGENT = 'FA'


class YahooAuthError(RuntimeError):
    """Raised when Yahoo OAuth credentials are missing or unusable.

    Callers that want to gracefully degrade (e.g. pitcher_cheatsheet)
    should catch this and fall back; CLI entry points should report it
    and exit non-zero.
    """


def load_oauth():
    """Load Yahoo OAuth2 credentials, preferring YAHOO_OAUTH_JSON_B64.

    Falls back to ``oauth2.json`` next to this module. Raises
    :class:`YahooAuthError` if no credentials can be located or the
    base64 blob is malformed.
    """
    encoded = os.environ.get('YAHOO_OAUTH_JSON_B64')
    if encoded:
        try:
            decoded = base64.b64decode(encoded).decode('utf-8')
            json.loads(decoded)
        except Exception as e:
            raise YahooAuthError(f"YAHOO_OAUTH_JSON_B64 is malformed: {e}") from e

        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, prefix='yahoo_oauth_'
        )
        tmp.write(decoded)
        tmp.close()
        return OAuth2(None, None, from_file=tmp.name)

    local_path = os.path.join(os.path.dirname(__file__) or '.', 'oauth2.json')
    if os.path.exists(local_path):
        return OAuth2(None, None, from_file=local_path)

    raise YahooAuthError(
        "Yahoo OAuth credentials not found. Set YAHOO_OAUTH_JSON_B64 "
        "or place oauth2.json next to yahoo_client.py."
    )


def yahoo_get(oauth, url):
    """GET against the Yahoo API, refreshing the access token if needed."""
    if not oauth.token_is_valid():
        oauth.refresh_access_token()
    return oauth.session.get(url, params={'format': 'json'})


def fetch_my_team_name(oauth, league_key):
    """Return the current user's team name in this league, or '' if it
    can't be determined."""
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
    """Pull player metadata out of a Yahoo player array as returned by
    /league/.../players.

    Returns a dict with: name, player_id, owner_team, waiver_date, status,
    status_full. ``status`` is the short Yahoo roster-status code
    (e.g. "IL10", "IL15", "IL60", "NA", "DTD", "O", "SUSP") and is
    empty for healthy/active players. ``status_full`` is the
    human-readable form (e.g. "15-Day IL").
    """
    info_array = player_array[0]
    name, player_id, owner_team, waiver_date = '', '', '', ''
    status, status_full = '', ''
    for item in info_array:
        if not isinstance(item, dict):
            continue
        if 'name' in item:
            full = item['name'].get('full', '') if isinstance(item['name'], dict) else ''
            name = full or name
        if 'player_id' in item:
            player_id = str(item['player_id'])
        if 'status' in item and isinstance(item['status'], str):
            status = item['status'] or status
        if 'status_full' in item and isinstance(item['status_full'], str):
            status_full = item['status_full'] or status_full
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
        'status': status,
        'status_full': status_full,
    }


def fetch_players(oauth, league_key, status):
    """Paginated fetch of all players in the league with the given Yahoo
    ownership status (e.g. :data:`STATUS_TAKEN`, :data:`STATUS_WAIVERS`).

    Returns a list of dicts as produced by :func:`parse_player`.
    """
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
