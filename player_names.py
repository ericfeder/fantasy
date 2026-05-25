"""Shared helpers for matching players across FanGraphs, Yahoo, and the sheet."""

import re
import unicodedata

# FanGraphs team codes -> Yahoo / TJStats team codes
FG_TO_YAHOO_TEAM = {
    'ARI': 'AZ',
    'CHW': 'CWS',
    'KCR': 'KC',
    'SDP': 'SD',
    'SFG': 'SF',
    'TBR': 'TB',
    'WSN': 'WSH',
}


def fg_team_to_yahoo(team):
    if not isinstance(team, str):
        return team
    return FG_TO_YAHOO_TEAM.get(team, team)


def normalize_player_name(name):
    """Normalize player name for fuzzy matching."""
    if not isinstance(name, str):
        return ''
    name = name.lower()
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    name = re.sub(r'\s+(jr\.?|sr\.?|[ivx]+)$', '', name)
    name = re.sub(r'\s+\([^)]+\)', '', name)
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def parse_disambiguated_name(name):
    """Split ``Max Muncy (LAD)`` into ``('Max Muncy', 'LAD')``."""
    if not isinstance(name, str):
        return '', None
    m = re.match(r'^(.*)\s+\(([A-Z]{2,3})\)$', name.strip())
    if m:
        return m.group(1).strip(), m.group(2)
    return name.strip(), None


def ownership_lookup_key(name, team_abbr=None):
    """Build a lookup key for Yahoo ownership maps."""
    base_name, suffix_team = parse_disambiguated_name(name)
    team = team_abbr or suffix_team
    norm = normalize_player_name(base_name)
    if team:
        return f'{norm}|{team}'
    return norm


def lookup_yahoo_position(positions, name, team=None):
    """Resolve a Yahoo position using team when names collide."""
    yahoo_team = fg_team_to_yahoo(team) if team else None
    norm = normalize_player_name(name)
    for key in (
        (name, yahoo_team),
        (name, team),
        (norm, yahoo_team),
        (norm, team),
    ):
        if key[1] and key in positions:
            return positions[key]
    return positions.get(name) or positions.get(norm)
