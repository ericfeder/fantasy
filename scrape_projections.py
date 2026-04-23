import time
import pandas as pd
import requests
import json
import re
import os
import sys

# FanGraphs rest-of-season batting types → saved as atc / oopsy for batter_cheatsheet.py
ROS_URLS = {
    'atc': (
        'ratcdc',
        'https://www.fangraphs.com/projections?type=ratcdc&stats=bat&pos=all&team=0&players=0&lg=all&z=1745729762&pageitems=30&statgroup=standard&fantasypreset=dashboard',
    ),
    'oopsy': (
        'roopsydc',
        'https://www.fangraphs.com/projections?type=roopsydc&stats=bat&pos=all&team=0&players=0&lg=all&z=1745729762&pageitems=30&statgroup=standard&fantasypreset=dashboard',
    ),
    'thebatx': (
        'rthebatx',
        'https://www.fangraphs.com/projections?type=rthebatx&stats=bat&pos=all&team=0&players=0&lg=all&z=1745729762&pageitems=30&statgroup=standard&fantasypreset=dashboard',
    ),
}

OUTPUT_DIR = 'data/2026/projections'

# Create directories to store the CSV files
def ensure_directories():
    """Ensure all required directories exist"""
    directories = ['data', 'data/2026', OUTPUT_DIR]
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")

def scrape_projections(label, fangraphs_type, url):
    print(f"Scraping RoS {label} ({fangraphs_type}) projections...")
    
    try:
        # Set headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        
        # Make the request
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Extract the data from the JavaScript object
        # Look for the pattern where player data is stored
        pattern = r'{"data":\[(.+?)\],"dataUpdateCount":'
        match = re.search(pattern, response.text)
        
        if not match:
            print(f"Could not find player data in the HTML for {label}")
            return None
        
        # Extract the JSON data
        json_str = '[' + match.group(1) + ']'
        
        # Clean up the JSON string (remove any trailing commas)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        try:
            # Parse the JSON data
            data = json.loads(json_str)
            
            # Convert to DataFrame
            df = pd.DataFrame(data)
            
            # Save to CSV (label matches batter_cheatsheet load_projections keys)
            csv_path = f'{OUTPUT_DIR}/{label}_projections.csv'
            df.to_csv(csv_path, index=False)
            print(f"Saved {len(df)} players from RoS {label} to {csv_path}")
            
            return df
        
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON for {label}: {e}")
            
            # Try an alternative approach - extract each player object individually
            player_pattern = r'{"Team":"[^"]+".+?,"playerid":"[^"]+"}'
            player_matches = re.findall(player_pattern, response.text)
            
            if player_matches:
                print(f"Found {len(player_matches)} player objects using alternative method")
                players_data = []
                
                for player_json in player_matches:
                    try:
                        player_data = json.loads(player_json)
                        players_data.append(player_data)
                    except json.JSONDecodeError:
                        continue
                
                if players_data:
                    df = pd.DataFrame(players_data)
                    csv_path = f'{OUTPUT_DIR}/{label}_projections.csv'
                    df.to_csv(csv_path, index=False)
                    print(f"Saved {label} projections to {csv_path} using alternative method")
                    return df
            
            return None
    
    except Exception as e:
        print(f"❌ ERROR scraping {label} projections: {e}")
        return None

def main():
    # Ensure directories exist
    ensure_directories()
    
    # Scrape projections for each system
    dfs = {}
    failed_sources = []
    
    for label, (fangraphs_type, url) in ROS_URLS.items():
        result = scrape_projections(label, fangraphs_type, url)
        dfs[label] = result
        
        if result is None:
            failed_sources.append(label)
        
        # Add a delay to avoid overloading the server
        time.sleep(5)

    print("Scraping completed!")
    
    # Check if any scraping failed
    if failed_sources:
        print(f"\nERROR: Failed to scrape the following sources: {', '.join(failed_sources)}")
        print("Script will exit with error code.")
        sys.exit(1)
    
    print("All scraping operations completed successfully!")

if __name__ == "__main__":
    main() 
