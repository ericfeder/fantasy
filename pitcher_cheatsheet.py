import pandas as pd
import requests
import os
import re
import unicodedata


PROJECTION_DIR = 'data/2026/projections'
OUTPUT_DIR = 'data/output'
ENO_CACHE_PATH = 'data/2026/eno_pitch_report.csv'

SOURCES = ['thebatx', 'oopsy']

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


def fetch_eno_rankings(force_download=True):
    """Fetch Eno Sarris Pitch Report 2026 from Google Sheets."""
    os.makedirs(os.path.dirname(ENO_CACHE_PATH), exist_ok=True)

    should_download = force_download or not os.path.exists(ENO_CACHE_PATH)

    if should_download:
        url = "https://docs.google.com/spreadsheets/d/1daR9RNic3GcfDb6FLsm2OZRBS8VkqucOqHSnIS7ru5c/export?format=csv&gid=543684644"
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


def create_pitcher_cheatsheet():
    ensure_directories()

    projections = {}
    for source in SOURCES:
        df = load_pitching_projections(source)
        if df is not None:
            df = calculate_fantasy_points(df)
            df = df[['PlayerName', 'Team', 'xMLBAMID', 'G', 'GS', 'IP', 'FantasyPoints']].copy()
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
                on=['PlayerName', 'Team', 'xMLBAMID'],
                how='outer'
            )

    # Fill NaN and convert to int
    point_cols = [f'{s}_points' for s in SOURCES if s in projections]
    ip_cols = [f'{s}_ip' for s in SOURCES if s in projections]
    games_cols = [f'{s}_games' for s in SOURCES if s in projections]

    for col in point_cols + ip_cols + games_cols:
        merged[col] = merged[col].fillna(0).round().astype(int)

    # Points per IP for each source
    for source in SOURCES:
        pts_col = f'{source}_points'
        ip_col = f'{source}_ip'
        ppip_col = f'{source}_ppip'
        if pts_col in merged.columns and ip_col in merged.columns:
            merged[ppip_col] = 0.0
            valid = merged[ip_col] > 0
            merged.loc[valid, ppip_col] = (
                merged.loc[valid, pts_col] / merged.loc[valid, ip_col]
            ).round(2)

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

    # Build final column order
    out_cols = [
        'PlayerName', 'eno_rank', 'eno_proj_ip',
        'thebatx_points', 'thebatx_ppip', 'thebatx_ip',
        'oopsy_points', 'oopsy_ppip', 'oopsy_ip',
    ]
    out_cols = [c for c in out_cols if c in merged.columns]
    merged = merged[out_cols]

    # Sort by eno_rank (pitchers without an Eno rank go to the bottom)
    merged = merged.sort_values('eno_rank', ascending=True, na_position='last').reset_index(drop=True)

    output_file = f"{OUTPUT_DIR}/pitcher_cheatsheet.csv"
    merged.to_csv(output_file, index=False)
    print(f"\nSaved pitcher cheatsheet with {len(merged)} pitchers to {output_file}")

    print(f"\nTop 25 pitchers by Eno rank:")
    print(merged.head(25).to_string(index=False))

    print("\nNote: CG (2.5), SHO (2.5), and NH (5) are not projected by any system and are excluded.")
    print("These are extremely rare events with near-zero expected contribution.")


if __name__ == "__main__":
    create_pitcher_cheatsheet()
