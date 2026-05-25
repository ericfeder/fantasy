import pandas as pd
import requests
import csv
import os
import argparse
from collections import defaultdict

from player_names import normalize_player_name

def ensure_directories():
    """Ensure all required directories exist"""
    directories = ['data', 'data/positions']
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")

def fetch_positions_from_google_sheet(force_download=True):
    """
    Fetch position data from the Google Sheets spreadsheet.
    Returns a dictionary mapping player names to their positions.
    
    Args:
        force_download (bool): If True, always download fresh data from Google Sheets,
                              ignoring any cached version.
    """
    # Ensure directories exist
    ensure_directories()
    
    # Path to the local CSV file
    local_file_path = "data/positions/yahoo_positions_raw.csv"
    
    # Check if we should download the file
    should_download = force_download or not os.path.exists(local_file_path)
    
    if should_download:
        # Download it from Google Sheets
        url = "https://docs.google.com/spreadsheets/d/1aEwLXNbBCDiCDmt0B91y8pyhk-XnBApUgtQTNgIZBCc/export?format=csv&gid=75974690"
        
        try:
            # Fetch the CSV data
            response = requests.get(url)
            response.raise_for_status()  # Raise an exception for HTTP errors
            
            # Save the raw bytes to preserve correct UTF-8 encoding
            with open(local_file_path, 'wb') as f:
                f.write(response.content)
            
            print(f"Downloaded fresh Yahoo positions data to {local_file_path}")
        except Exception as e:
            print(f"Error downloading positions from Google Sheets: {e}")
            if os.path.exists(local_file_path):
                print("Using existing cached positions data instead")
            else:
                return {}
    else:
        print(f"Using existing Yahoo positions data from {local_file_path}")
    
    try:
        # Read the CSV data into a pandas DataFrame, skipping the first 3 rows which contain metadata
        df = pd.read_csv(local_file_path, skiprows=4)
        
        # Print the column names to understand the structure
        print("Columns in the spreadsheet:", df.columns.tolist())
        
        position_rows = []
        player_positions = {}

        # Based on the observed structure, we need 'Full Name' and 'Position' columns
        if 'Full Name' in df.columns and 'Position' in df.columns:
            print("Found 'Full Name' and 'Position' columns in the spreadsheet")

            for _, row in df.iterrows():
                player_name = row.get('Full Name')
                position = row.get('Position')
                team = row.get('Team') if 'Team' in df.columns else None

                if pd.isna(player_name) or pd.isna(position):
                    continue

                if not isinstance(player_name, str):
                    player_name = str(player_name)
                if not isinstance(position, str):
                    position = str(position)
                if pd.isna(team):
                    team = ''
                elif not isinstance(team, str):
                    team = str(team)

                position_rows.append({
                    'name': player_name,
                    'team': team,
                    'position': position,
                })

            names_by_player = defaultdict(list)
            for entry in position_rows:
                names_by_player[entry['name']].append(entry)

            for entry in position_rows:
                name = entry['name']
                team = entry['team']
                position = entry['position']
                norm = normalize_player_name(name)

                if team:
                    player_positions[(name, team)] = position
                    player_positions[(norm, team)] = position

                if len(names_by_player[name]) == 1:
                    player_positions[name] = position
                    player_positions[norm] = position

                if "(Batter)" in name:
                    base_name = name.replace(" (Batter)", "")
                    base_norm = normalize_player_name(base_name)
                    if team:
                        player_positions[(base_name, team)] = position
                        player_positions[(base_norm, team)] = position
                    if len(names_by_player[name]) == 1:
                        player_positions[base_name] = position
                        player_positions[base_norm] = position

            print(
                f"Extracted positions for {len(position_rows)} players "
                f"({len(names_by_player)} unique names) from Yahoo positions data"
            )
        else:
            print("Could not find 'Full Name' and 'Position' columns in the spreadsheet")
            print("Available columns:", df.columns.tolist())

        player_positions['_rows'] = position_rows
        return player_positions
    
    except Exception as e:
        print(f"Error processing Yahoo positions data: {e}")
        return {}

def save_positions_to_csv(player_positions):
    """Save the player positions to a CSV file."""
    ensure_directories()

    rows = player_positions.get('_rows', [])
    with open('data/positions/player_positions.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Player', 'Team', 'Position'])
        for entry in sorted(rows, key=lambda r: (r['name'], r['team'])):
            writer.writerow([entry['name'], entry['team'], entry['position']])

    print(f"Saved {len(rows)} player positions to data/positions/player_positions.csv")

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Fetch player positions from Google Sheets.')
    parser.add_argument('--no-force', action='store_true', 
                        help='Use cached positions if available instead of forcing download')
    args = parser.parse_args()
    
    # Determine if we should force download
    force_download = not args.no_force
    if force_download:
        print("Will force download of latest position data from Google Sheets")
    else:
        print("Will use cached position data if available")
    
    # Fetch the positions
    positions = fetch_positions_from_google_sheet(force_download=force_download)
    
    rows = positions.get('_rows', [])
    print(f"Fetched positions for {len(rows)} players")

    for entry in sorted(rows, key=lambda r: r['name'])[:20]:
        team = entry['team']
        suffix = f" ({team})" if team else ''
        print(f"{entry['name']}{suffix}: {entry['position']}")
    
    # Save the positions to a CSV file
    save_positions_to_csv(positions) 