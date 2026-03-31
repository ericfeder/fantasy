import pandas as pd
import requests
import io
import csv
import os
import re
import unicodedata
import argparse

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
        
        # Create a dictionary to store player positions
        player_positions = {}
        
        # Extract player names and positions
        # Based on the observed structure, we need 'Full Name' and 'Position' columns
        if 'Full Name' in df.columns and 'Position' in df.columns:
            print("Found 'Full Name' and 'Position' columns in the spreadsheet")
            
            # Extract player names and positions
            for _, row in df.iterrows():
                player_name = row.get('Full Name')
                position = row.get('Position')
                
                # Skip if player name or position is NaN
                if pd.isna(player_name) or pd.isna(position):
                    continue
                
                # Convert to string if not already
                if not isinstance(player_name, str):
                    player_name = str(player_name)
                if not isinstance(position, str):
                    position = str(position)
                
                # Store both original and normalized versions of the name
                player_positions[player_name] = position
                
                # Also store a normalized version for better matching
                normalized_name = normalize_player_name(player_name)
                player_positions[normalized_name] = position
                
                # Handle special cases
                if "(Batter)" in player_name:
                    # Remove the (Batter) suffix
                    base_name = player_name.replace(" (Batter)", "")
                    player_positions[base_name] = position
                    player_positions[normalize_player_name(base_name)] = position
            
            print(f"Extracted positions for {len(player_positions)} entries from Yahoo positions data")
        else:
            print("Could not find 'Full Name' and 'Position' columns in the spreadsheet")
            print("Available columns:", df.columns.tolist())
        
        return player_positions
    
    except Exception as e:
        print(f"Error processing Yahoo positions data: {e}")
        return {}

def save_positions_to_csv(player_positions):
    """Save the player positions to a CSV file."""
    # Ensure directories exist
    ensure_directories()
    
    # Count unique player names (excluding normalized versions)
    unique_players = set()
    for player in player_positions.keys():
        # Only count names that don't look like normalized names
        if any(c.isupper() for c in player) or any(c in player for c in "áéíóúüñÁÉÍÓÚÜÑ"):
            unique_players.add(player)
    
    with open('data/positions/player_positions.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Player', 'Position'])
        
        # Only write original player names (not normalized versions)
        for player in sorted(unique_players):
            writer.writerow([player, player_positions[player]])
    
    print(f"Saved {len(unique_players)} player positions to data/positions/player_positions.csv")

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
    
    # Count unique player names (excluding normalized versions)
    unique_players = set()
    for player in positions.keys():
        # Only count names that don't look like normalized names
        if any(c.isupper() for c in player) or any(c in player for c in "áéíóúüñÁÉÍÓÚÜÑ"):
            unique_players.add(player)
    
    print(f"Fetched positions for {len(unique_players)} unique players")
    
    # Print a few examples
    for i, player in enumerate(sorted(unique_players)[:20]):
        print(f"{player}: {positions[player]}")
    
    # Save the positions to a CSV file
    save_positions_to_csv(positions) 