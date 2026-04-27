import pandas as pd
import os
import csv
import re
import unicodedata

def ensure_directories():
    """Ensure all required directories exist"""
    directories = ['data', 'data/2026/projections', 'data/positions', 'data/output']
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")

def load_projections(source):
    """Load projections from a CSV file (rest-of-season ATC / OOPSY from FanGraphs)."""
    file_path = f"data/2026/projections/{source}_projections.csv"
    if not os.path.exists(file_path):
        print(f"Warning: {file_path} does not exist")
        return None
    
    df = pd.read_csv(file_path)
    print(f"Loaded {len(df)} players from {source}")
    return df


ACTUALS_2025_BATTING = 'data/2025/actuals/2025_batting_actuals.csv'


def load_2025_batting_ppg():
    """Compute empirical 2025 fantasy Pts/G per player from the FanGraphs
    leaderboard CSV at ``ACTUALS_2025_BATTING``. Returns a DataFrame with
    string ``playerid`` + ``ppg_2025``, or ``None`` if the file is missing.
    """
    if not os.path.exists(ACTUALS_2025_BATTING):
        print(f"Warning: {ACTUALS_2025_BATTING} not found; skipping 2025 Pts/G column")
        return None

    df = pd.read_csv(ACTUALS_2025_BATTING)
    df = df[df['G'].fillna(0) > 0].copy()
    df = calculate_fantasy_points(df)
    df['ppg_2025'] = (df['FantasyPoints'] / df['G']).round(1)
    df['playerid'] = df['playerid'].astype(str)
    print(f"Loaded 2025 batting actuals for {len(df)} players")
    return df[['playerid', 'ppg_2025']]

def calculate_fantasy_points(df):
    """Calculate fantasy points for each player based on their stats."""
    # Define the scoring system
    scoring = {
        'R': 2,      # Runs: 2 points
        '1B': 3,     # Singles: 3 points
        '2B': 5,     # Doubles: 5 points
        '3B': 8,     # Triples: 8 points
        'HR': 10,    # Home Runs: 10 points
        'RBI': 4,    # Runs Batted In: 4 points
        'SB': 5,     # Stolen Bases: 5 points
        'BB': 2,     # Walks: 2 points
        'HBP': 2,    # Hit By Pitch: 2 points
    }
    
    # Initialize fantasy points column
    df['FantasyPoints'] = 0
    
    # Add points for each category
    for category, points in scoring.items():
        if category in df.columns:
            df['FantasyPoints'] += df[category] * points
    
    return df

def load_yahoo_positions():
    """Load player positions from the CSV file."""
    file_path = "data/positions/player_positions.csv"
    if not os.path.exists(file_path):
        print(f"Warning: {file_path} does not exist")
        return {}
    
    positions = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        for row in reader:
            if len(row) >= 2:
                player_name = row[0]
                position = row[1]
                
                # Store the original name
                positions[player_name] = position
                
                # Also add a normalized version of the name for better matching
                normalized_name = normalize_player_name(player_name)
                positions[normalized_name] = position
                
                # Handle special cases
                if "(Batter)" in player_name:
                    # Remove the (Batter) suffix
                    base_name = player_name.replace(" (Batter)", "")
                    positions[base_name] = position
                    positions[normalize_player_name(base_name)] = position
    
    print(f"Loaded positions for {len(positions)} unique players")
    return positions

def normalize_player_name(name):
    """Normalize player name for better matching."""
    if not isinstance(name, str):
        return ""
    
    # Convert to lowercase
    name = name.lower()
    
    # Remove accents and convert to ASCII
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    
    # Remove suffixes like "Jr.", "Sr.", "III", etc.
    name = re.sub(r'\s+(jr\.?|sr\.?|[ivx]+)$', '', name)
    
    # Remove parenthetical suffixes like (Batter), (Pitcher)
    name = re.sub(r'\s+\([^)]+\)', '', name)
    
    # Remove special characters and extra spaces
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

def add_manual_positions(merged_df):
    """Add manual positions for important players with accent marks."""
    # Dictionary of player names and their positions
    manual_positions = {
        'Julio Rodríguez': 'OF',
        'Ronald Acuña Jr.': 'OF',
        'Adolis García': 'OF',
        'Jeremy Peña': 'SS',
        'Yandy Díaz': '1B,3B',
        'Andrés Giménez': '2B',
        'Jasson Domínguez': 'OF',
        'Jesús Sánchez': 'OF',
        'José Caballero': '2B,SS',
        'Endy Rodríguez': 'C,2B',
        'Mauricio Dubón': '2B,SS,OF',
        'Wenceel Pérez': '2B,OF',
        'José Tena': '2B,SS',
        'Ramón Urías': '2B,3B',
        'Ramón Laureano': 'OF',
        'Elias Díaz': 'C',
        'Agustin Ramírez': 'C',
        'Luis Urías': '2B,3B',
        'Eloy Jiménez': 'OF,DH',
        'Pedro Pagés': 'C',
        'Luisangel Acuña': '2B,SS',
        'Andy Ibáñez': '1B,2B,3B',
        'Angel Martínez': '2B,SS',
        'José Abreu': '1B',
        'Andrés Chaparro': '1B,3B',
        'Leo Jiménez': '2B,SS',
        'Aledmys Díaz': '1B,2B,3B',
        'Miguel Sanó': '1B,DH',
        'Nasim Nuñez': 'SS',
        'José Fermín': '2B,3B',
        'Tomás Nido': 'C',
        'Harold Ramírez': 'OF,DH',
        'Omar Narváez': 'C',
        'Pedro León': 'OF',
        'Martín Maldonado': 'C',
        'René Pinto': 'C',
        'Carlos Pérez': 'C',
        'Jesús Bastidas': '2B,SS',
        'César Salazar': 'C',
        'David Bañuelos': 'C',
        'Jack López': '2B,3B',
        'Sandy León': 'C',
        'Dom Nuñez': 'C'
    }
    
    # Add manual positions for players who don't have positions
    for idx, row in merged_df.iterrows():
        if pd.isna(row['YahooPositions']) or row['YahooPositions'] == '':
            player_name = row['PlayerName']
            if player_name in manual_positions:
                merged_df.at[idx, 'YahooPositions'] = manual_positions[player_name]
    
    return merged_df

def create_batter_cheatsheet():
    """Create a cheat sheet for batters with Yahoo positions (RoS ATC + OOPSY)."""
    # Ensure directories exist
    ensure_directories()
    
    # Rest-of-season projections only (scraped via ratcdc / roopsydc → atc / oopsy CSVs)
    sources = ['atc', 'oopsy', 'thebatx']
    projections = {}
    
    for source in sources:
        df = load_projections(source)
        if df is not None:
            # Filter out pitchers (batters have AB > 0)
            df = df[df['AB'] > 0]
            # Calculate fantasy points
            df = calculate_fantasy_points(df)
            # Keep only necessary columns, now including Games + playerid (for
            # joining to 2025 actuals later).
            df = df[['PlayerName', 'Team', 'playerid', 'G', 'FantasyPoints']].copy()
            df['playerid'] = df['playerid'].astype(str)
            # Round fantasy points to integers
            df['FantasyPoints'] = df['FantasyPoints'].round().astype(int)
            # Rename the fantasy points column to include the source
            df = df.rename(columns={'FantasyPoints': f'{source}_points', 'G': f'{source}_games'})
            projections[source] = df
    
    # Merge projections from all sources
    if not projections:
        print("No projections available")
        return
    
    # Start with the first source
    merged_df = projections[sources[0]]
    
    # Merge with other sources
    for source in sources[1:]:
        if source in projections:
            merged_df = pd.merge(
                merged_df, 
                projections[source], 
                on=['PlayerName', 'Team', 'playerid'], 
                how='outer'
            )
    
    # Convert all fantasy point columns to integers to remove decimal points
    point_columns = [f'{source}_points' for source in sources if source in projections]
    for col in point_columns:
        merged_df[col] = merged_df[col].fillna(0).round().astype(int)
    
    # Convert all games columns to integers to remove decimal points
    games_columns = [f'{source}_games' for source in sources if source in projections]
    for col in games_columns:
        merged_df[col] = merged_df[col].fillna(0).round().astype(int)
    
    # Filter out players projected to play <60% of remaining games
    # (uses league-wide max projected G as the proxy for remaining games)
    max_games = merged_df[games_columns].max(axis=1)
    remaining_games = max_games.max()
    threshold = 0.6 * remaining_games
    before = len(merged_df)
    merged_df = merged_df[max_games >= threshold].reset_index(drop=True)
    print(
        f"Filtered out {before - len(merged_df)} players projected to play "
        f"<60% of remaining games (threshold: {threshold:.1f} of {remaining_games:.0f} games)"
    )
    
    # Calculate points per game for each projection system
    for source in sources:
        points_col = f'{source}_points'
        games_col = f'{source}_games'
        ppg_col = f'{source}_ppg'
        if points_col in merged_df.columns and games_col in merged_df.columns:
            merged_df[ppg_col] = (merged_df[points_col] / merged_df[games_col]).round(1)
        else:
            merged_df[ppg_col] = 0.0
        # Handle edge cases: replace inf and NaN values with 0
        merged_df[ppg_col] = merged_df[ppg_col].replace([float('inf'), float('-inf')], 0)
        merged_df[ppg_col] = merged_df[ppg_col].fillna(0)

    # Merge in empirical 2025 Pts/G (NaN for players without a 2025 line)
    actuals_2025 = load_2025_batting_ppg()
    if actuals_2025 is not None:
        merged_df = merged_df.merge(actuals_2025, on='playerid', how='left')
    else:
        merged_df['ppg_2025'] = pd.NA

    # Load Yahoo positions
    yahoo_positions = load_yahoo_positions()
    
    # Add normalized player names for better matching
    merged_df['NormalizedName'] = merged_df['PlayerName'].apply(normalize_player_name)
    
    # Add Yahoo positions to the dataframe
    # First try exact match
    merged_df['YahooPositions'] = merged_df['PlayerName'].map(yahoo_positions)
    
    # For players without positions, try normalized name match
    mask = merged_df['YahooPositions'].isna()
    merged_df.loc[mask, 'YahooPositions'] = merged_df.loc[mask, 'NormalizedName'].map(yahoo_positions)
    
    # Special case handling for specific players
    for idx, row in merged_df.iterrows():
        if pd.isna(row['YahooPositions']) or row['YahooPositions'] == '':
            player_name = row['PlayerName']
            
            # Handle José Ramírez specifically
            if player_name == 'José Ramírez':
                merged_df.at[idx, 'YahooPositions'] = '3B'
            
            # Handle Shohei Ohtani specifically
            elif player_name == 'Shohei Ohtani':
                merged_df.at[idx, 'YahooPositions'] = 'Util'
    
    # Add manual positions for important players with accent marks
    merged_df = add_manual_positions(merged_df)
    
    # Standardize outfield positions (convert LF, CF, RF to OF)
    merged_df['YahooPositions'] = merged_df['YahooPositions'].apply(standardize_positions)
    
    # Fill NaN values in YahooPositions
    merged_df['YahooPositions'] = merged_df['YahooPositions'].fillna('')
    
    # Drop the normalized name column as it's no longer needed
    merged_df = merged_df.drop(columns=['NormalizedName'])
    
    # Select and reorder columns
    final_columns = [
        'PlayerName', 'YahooPositions',
        'oopsy_ppg', 'thebatx_ppg', 'atc_ppg', 'ppg_2025',
        'oopsy_points', 'thebatx_points', 'atc_points',
    ]
    final_columns = [c for c in final_columns if c in merged_df.columns]
    merged_df = merged_df[final_columns]
    
    # Sort by RoS ATC points per game
    merged_df = merged_df.sort_values('atc_ppg', ascending=False)
    
    # Rename columns to human-friendly headers before saving
    merged_df = merged_df.rename(columns={
        'PlayerName':     'Player',
        'YahooPositions': 'Position',
        'atc_points':     'ATC Pts',
        'oopsy_points':   'OOPSY Pts',
        'thebatx_points': 'THE BAT X Pts',
        'atc_ppg':        'ATC Pts/G',
        'oopsy_ppg':      'OOPSY Pts/G',
        'thebatx_ppg':    'THE BAT X Pts/G',
        'ppg_2025':       '2025 Pts/G',
    })

    # Save to CSV
    output_file = "data/output/batter_cheatsheet.csv"
    merged_df.to_csv(output_file, index=False)
    print(f"Saved batter cheat sheet with {len(merged_df)} players to {output_file}")
    
    # Print top batters
    print("\nTop batters by RoS ATC fantasy points:")
    print(merged_df.head(10))
    
    # Print stats on position matching
    positions_filled = (merged_df['Position'] != '').sum()
    print(f"\nPosition matching stats:")
    print(f"Players with positions: {positions_filled} out of {len(merged_df)} ({positions_filled/len(merged_df)*100:.1f}%)")
    
    # Print players with accent marks who don't have positions
    accent_players = merged_df[
        (merged_df['Position'] == '') & 
        (merged_df['Player'].str.contains('[áéíóúüñÁÉÍÓÚÜÑ]'))
    ]
    if not accent_players.empty:
        print("\nPlayers with accent marks who don't have positions:")
        for idx, row in accent_players.iterrows():
            print(f"{row['Player']}")

def standardize_positions(positions):
    """
    Standardize positions by converting specific outfield positions (LF, CF, RF)
    to a generic outfield position (OF).
    """
    # Handle NaN values and empty strings
    if pd.isna(positions) or positions == '':
        return positions
    
    # Convert to string if it's not already
    if not isinstance(positions, str):
        positions = str(positions)
    
    # Split the positions by comma
    pos_list = positions.split(',')
    
    # Replace LF, CF, RF with OF
    standardized_pos = []
    has_of = False
    
    for pos in pos_list:
        pos = pos.strip()
        if pos in ['LF', 'CF', 'RF']:
            if not has_of:
                standardized_pos.append('OF')
                has_of = True
        else:
            standardized_pos.append(pos)
    
    # Join the positions with commas
    return ','.join(standardized_pos)

if __name__ == "__main__":
    create_batter_cheatsheet() 
