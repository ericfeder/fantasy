import subprocess
import os
import time
import sys
import re
import glob

def run_command(command, description):
    """Run a command and print its output in real-time"""
    print(f"\n{'='*80}")
    print(f"RUNNING: {description}")
    print(f"{'='*80}\n")
    
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Print output in real-time
    for line in process.stdout:
        print(line, end='')
        sys.stdout.flush()
    
    process.wait()
    return process.returncode

def get_source_names_from_cheatsheet():
    """Extract the projection source names from batter_cheatsheet.py"""
    with open('batter_cheatsheet.py', 'r') as f:
        content = f.read()
    
    # Find the sources list in the file
    match = re.search(r"sources\s*=\s*\[(.*?)\]", content)
    if match:
        sources_str = match.group(1)
        # Extract individual source names
        sources = [s.strip("' ") for s in sources_str.split(',')]
        return sources
    
    return []

def ensure_directories():
    """Ensure all required directories exist"""
    directories = ['data', 'data/2026/projections', 'data/positions', 'data/output']
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")

def update_cheatsheet_sources(available_files):
    """Update the sources in batter_cheatsheet.py to match available files"""
    available_sources = []
    for f in available_files:
        source = os.path.splitext(os.path.basename(f))[0].replace('_projections', '')
        available_sources.append(source)
    
    if not available_sources:
        print("No projection files found in data/2026/projections.")
        return False
    
    current_sources = get_source_names_from_cheatsheet()
    if set(current_sources) == set(available_sources):
        print("Sources in batter_cheatsheet.py already match available files.")
        return False
    
    print(f"Updating batter_cheatsheet.py with sources: {available_sources}")
    
    with open('batter_cheatsheet.py', 'r') as f:
        content = f.read()
    
    # Replace the sources list
    sources_str = "', '".join(available_sources)
    updated_content = re.sub(
        r"sources\s*=\s*\[(.*?)\]",
        f"sources = ['{sources_str}']",
        content
    )
    
    with open('batter_cheatsheet.py', 'w') as f:
        f.write(updated_content)
    
    return True

def main():
    """Main function to run both scraping and cheatsheet generation"""
    start_time = time.time()
    
    # Ensure directories exist
    ensure_directories()
    
    # Step 1: Scrape batting projections
    scrape_status = run_command(['python', 'scrape_projections.py'], 
                                "Scraping batting projections from FanGraphs")
    
    if scrape_status != 0:
        print("\nERROR: Batting projection scraping failed. Exiting.")
        return
    
    # Step 2: Scrape pitching projections
    pitch_scrape_status = run_command(['python', 'scrape_pitching_projections.py'],
                                      "Scraping pitching projections from FanGraphs")
    
    if pitch_scrape_status != 0:
        print("\nERROR: Pitching projection scraping failed. Exiting.")
        return
    
    # Step 3: Check and update source names in batter_cheatsheet.py if needed
    batter_dir = 'data/2026/projections'
    batter_basenames = ('atc_projections.csv', 'oopsy_projections.csv')
    projection_files = [
        os.path.join(batter_dir, b)
        for b in batter_basenames
        if os.path.exists(os.path.join(batter_dir, b))
    ]
    if projection_files:
        update_cheatsheet_sources(projection_files)
    
    # Step 4: Fetch the latest player positions from Google Sheets
    positions_status = run_command(['python', 'fetch_positions.py'],
                                   "Fetching latest player positions")
    
    if positions_status != 0:
        print("\nWARNING: Position fetching failed. Will use existing position data if available.")
    
    # Step 5: Generate batter cheatsheet
    cheatsheet_status = run_command(['python', 'batter_cheatsheet.py'],
                                    "Generating batter cheatsheet")
    
    if cheatsheet_status != 0:
        print("\nERROR: Batter cheatsheet generation failed.")
        return
    
    # Step 6: Generate pitcher cheatsheet
    pitch_cheatsheet_status = run_command(['python', 'pitcher_cheatsheet.py'],
                                          "Generating pitcher cheatsheet")
    
    if pitch_cheatsheet_status != 0:
        print("\nERROR: Pitcher cheatsheet generation failed.")
        return
    
    # Step 7: Upload cheatsheets to Google Sheets
    upload_status = run_command(['python', 'upload_to_sheets.py'],
                                "Uploading cheatsheets to Google Sheets")

    if upload_status != 0:
        print("\nWARNING: Google Sheets upload failed. Local CSVs are still up-to-date.")

    # Calculate and display total runtime
    end_time = time.time()
    runtime = end_time - start_time
    print(f"\nTotal runtime: {runtime:.2f} seconds ({runtime/60:.2f} minutes)")
    
    # Display success message
    print("\n✅ FANTASY BASEBALL UPDATE COMPLETE!")
    print("   Your projections and cheatsheet are now up-to-date.")

if __name__ == "__main__":
    main() 