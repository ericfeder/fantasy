import pandas as pd
import requests
import os
import re
import unicodedata
from datetime import date, timedelta
from collections import defaultdict


PROJECTION_DIR = 'data/2026/projections'
OUTPUT_DIR = 'data/output'
ENO_CACHE_PATH = 'data/2026/eno_pitch_report.csv'
PL_CACHE_PATH = 'data/2026/pitcherlist_top100.csv'
PL_INJURED_CACHE_PATH = 'data/2026/pitcherlist_injured.csv'
# Nick Pollack's weekly top-100 SP list (active rotation only; IL arms omitted).
PL_RANKINGS_URL = (
    'https://pitcherlist.com/top-100-starting-pitchers-for-2026-fantasy-baseball-'
    '5-26-week-10-rankings/'
)

SOURCES = ['thebatx', 'oopsy']

# Eno Sarris "Injured pitchers w/ approx. returns" table (May 15, 2026 update).
# (name, injury, return_eta, projected_rank_when_back)
INJURED_PITCHERS = [
    ("Grayson Rodriguez",     "Shoulder",        "> 1 wks",  55),
    ("Joe Boyle",             "Elbow Strain",    "> 1 wks",  65),
    ("Garrett Crochet",       "Shoulder",        "> 2 wks",  5),
    ("Tyler Glasnow",         "Back",            "> 2 wks",  15),
    ("Logan Webb",            "Knee",            "> 2 wks",  20),
    ("Gerrit Cole",           "Tommy John",      "> 2 wks",  35),
    ("Brandon Woodruff",      "Shoulder Inf.",   "> 2 wks",  40),
    ("Jared Jones",           "Tommy John",      "> 2 wks",  45),
    ("Taj Bradley",           "Pectoral",        "> 2 wks",  50),
    ("Kodai Senga",           "Back",            "> 2 wks",  60),
    ("Casey Mize",            "Adductor",        "> 2 wks",  65),
    ("Steven Matz",           "Elbow",           "> 2 wks",  85),
    ("Cole Ragans",           "Elbow",           "> 3 wks",  20),
    ("José Berríos",          "Elbow",           "> 3 wks",  90),
    ("Justin Verlander",      "Hip",             "> 3 wks",  105),
    ("Nick Pivetta",          "Elbow?",          "> 4 wks",  30),
    ("Shane Bieber",          "Elbow",           "> 4 wks",  55),
    ("Mick Abel",             "Elbow",           "> 4 wks",  60),
    ("Cade Povich",           "Shoulder",        "> 4 wks",  80),
    ("Yusei Kikuchi",         "Shoulder",        "> 4 wks",  90),
    ("Dean Kremer",           "Quad",            "> 4 wks",  105),
    ("Hunter Brown",          "Shoulder Strain", "> 5 wks",  20),
    ("Patrick Sandoval",      "Tommy John",      "> 5 wks",  110),
    ("Tarik Skubal",          "Elbow",           "> 6 wks",  5),
    ("Hunter Greene",         "Elbow Surgery",   "> 6 wks",  25),
    ("Joe Musgrove",          "Tommy John",      "> 6 wks",  55),
    ("Matthew Boyd",          "Knee",            "> 6 wks",  60),
    ("Robby Snelling",        "Elbow",           "> 6 wks",  65),
    ("Max Scherzer",          "Forearm/Thumb",   "> 6 wks",  75),
    ("Troy Melton",           "Elbow",           "> 6 wks",  80),
    ("Cristian Javier",       "Shoulder Strain", "> 7 wks",  125),
    ("Spencer Schwellenbach", "Elbow Surgery",   "> 8 wks",  25),
    ("Corbin Burnes",         "Tommy John",      "> 8 wks",  45),
    ("Justin Steele",         "Tommy John",      "> 8 wks",  50),
    ("Hurston Waldrep",       "Elbow Surgery",   "> 8 wks",  90),
    ("Johan Oviedo",          "Flexor Strain",   "> 8 wks",  100),
    ("Quinn Priester",        "Wrist",           "> 8 wks",  125),
]

# Eno Sarris "Select prospect pitchers" table (May 15, 2026 update).
# (name, aaa_stuff_plus_or_None, rank_if_called_up)
PROSPECT_PITCHERS = [
    ("Ryan Sloan",       None, 50),
    ("River Ryan",       110,  55),
    ("Kade Anderson",    None, 55),
    ("Carlos Lagrange",  108,  60),
    ("Hagen Smith",      104,  70),
    ("Tanner McDougal",  95,   70),
    ("Robert Gasser",    104,  75),
    ("Quinn Mathews",    99,   75),
    ("Jonah Tong",       109,  80),
    ("Thomas White",     95,   85),
    ("Jack Wenniger",    98,   85),
    ("Gage Jump",        99,   90),
    ("Brody Hopkins",    99,   90),
]


def _normalize_pitcher_name(name):
    """Lowercase, strip accents, suffixes, and punctuation for matching."""
    if not isinstance(name, str):
        return ''
    s = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8').lower()
    s = re.sub(r'\s+(jr\.?|sr\.?|ii|iii|iv)$', '', s)
    s = re.sub(r'[^\w\s]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def apply_injured_and_prospects(merged):
    """Fill eno_rank + eno_note for injured/prospect pitchers from the Eno
    article, appending new rows for any names not already present."""
    if 'eno_note' not in merged.columns:
        merged['eno_note'] = ''
    if 'eno_rank' not in merged.columns:
        merged['eno_rank'] = pd.NA

    name_to_idx = {}
    for i, name in enumerate(merged['PlayerName']):
        key = _normalize_pitcher_name(name)
        if key and key not in name_to_idx:
            name_to_idx[key] = i

    new_rows = []

    def _set_or_append(name, rank, note):
        key = _normalize_pitcher_name(name)
        idx = name_to_idx.get(key)
        if idx is not None:
            merged.at[idx, 'eno_rank'] = rank
            merged.at[idx, 'eno_note'] = note
        else:
            new_rows.append({'PlayerName': name, 'eno_rank': rank, 'eno_note': note})

    for name, injury, eta, rank in INJURED_PITCHERS:
        note = f"Inj: {injury} ({eta})"
        _set_or_append(name, rank, note)

    for name, stuff, rank in PROSPECT_PITCHERS:
        note = (
            f"Prospect (AAA Stuff+ {stuff})" if stuff is not None else "Prospect"
        )
        _set_or_append(name, rank, note)

    if new_rows:
        merged = pd.concat([merged, pd.DataFrame(new_rows)], ignore_index=True)
        print(f"Appended {len(new_rows)} pitchers not found in projections")

    return merged

# Pitcher scoring: CG, SHO, NH are not projected by any system (too rare)
SCORING = {
    'IP': 2.25,
    'W': 4,
    'SV': 2,
    'H': -0.6,
    'ER': -2,
    'BB': -0.6,
    'HBP': -0.6,
    'SO': 2,       # K in scoring, SO in FanGraphs
    'HLD': 1,
}


def ensure_directories():
    for d in ['data', 'data/2026', PROJECTION_DIR, OUTPUT_DIR]:
        os.makedirs(d, exist_ok=True)


def load_pitching_projections(source):
    file_path = f"{PROJECTION_DIR}/{source}_pitching_projections.csv"
    if not os.path.exists(file_path):
        print(f"Warning: {file_path} does not exist")
        return None

    df = pd.read_csv(file_path)
    # Filter to pitchers with meaningful IP
    df = df[df['IP'] > 0]
    print(f"Loaded {len(df)} pitchers from {source}")
    return df


def calculate_fantasy_points(df):
    df['FantasyPoints'] = 0.0
    for stat, weight in SCORING.items():
        if stat in df.columns:
            df['FantasyPoints'] += df[stat].fillna(0) * weight
    return df


def _parse_pl_active_ranks(html):
    """Parse numbered top-100 entries from the PL article body."""
    by_rank = {}

    link_pat = re.compile(
        r'<strong>(\d+)\.\s*<a[^>]*href="[^"]*pitcherlist\.com/player/[^"]*"[^>]*>'
        r'([^<]+)</a>',
        re.I,
    )
    plain_pat = re.compile(
        r'<strong>(\d+)\.\s*([^<]+?)\s*\(([A-Z]{2,4})\)\s*(?:&#8211;|–|-)',
        re.I,
    )
    split_pat = re.compile(
        r'<strong>(\d+)\.\s*([^<]*)</strong><strong>([^<]+?)\s*\(([A-Z]{2,4})\)',
        re.I,
    )

    for m in link_pat.finditer(html):
        rank = int(m.group(1))
        if 1 <= rank <= 100:
            by_rank[rank] = m.group(2).strip()

    for m in plain_pat.finditer(html):
        rank = int(m.group(1))
        if 1 <= rank <= 100 and rank not in by_rank:
            by_rank[rank] = re.sub(r'\s+', ' ', m.group(2).strip())

    for m in split_pat.finditer(html):
        rank = int(m.group(1))
        if 1 <= rank <= 100 and rank not in by_rank:
            name = re.sub(r'\s+', ' ', (m.group(2) + m.group(3)).strip())
            by_rank[rank] = name

    return [
        {'pl_rank': rank, 'pl_name': name}
        for rank, name in sorted(by_rank.items())
    ]


def _parse_pl_injured_table(html):
    """Parse PL article table: Injured Pitchers Who Will Be Considered When Healthy."""
    marker = 'Injured Pitchers Who Will Be Considered When Healthy'
    start = html.find(marker)
    if start < 0:
        return []

    end_markers = (
        "Nick's Loose Minor League",
        'Nick&#8217;s Loose Minor League',
        'Treat it s a bonus table',
    )
    end = len(html)
    for m in end_markers:
        pos = html.find(m, start)
        if pos > start:
            end = min(end, pos)

    chunk = html[start:end]
    row_pat = re.compile(
        r'<tr>\s*<td><a class="player-tag"[^>]*>([^<]+)</a></td>\s*'
        r'<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*</tr>',
        re.I | re.S,
    )
    rows = []
    for name, injury, rank_range in row_pat.findall(chunk):
        name = name.strip()
        injury = injury.strip()
        rank_range = rank_range.strip()
        if name and rank_range:
            rows.append({
                'pl_name': name,
                'pl_injury': injury,
                'pl_rank_range': rank_range,
            })
    return rows


def fetch_pitcherlist_rankings(force_download=True):
    """Fetch Pitcher List top-100 SP ranks and IL relative-rank table."""
    os.makedirs(os.path.dirname(PL_CACHE_PATH), exist_ok=True)
    need_active = force_download or not os.path.exists(PL_CACHE_PATH)
    need_injured = force_download or not os.path.exists(PL_INJURED_CACHE_PATH)

    if need_active or need_injured:
        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
        }
        try:
            response = requests.get(PL_RANKINGS_URL, headers=headers, timeout=20)
            response.raise_for_status()
            html = response.text

            active_rows = _parse_pl_active_ranks(html)
            if len(active_rows) < 90:
                raise ValueError(f"only parsed {len(active_rows)} PL ranks from article")
            pd.DataFrame(active_rows).drop_duplicates(subset=['pl_rank']).to_csv(
                PL_CACHE_PATH, index=False
            )
            print(f"Downloaded Pitcher List top 100 to {PL_CACHE_PATH}")

            injured_rows = _parse_pl_injured_table(html)
            if len(injured_rows) < 10:
                raise ValueError(f"only parsed {len(injured_rows)} PL injured pitchers")
            pd.DataFrame(injured_rows).drop_duplicates(subset=['pl_name']).to_csv(
                PL_INJURED_CACHE_PATH, index=False
            )
            print(
                f"Downloaded {len(injured_rows)} Pitcher List injured pitchers "
                f"to {PL_INJURED_CACHE_PATH}"
            )
        except Exception as e:
            print(f"Error downloading Pitcher List rankings: {e}")
            if not os.path.exists(PL_CACHE_PATH) or not os.path.exists(PL_INJURED_CACHE_PATH):
                return None, None

    try:
        active = pd.read_csv(PL_CACHE_PATH)
        active['pl_rank'] = pd.to_numeric(active['pl_rank'], errors='coerce')
        active = active.dropna(subset=['pl_rank'])
        active['pl_rank'] = active['pl_rank'].astype(int)
        print(f"Loaded {len(active)} Pitcher List top-100 ranks")

        injured = pd.read_csv(PL_INJURED_CACHE_PATH)
        print(f"Loaded {len(injured)} Pitcher List injured pitchers")
        return active, injured
    except Exception as e:
        print(f"Error parsing Pitcher List rankings: {e}")
        return None, None


def merge_pitcherlist_rankings(merged, pl_active, pl_injured):
    """Attach ``pl_rank`` from the active top 100, then IL relative-rank ranges."""
    if 'pl_rank' not in merged.columns:
        merged['pl_rank'] = pd.NA

    if pl_active is not None and not pl_active.empty:
        pl = pl_active.copy()
        pl['norm_name'] = pl['pl_name'].map(_normalize_pitcher_name)
        pl_by_name = pl.drop_duplicates(subset=['norm_name']).set_index('norm_name')['pl_rank']
        merged['pl_rank'] = merged['PlayerName'].map(
            lambda n: pl_by_name.get(_normalize_pitcher_name(n), pd.NA)
        )
        matched = merged['pl_rank'].notna().sum()
        print(f"Matched {matched} pitchers to Pitcher List top 100")

    if pl_injured is not None and not pl_injured.empty:
        pl_inj = pl_injured.copy()
        pl_inj['norm_name'] = pl_inj['pl_name'].map(_normalize_pitcher_name)
        range_by_name = pl_inj.drop_duplicates(subset=['norm_name']).set_index('norm_name')[
            'pl_rank_range'
        ]
        filled = 0
        for i, name in enumerate(merged['PlayerName']):
            if pd.notna(merged.at[i, 'pl_rank']):
                continue
            key = _normalize_pitcher_name(name)
            if key in range_by_name.index:
                merged.at[i, 'pl_rank'] = range_by_name[key]
                filled += 1
        print(f"Filled PL # from injured table for {filled} pitchers")

    return merged


def _strip_pl_notes_from_eno_note(note):
    """Remove ``PL IL: ...`` fragments from Eno Note (PL # holds IL rank ranges)."""
    if not isinstance(note, str) or not note.strip():
        return ''
    parts = [p.strip() for p in note.split(';')]
    parts = [p for p in parts if p and not p.startswith('PL IL:')]
    return '; '.join(parts)


def apply_pl_injured(merged, pl_injured):
    """Append PL IL arms missing from projections; rank range goes in ``pl_rank`` only."""
    if pl_injured is None or pl_injured.empty:
        return merged

    if 'eno_note' not in merged.columns:
        merged['eno_note'] = ''
    if 'pl_rank' not in merged.columns:
        merged['pl_rank'] = pd.NA

    name_to_idx = {}
    for i, name in enumerate(merged['PlayerName']):
        key = _normalize_pitcher_name(name)
        if key and key not in name_to_idx:
            name_to_idx[key] = i

    new_rows = []
    for _, row in pl_injured.iterrows():
        name = row['pl_name']
        rank_range = row['pl_rank_range']
        key = _normalize_pitcher_name(name)
        idx = name_to_idx.get(key)
        if idx is not None:
            if pd.isna(merged.at[idx, 'pl_rank']):
                merged.at[idx, 'pl_rank'] = rank_range
            merged.at[idx, 'eno_note'] = _strip_pl_notes_from_eno_note(
                merged.at[idx, 'eno_note']
            )
        else:
            new_rows.append({
                'PlayerName': name,
                'pl_rank': rank_range,
                'eno_note': '',
            })

    if new_rows:
        merged = pd.concat([merged, pd.DataFrame(new_rows)], ignore_index=True)
        print(f"Appended {len(new_rows)} pitchers from Pitcher List injured table")

    return merged


def fetch_eno_rankings(force_download=True):
    """Fetch Eno Sarris Pitch Report 2026 from Google Sheets."""
    os.makedirs(os.path.dirname(ENO_CACHE_PATH), exist_ok=True)

    should_download = force_download or not os.path.exists(ENO_CACHE_PATH)

    if should_download:
        url = "https://docs.google.com/spreadsheets/d/1daR9RNic3GcfDb6FLsm2OZRBS8VkqucOqHSnIS7ru5c/export?format=csv&gid=781005216"
        try:
            response = requests.get(url)
            response.raise_for_status()
            with open(ENO_CACHE_PATH, 'w', encoding='utf-8') as f:
                f.write(response.text)
            print(f"Downloaded Eno Pitch Report to {ENO_CACHE_PATH}")
        except Exception as e:
            print(f"Error downloading Eno rankings: {e}")
            if not os.path.exists(ENO_CACHE_PATH):
                return None

    try:
        df = pd.read_csv(ENO_CACHE_PATH)
        print(f"Eno sheet columns: {df.columns.tolist()[:15]}...")
        print(f"Eno sheet rows: {len(df)}")

        col_map = {}
        for col in df.columns:
            col_lower = col.strip().lower()
            if col_lower == 'eno' or col_lower == '#':
                col_map['eno_rank'] = col
            elif col_lower == 'name':
                col_map['eno_name'] = col
            elif 'mlbam' in col_lower:
                col_map['mlbam_id'] = col
            elif col_lower == 'team':
                col_map['eno_team'] = col
            elif 'proj' in col_lower and 'ip' in col_lower:
                col_map['eno_proj_ip'] = col
            elif col_lower == 'ppera':
                col_map['eno_ppera'] = col
            elif col_lower in ('ppk%', 'ppk'):
                col_map['eno_ppk'] = col
            elif col_lower == 'stuff+':
                col_map['eno_stuff_plus'] = col
            elif col_lower == 'pitching+':
                col_map['eno_pitching_plus'] = col
            elif col_lower == 'health':
                col_map['eno_health'] = col

        print(f"Mapped Eno columns: {col_map}")

        rename = {v: k for k, v in col_map.items()}
        eno = df.rename(columns=rename)

        keep_cols = [c for c in col_map.keys() if c in eno.columns]
        eno = eno[keep_cols].copy()

        if 'eno_rank' in eno.columns:
            eno['eno_rank'] = pd.to_numeric(eno['eno_rank'], errors='coerce')
        if 'mlbam_id' in eno.columns:
            eno['mlbam_id'] = pd.to_numeric(eno['mlbam_id'], errors='coerce')

        if 'mlbam_id' in eno.columns:
            eno = eno.dropna(subset=['mlbam_id'])
            eno['mlbam_id'] = eno['mlbam_id'].astype(int)

        print(f"Parsed {len(eno)} Eno-ranked pitchers")
        return eno

    except Exception as e:
        print(f"Error parsing Eno rankings: {e}")
        import traceback
        traceback.print_exc()
        return None


def fetch_yahoo_ownership_keys():
    """Fetch sets of normalized names for Yahoo-rostered and waiver pitchers.

    Returns (taken_keys, waiver_keys), each a set of normalized names, or
    (None, None) if Yahoo data can't be retrieved (missing creds, network
    error, etc.). Callers should treat None as "ownership data unavailable"
    and skip the ownership-based criterion rather than treat every pitcher
    as a free agent.
    """
    try:
        from yahoo_client import (
            STATUS_TAKEN, STATUS_WAIVERS,
            YahooAuthError, fetch_players, load_oauth,
        )
        from update_ownership import normalize_name
    except Exception as e:
        print(f"Could not import Yahoo ownership helpers: {e}")
        return None, None

    league_key = os.environ.get('YAHOO_LEAGUE_KEY')
    if not league_key:
        print("YAHOO_LEAGUE_KEY not set; skipping ownership-based pitcher filter")
        return None, None

    try:
        oauth = load_oauth()
        if not oauth.token_is_valid():
            oauth.refresh_access_token()
        taken = fetch_players(oauth, league_key, STATUS_TAKEN)
        waivers = fetch_players(oauth, league_key, STATUS_WAIVERS)
    except YahooAuthError as e:
        print(f"{e}; skipping ownership-based pitcher filter")
        return None, None
    except Exception as e:
        print(f"Yahoo ownership fetch failed: {e}; skipping ownership-based pitcher filter")
        return None, None

    taken_keys = {normalize_name(p['name']) for p in taken if p.get('name')}
    waiver_keys = {normalize_name(p['name']) for p in waivers if p.get('name')}
    return taken_keys, waiver_keys


def filter_included_pitchers(merged, taken_keys, waiver_keys, pl_injured_keys=None):
    """Keep pitchers matching at least one of:

    1. Owned by a Yahoo team or on waivers
    2. Ranked by Eno (eno_rank present)
    3. On Pitcher List's injured-when-healthy table
    4. Projected to start at least max(projected GS) / 3 games RoS
    5. Probable starter in any game this fantasy week or next

    If both ``taken_keys`` and ``waiver_keys`` are None we couldn't reach
    Yahoo at all, so we skip the filter entirely rather than risk dropping
    legitimately rostered pitchers.
    """
    if taken_keys is None and waiver_keys is None:
        print("Skipping pitcher filter (no Yahoo ownership data)")
        return merged

    # Use the same normalization that built the Yahoo key sets so the
    # isin() lookup actually matches.
    from update_ownership import normalize_name as _yahoo_normalize_name

    starts_cols = [c for c in (f'{s}_starts' for s in SOURCES) if c in merged.columns]
    if starts_cols:
        max_starts_per_pitcher = merged[starts_cols].max(axis=1).fillna(0)
        league_max_gs = max_starts_per_pitcher.max()
        gs_threshold = league_max_gs / 3
    else:
        max_starts_per_pitcher = pd.Series(0, index=merged.index)
        league_max_gs = 0
        gs_threshold = float('inf')

    norm_names = merged['PlayerName'].apply(_yahoo_normalize_name)
    owned_or_waivers = norm_names.isin((taken_keys or set()) | (waiver_keys or set()))

    eno_ranked = (
        merged['eno_rank'].notna()
        if 'eno_rank' in merged.columns
        else pd.Series(False, index=merged.index)
    )

    pl_injured_listed = (
        norm_names.isin(pl_injured_keys or set())
        if pl_injured_keys
        else pd.Series(False, index=merged.index)
    )

    enough_starts = max_starts_per_pitcher >= gs_threshold

    week_cols = [c for c in ('starts_this_week', 'starts_next_week') if c in merged.columns]
    if week_cols:
        probable_this_or_next = merged[week_cols].apply(
            lambda col: col.fillna('').astype(str).str.strip().ne('')
        ).any(axis=1)
    else:
        probable_this_or_next = pd.Series(False, index=merged.index)

    keep = (
        owned_or_waivers | eno_ranked | pl_injured_listed
        | enough_starts | probable_this_or_next
    )

    print(
        f"Pitcher filter: {int(keep.sum())}/{len(merged)} kept "
        f"(owned/waivers={int(owned_or_waivers.sum())}, "
        f"eno_ranked={int(eno_ranked.sum())}, "
        f"pl_injured={int(pl_injured_listed.sum())}, "
        f"GS>={gs_threshold:.1f}={int(enough_starts.sum())}, "
        f"probable_this/next_wk={int(probable_this_or_next.sum())})"
    )

    return merged[keep].reset_index(drop=True)


def fetch_probable_starters():
    """Fetch probable starter grid from FanGraphs API.

    Returns {fg_player_id_str: [(date_obj, opp_abbrev, is_home), ...]}
    """
    from fangraphs_http import get_best_effort

    url = "https://www.fangraphs.com/api/roster-resource/probables-grid/data"
    try:
        resp = get_best_effort(
            url,
            timeout=15,
            headers={
                'Accept': 'application/json',
                'Referer': 'https://www.fangraphs.com/roster-resource/probables-grid',
            },
        )
        payload = resp.json()
    except Exception as e:
        print(f"Error fetching probable starters: {e}")
        return {}

    # As of May 2026, the FanGraphs API returns:
    #   {"games": [
    #       {"abbName": "LAA", "gameDate": "2026-05-02", "isHome": true,
    #        "team":     {"sp": {"playerId": "27468", ...}, ...},
    #        "opponent": {"abbName": "NYM", "sp": {"playerId": "33703", ...}, ...}},
    #       ...
    #   ]}
    # The API emits each matchup twice (once from each team's perspective), so we only
    # record the SP listed under "team" per record to avoid double-counting. Older flat
    # payloads (`teamSPPlayerId`/`OpponentAbbName`/`GameDate`) are also tolerated.
    if isinstance(payload, dict):
        records = payload.get('games', [])
    else:
        records = payload or []
    print(f"Fetched {len(records)} probable-starter games from FanGraphs")

    today = date.today()
    starters = defaultdict(list)
    for rec in records:
        if not isinstance(rec, dict):
            continue

        date_str = rec.get('gameDate') or rec.get('GameDate')
        if not date_str:
            continue
        try:
            game_date = date.fromisoformat(date_str[:10])
        except (TypeError, ValueError):
            continue
        if game_date < today:
            continue

        opponent = rec.get('opponent') or {}
        opp_abbr = opponent.get('abbName') or rec.get('OpponentAbbName') or '?'
        is_home = bool(rec.get('isHome'))

        pid = (
            ((rec.get('team') or {}).get('sp') or {}).get('playerId')
            or rec.get('teamSPPlayerId')
        )
        if not pid:
            continue
        starters[str(pid)].append((game_date, opp_abbr, is_home))

    for pid in starters:
        starters[pid].sort(key=lambda x: x[0])

    print(f"Parsed probable starters for {len(starters)} pitchers")
    return dict(starters)


def _format_matchup(opp, is_home):
    return f"vs {opp}" if is_home else f"@ {opp}"


DAY_ABBREV = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def add_schedule_columns(merged, starters):
    """Add the 5 probable-start columns to the merged DataFrame."""
    today = date.today()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)

    # This fantasy week: Monday through Sunday containing today
    days_since_monday = today.weekday()  # 0=Mon
    this_week_start = today - timedelta(days=days_since_monday)
    this_week_end = this_week_start + timedelta(days=6)

    next_week_start = this_week_end + timedelta(days=1)
    next_week_end = next_week_start + timedelta(days=6)

    col_today = []
    col_tomorrow = []
    col_day_after = []
    col_this_week = []
    col_next_week = []

    for _, row in merged.iterrows():
        raw_pid = row.get('playerid')
        if pd.notna(raw_pid):
            pid = str(int(raw_pid)) if isinstance(raw_pid, float) and raw_pid == int(raw_pid) else str(raw_pid)
        else:
            pid = ''
        starts = starters.get(pid, [])

        val_today = ''
        val_tomorrow = ''
        val_day_after = ''
        parts_this_week = []
        parts_next_week = []

        for game_date, opp, is_home in starts:
            matchup = _format_matchup(opp, is_home)
            if game_date == today:
                val_today = matchup
            if game_date == tomorrow:
                val_tomorrow = matchup
            if game_date == day_after:
                val_day_after = matchup
            if this_week_start <= game_date <= this_week_end:
                day_name = DAY_ABBREV[game_date.weekday()]
                parts_this_week.append(f"{day_name} {matchup}")
            if next_week_start <= game_date <= next_week_end:
                day_name = DAY_ABBREV[game_date.weekday()]
                parts_next_week.append(f"{day_name} {matchup}")

        col_today.append(val_today)
        col_tomorrow.append(val_tomorrow)
        col_day_after.append(val_day_after)
        col_this_week.append(', '.join(parts_this_week))
        col_next_week.append(', '.join(parts_next_week))

    merged['start_today'] = col_today
    merged['start_tomorrow'] = col_tomorrow
    merged['start_day_after'] = col_day_after
    merged['starts_this_week'] = col_this_week
    merged['starts_next_week'] = col_next_week
    return merged


def create_pitcher_cheatsheet():
    ensure_directories()

    projections = {}
    for source in SOURCES:
        df = load_pitching_projections(source)
        if df is not None:
            df = calculate_fantasy_points(df)
            df = df[['PlayerName', 'Team', 'xMLBAMID', 'playerid', 'G', 'GS', 'IP', 'FantasyPoints']].copy()
            df['FantasyPoints'] = df['FantasyPoints'].round().astype(int)
            df['IP'] = df['IP'].round().astype(int)
            df = df.rename(columns={
                'FantasyPoints': f'{source}_points',
                'G': f'{source}_games',
                'GS': f'{source}_starts',
                'IP': f'{source}_ip',
            })
            projections[source] = df

    if not projections:
        print("No projections available")
        return

    # Merge all sources
    merged = projections[SOURCES[0]]
    for source in SOURCES[1:]:
        if source in projections:
            merged = pd.merge(
                merged,
                projections[source],
                on=['PlayerName', 'Team', 'xMLBAMID', 'playerid'],
                how='outer'
            )

    # Fill NaN and convert to int
    point_cols = [f'{s}_points' for s in SOURCES if s in projections]
    ip_cols = [f'{s}_ip' for s in SOURCES if s in projections]
    games_cols = [f'{s}_games' for s in SOURCES if s in projections]
    starts_cols = [f'{s}_starts' for s in SOURCES if s in projections]

    for col in point_cols + ip_cols + games_cols + starts_cols:
        merged[col] = merged[col].fillna(0).round().astype(int)

    # Points per game and formatted games column for each source
    for source in SOURCES:
        pts_col = f'{source}_points'
        games_col = f'{source}_games'
        starts_col = f'{source}_starts'
        ppg_col = f'{source}_ppg'
        gf_col = f'{source}_g'
        if pts_col in merged.columns and games_col in merged.columns:
            merged[ppg_col] = 0.0
            valid = merged[games_col] > 0
            merged.loc[valid, ppg_col] = (
                merged.loc[valid, pts_col] / merged.loc[valid, games_col]
            ).round(1)
        if games_col in merged.columns and starts_col in merged.columns:
            merged[gf_col] = merged.apply(
                lambda r: f"{r[games_col]} ({r[starts_col]} GS)"
                if r[games_col] != r[starts_col]
                else str(r[games_col]),
                axis=1,
            )

    # Sort by THE BAT X points (primary sort)
    merged = merged.sort_values('thebatx_points', ascending=False).reset_index(drop=True)
    merged['points_rank'] = range(1, len(merged) + 1)

    # Fetch and merge Eno rankings
    eno = fetch_eno_rankings()
    if eno is not None and 'mlbam_id' in eno.columns:
        merged['xMLBAMID'] = pd.to_numeric(merged['xMLBAMID'], errors='coerce')
        merged = merged.merge(eno, left_on='xMLBAMID', right_on='mlbam_id', how='left')

        if 'eno_rank' in merged.columns:
            merged['rank_diff'] = merged['eno_rank'] - merged['points_rank']
        if 'mlbam_id' in merged.columns:
            merged = merged.drop(columns=['mlbam_id'])

    # Layer in injured + prospect pitchers from the Eno article (their
    # "expected ranks") and tag them with a note column.
    merged = apply_injured_and_prospects(merged)

    # Add probable starter schedule columns
    starters = fetch_probable_starters()
    merged = add_schedule_columns(merged, starters)

    pl_active, pl_injured = fetch_pitcherlist_rankings()
    merged = merge_pitcherlist_rankings(merged, pl_active, pl_injured)
    merged = apply_pl_injured(merged, pl_injured)

    pl_injured_keys = None
    if pl_injured is not None and not pl_injured.empty:
        pl_injured_keys = {
            _normalize_pitcher_name(n) for n in pl_injured['pl_name'] if isinstance(n, str)
        }

    # Apply inclusion filter: keep pitchers who are owned/on waivers, ranked
    # by Eno or PL IL table, projected to start a meaningful share of remaining
    # games, or have a probable start this/next fantasy week.
    taken_keys, waiver_keys = fetch_yahoo_ownership_keys()
    merged = filter_included_pitchers(
        merged, taken_keys, waiver_keys, pl_injured_keys=pl_injured_keys
    )

    # Build final column order
    out_cols = [
        'PlayerName',
        'start_today', 'start_tomorrow', 'start_day_after',
        'starts_this_week', 'starts_next_week',
        'oopsy_ppg', 'thebatx_g',
        'eno_rank', 'pl_rank', 'eno_note',
    ]
    out_cols = [c for c in out_cols if c in merged.columns]
    merged = merged[out_cols]

    # Sort by eno_rank (pitchers without an Eno rank go to the bottom)
    merged = merged.sort_values('eno_rank', ascending=True, na_position='last').reset_index(drop=True)

    # Compute week date ranges for column headers
    today = date.today()
    days_since_monday = today.weekday()
    this_week_start = today - timedelta(days=days_since_monday)
    this_week_end = this_week_start + timedelta(days=6)
    next_week_start = this_week_end + timedelta(days=1)
    next_week_end = next_week_start + timedelta(days=6)
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)
    today_label     = f"{today.strftime('%-m/%-d')} ({DAY_ABBREV[today.weekday()]})"
    tomorrow_label  = f"{tomorrow.strftime('%-m/%-d')} ({DAY_ABBREV[tomorrow.weekday()]})"
    day_after_label = f"{day_after.strftime('%-m/%-d')} ({DAY_ABBREV[day_after.weekday()]})"
    this_week_label = f"{this_week_start.strftime('%-m/%-d')}-{this_week_end.strftime('%-m/%-d')}"
    next_week_label = f"{next_week_start.strftime('%-m/%-d')}-{next_week_end.strftime('%-m/%-d')}"

    # Rename columns to human-friendly headers before saving
    merged = merged.rename(columns={
        'PlayerName':       'Player',
        'start_today':      today_label,
        'start_tomorrow':   tomorrow_label,
        'start_day_after':  day_after_label,
        'starts_this_week': this_week_label,
        'starts_next_week': next_week_label,
        'eno_rank':         'Eno #',
        'pl_rank':          'PL #',
        'eno_note':         'Eno Note',
        'thebatx_g':        'Proj. G',
        'oopsy_ppg':        'OOPSY',
    })

    output_file = f"{OUTPUT_DIR}/pitcher_cheatsheet.csv"
    merged.to_csv(output_file, index=False)
    print(f"\nSaved pitcher cheatsheet with {len(merged)} pitchers to {output_file}")

    print(f"\nTop 25 pitchers by Eno rank:")
    print(merged.head(25).to_string(index=False))

    print("\nNote: CG (2.5), SHO (2.5), and NH (5) are not projected by any system and are excluded.")
    print("These are extremely rare events with near-zero expected contribution.")


if __name__ == "__main__":
    create_pitcher_cheatsheet()
