import time
import pandas as pd
import requests
import json
import re
import os
import sys

# FanGraphs rest-of-season pitching types → saved as thebatx / oopsy for pitcher_cheatsheet.py
ROS_URLS = {
    'thebatx': (
        'rthebatx',
        'https://www.fangraphs.com/projections?type=rthebatx&stats=pit&pos=all&team=0&players=0&lg=all&z=1745729762&pageitems=30&statgroup=standard&fantasypreset=dashboard',
    ),
    'oopsy': (
        'roopsydc',
        'https://www.fangraphs.com/projections?type=roopsydc&stats=pit&pos=all&team=0&players=0&lg=all&z=1745729762&pageitems=30&statgroup=standard&fantasypreset=dashboard',
    ),
}

OUTPUT_DIR = 'data/2026/projections'


def ensure_directories():
    directories = ['data', 'data/2026', OUTPUT_DIR]
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")


def scrape_projections(label, fangraphs_type, url):
    print(f"Scraping RoS {label} ({fangraphs_type}) pitching projections...")

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        pattern = r'{"data":\[(.+?)\],"dataUpdateCount":'
        match = re.search(pattern, response.text)

        if not match:
            print(f"Could not find player data in the HTML for {label}")
            return None

        json_str = '[' + match.group(1) + ']'
        json_str = re.sub(r',\s*]', ']', json_str)

        try:
            data = json.loads(json_str)
            df = pd.DataFrame(data)

            csv_path = f'{OUTPUT_DIR}/{label}_pitching_projections.csv'
            df.to_csv(csv_path, index=False)
            print(f"Saved {len(df)} pitchers from RoS {label} to {csv_path}")

            return df

        except json.JSONDecodeError as e:
            print(f"Error parsing JSON for {label}: {e}")

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
                    csv_path = f'{OUTPUT_DIR}/{label}_pitching_projections.csv'
                    df.to_csv(csv_path, index=False)
                    print(f"Saved {label} pitching projections to {csv_path} using alternative method")
                    return df

            return None

    except Exception as e:
        print(f"ERROR scraping {label} pitching projections: {e}")
        return None


def main():
    ensure_directories()

    dfs = {}
    failed_sources = []

    for label, (fangraphs_type, url) in ROS_URLS.items():
        result = scrape_projections(label, fangraphs_type, url)
        dfs[label] = result

        if result is None:
            failed_sources.append(label)

        time.sleep(5)

    print("\nScraping completed!")

    if failed_sources:
        print(f"\nERROR: Failed to scrape the following sources: {', '.join(failed_sources)}")
        print("Script will exit with error code.")
        sys.exit(1)

    print("All pitching projection scraping completed successfully!")


if __name__ == "__main__":
    main()
