"""Download FanGraphs rest-of-season projection tables.

FanGraphs blocks datacenter traffic (403 / Cloudflare). We try, in order:

1. ``/api/projections`` JSON (same source the site uses for its table)
2. Legacy HTML scrape (embedded React ``data`` array)
"""
import json
import os
import re

import pandas as pd

from fangraphs_http import get_best_effort

API_BASE = 'https://www.fangraphs.com/api/projections'
DEFAULT_REFERER = 'https://www.fangraphs.com/projections'

_HTML_DATA_RE = re.compile(r'{"data":\[(.+?)\],"dataUpdateCount":')
_HTML_PLAYER_RE = re.compile(r'{"Team":"[^"]+".+?,"playerid":"[^"]+"}')


def projections_api_url(stats, fangraphs_type):
    return f'{API_BASE}?stats={stats}&type={fangraphs_type}'


def _api_headers(stats, fangraphs_type):
    return {
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'{DEFAULT_REFERER}?stats={stats}&type={fangraphs_type}',
    }


def _rows_from_api_payload(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ('data', 'players', 'rows'):
            rows = payload.get(key)
            if isinstance(rows, list) and rows:
                return rows
    raise ValueError(f'unexpected API payload type/shape: {type(payload).__name__}')


def fetch_rows_from_api(stats, fangraphs_type):
    url = projections_api_url(stats, fangraphs_type)
    response = get_best_effort(url, headers=_api_headers(stats, fangraphs_type))
    if 'json' not in (response.headers.get('content-type') or '').lower():
        if response.text.lstrip().startswith('<!'):
            raise RuntimeError('API returned HTML (likely Cloudflare challenge)')
    return _rows_from_api_payload(response.json())


def fetch_rows_from_html(page_url):
    response = get_best_effort(
        page_url,
        headers={'Referer': DEFAULT_REFERER},
    )
    html = response.text
    match = _HTML_DATA_RE.search(html)
    if match:
        json_str = '[' + match.group(1) + ']'
        json_str = re.sub(r',\s*]', ']', json_str)
        return json.loads(json_str)

    players = []
    for player_json in _HTML_PLAYER_RE.findall(html):
        try:
            players.append(json.loads(player_json))
        except json.JSONDecodeError:
            continue
    if players:
        return players
    raise RuntimeError('could not find projection data in HTML')


def download_projections(label, fangraphs_type, stats, csv_path, page_url=None):
    """Fetch projections and write ``csv_path``. Returns DataFrame or None."""
    print(f"Scraping RoS {label} ({fangraphs_type}, {stats}) projections...")

    rows = None
    source = None

    try:
        rows = fetch_rows_from_api(stats, fangraphs_type)
        source = 'API'
    except Exception as api_err:
        print(f"  API fetch failed: {api_err}")

    if rows is None and page_url:
        try:
            rows = fetch_rows_from_html(page_url)
            source = 'HTML'
        except Exception as html_err:
            print(f"  HTML fetch failed: {html_err}")

    if not rows:
        print(f"ERROR: could not fetch {label} projections")
        return None

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(csv_path) or '.', exist_ok=True)
    df.to_csv(csv_path, index=False)
    print(f"Saved {len(df)} rows from RoS {label} via {source} to {csv_path}")
    return df
