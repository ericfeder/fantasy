import os
import sys
import time

from fangraphs_projections import download_projections

# FanGraphs rest-of-season batting types → saved as atc / oopsy for batter_cheatsheet.py
ROS_SOURCES = {
    'atc': (
        'ratcdc',
        'https://www.fangraphs.com/projections?type=ratcdc&stats=bat&pos=all&team=0&players=0&lg=all&pageitems=30&statgroup=standard&fantasypreset=dashboard',
    ),
    'oopsy': (
        'roopsydc',
        'https://www.fangraphs.com/projections?type=roopsydc&stats=bat&pos=all&team=0&players=0&lg=all&pageitems=30&statgroup=standard&fantasypreset=dashboard',
    ),
    'thebatx': (
        'rthebatx',
        'https://www.fangraphs.com/projections?type=rthebatx&stats=bat&pos=all&team=0&players=0&lg=all&pageitems=30&statgroup=standard&fantasypreset=dashboard',
    ),
}

OUTPUT_DIR = 'data/2026/projections'


def ensure_directories():
    for directory in ('data', 'data/2026', OUTPUT_DIR):
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")


def main():
    ensure_directories()

    failed_sources = []
    for label, (fangraphs_type, page_url) in ROS_SOURCES.items():
        csv_path = f'{OUTPUT_DIR}/{label}_projections.csv'
        result = download_projections(
            label, fangraphs_type, 'bat', csv_path, page_url=page_url,
        )
        if result is None:
            failed_sources.append(label)
        time.sleep(3)

    print('Scraping completed!')

    if failed_sources:
        print(f"\nERROR: Failed to scrape the following sources: {', '.join(failed_sources)}")
        print('Script will exit with error code.')
        sys.exit(1)

    print('All scraping operations completed successfully!')


if __name__ == '__main__':
    main()
