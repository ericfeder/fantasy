import pandas as pd
import subprocess
import json
import os
import re
import tempfile
import unicodedata

SPREADSHEET_ID = '1LRhXDU-cu66YVhGZWZeY9qi1187elU8lcFtS_jVgxXs'

TABS = {
    'Hitters': 'data/output/batter_cheatsheet.csv',
    'Pitchers': 'data/output/pitcher_cheatsheet.csv',
}


def csv_to_values(csv_path):
    """Read a CSV and return a list-of-lists (header + rows) for the Sheets API."""
    df = pd.read_csv(csv_path)
    header = df.columns.tolist()
    rows = df.fillna('').values.tolist()
    # Convert numpy types to native Python for JSON serialisation
    rows = [[v.item() if hasattr(v, 'item') else v for v in row] for row in rows]
    return [header] + rows


def get_sheet_id(tab_name):
    """Get the sheetId for a given tab name."""
    result = subprocess.run(
        ['gws', 'sheets', 'spreadsheets', 'get',
         '--params', json.dumps({'spreadsheetId': SPREADSHEET_ID})],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    # Filter out the keyring info line
    lines = [l for l in result.stdout.splitlines() if not l.strip().startswith('Using keyring')]
    data = json.loads('\n'.join(lines))
    for sheet in data.get('sheets', []):
        if sheet['properties']['title'] == tab_name:
            return sheet['properties']['sheetId']
    return None


def resize_tab(tab_name, num_rows, num_cols=26):
    """Resize a tab to fit the data."""
    sheet_id = get_sheet_id(tab_name)
    if sheet_id is None:
        print(f"  Could not find sheetId for {tab_name}")
        return

    result = subprocess.run(
        ['gws', 'sheets', 'spreadsheets', 'batchUpdate',
         '--params', json.dumps({'spreadsheetId': SPREADSHEET_ID}),
         '--json', json.dumps({'requests': [{
             'updateSheetProperties': {
                 'properties': {
                     'sheetId': sheet_id,
                     'gridProperties': {'rowCount': num_rows, 'columnCount': num_cols},
                 },
                 'fields': 'gridProperties(rowCount,columnCount)',
             }
         }]})],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        stderr = [l for l in result.stderr.splitlines() if 'keyring' not in l.lower()]
        print(f"  Warning resizing {tab_name}: {' '.join(stderr)}")


def clear_tab(tab_name):
    """Clear all values in a tab."""
    result = subprocess.run(
        [
            'gws', 'sheets', 'spreadsheets', 'values', 'clear',
            '--params', json.dumps({
                'spreadsheetId': SPREADSHEET_ID,
                'range': f'{tab_name}!A:ZZ',
            }),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  Warning clearing {tab_name}: {result.stderr.strip()}")
    else:
        print(f"  Cleared {tab_name}")


def write_tab(tab_name, values, batch_size=500):
    """Write values to a tab, batching to stay within command-line limits."""
    header = values[0]
    data_rows = values[1:]
    total_written = 0

    for i in range(0, len(data_rows), batch_size):
        batch = data_rows[i:i + batch_size]
        start_row = i + 1  # row 1 is header when i==0, data starts at row 2
        if i == 0:
            batch = [header] + batch
            start_row = 1

        end_col = chr(ord('A') + len(header) - 1) if len(header) <= 26 else 'ZZ'
        cell_range = f'{tab_name}!A{start_row}:{end_col}{start_row + len(batch) - 1}'

        body_json = json.dumps({'values': batch})

        result = subprocess.run(
            [
                'gws', 'sheets', 'spreadsheets', 'values', 'update',
                '--params', json.dumps({
                    'spreadsheetId': SPREADSHEET_ID,
                    'range': cell_range,
                    'valueInputOption': 'RAW',
                }),
                '--json', body_json,
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            # Filter out the keyring info line
            err_lines = [l for l in stderr.splitlines() if 'keyring' not in l.lower()]
            print(f"  Error writing {tab_name} batch {i}: {' '.join(err_lines)}")
            return False

        rows_in_batch = len(batch) - (1 if i == 0 else 0)
        total_written += rows_in_batch

    print(f"  Wrote {total_written} rows to {tab_name}")
    return True


def format_tab(tab_name, num_rows, num_cols):
    """Apply formatting: freeze + bold header, center-align all columns, auto-resize."""
    sheet_id = get_sheet_id(tab_name)
    if sheet_id is None:
        print(f"  Could not find sheetId for {tab_name}, skipping formatting")
        return

    requests = [
        # Freeze the header row
        {
            'updateSheetProperties': {
                'properties': {
                    'sheetId': sheet_id,
                    'gridProperties': {'frozenRowCount': 1, 'frozenColumnCount': 1},
                },
                'fields': 'gridProperties.frozenRowCount,gridProperties.frozenColumnCount',
            }
        },
        # Bold the header row
        {
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 0,
                    'endRowIndex': 1,
                },
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {'bold': True},
                    }
                },
                'fields': 'userEnteredFormat.textFormat.bold',
            }
        },
        # Center-align all cells
        {
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 0,
                    'endRowIndex': num_rows,
                    'startColumnIndex': 0,
                    'endColumnIndex': num_cols,
                },
                'cell': {
                    'userEnteredFormat': {
                        'horizontalAlignment': 'CENTER',
                    }
                },
                'fields': 'userEnteredFormat.horizontalAlignment',
            }
        },
        # Auto-resize all columns to fit content
        {
            'autoResizeDimensions': {
                'dimensions': {
                    'sheetId': sheet_id,
                    'dimension': 'COLUMNS',
                    'startIndex': 0,
                    'endIndex': num_cols,
                }
            }
        },
    ]

    result = subprocess.run(
        ['gws', 'sheets', 'spreadsheets', 'batchUpdate',
         '--params', json.dumps({'spreadsheetId': SPREADSHEET_ID}),
         '--json', json.dumps({'requests': requests})],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        stderr = [l for l in result.stderr.splitlines() if 'keyring' not in l.lower()]
        print(f"  Warning formatting {tab_name}: {' '.join(stderr)}")
    else:
        print(f"  Formatted {tab_name}")


COLUMN_PADDING = {
    'Player': 0,
    'Status': 0,
}
COLUMN_MIN_WIDTH = {
    'Status': 150,
}
DEFAULT_PADDING = 15


def pad_columns(tab_name):
    """Add padding pixels to each column after auto-resize.

    Uses COLUMN_PADDING for per-column overrides (by header name) and
    DEFAULT_PADDING for everything else.
    """
    sheet_id = get_sheet_id(tab_name)
    if sheet_id is None:
        return

    # Read the header row to map column names to indices
    header_result = subprocess.run(
        ['gws', 'sheets', 'spreadsheets', 'values', 'get',
         '--params', json.dumps({
             'spreadsheetId': SPREADSHEET_ID,
             'range': f'{tab_name}!1:1',
         })],
        capture_output=True, text=True,
    )
    if header_result.returncode != 0:
        return
    lines = [l for l in header_result.stdout.splitlines()
             if not l.strip().startswith('Using keyring')]
    header_data = json.loads('\n'.join(lines))
    headers = header_data.get('values', [[]])[0]
    if not headers:
        return

    num_cols = len(headers)
    name_padding = {}
    name_min_width = {}
    for i, name in enumerate(headers):
        name_padding[i] = COLUMN_PADDING.get(name, DEFAULT_PADDING)
        if name in COLUMN_MIN_WIDTH:
            name_min_width[i] = COLUMN_MIN_WIDTH[name]

    # Fetch current column widths
    result = subprocess.run(
        ['gws', 'sheets', 'spreadsheets', 'get',
         '--params', json.dumps({
             'spreadsheetId': SPREADSHEET_ID,
             'fields': 'sheets.properties,sheets.data.columnMetadata',
         })],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return

    lines = [l for l in result.stdout.splitlines() if not l.strip().startswith('Using keyring')]
    data = json.loads('\n'.join(lines))

    col_metadata = []
    for sheet in data.get('sheets', []):
        if sheet['properties']['title'] == tab_name:
            col_metadata = sheet.get('data', [{}])[0].get('columnMetadata', [])
            break

    if not col_metadata:
        return

    requests = []
    for i in range(min(num_cols, len(col_metadata))):
        col_padding = name_padding.get(i, DEFAULT_PADDING)
        current_width = col_metadata[i].get('pixelSize', 100)
        new_width = current_width + col_padding
        if i in name_min_width:
            new_width = max(new_width, name_min_width[i])
        requests.append({
            'updateDimensionProperties': {
                'range': {
                    'sheetId': sheet_id,
                    'dimension': 'COLUMNS',
                    'startIndex': i,
                    'endIndex': i + 1,
                },
                'properties': {'pixelSize': new_width},
                'fields': 'pixelSize',
            }
        })

    if not requests:
        return

    subprocess.run(
        ['gws', 'sheets', 'spreadsheets', 'batchUpdate',
         '--params', json.dumps({'spreadsheetId': SPREADSHEET_ID}),
         '--json', json.dumps({'requests': requests})],
        capture_output=True, text=True,
    )
    print(f"  Padded {len(requests)} columns in {tab_name}")


def normalize_name(name):
    """Normalize a player name for fuzzy matching."""
    if not isinstance(name, str):
        return ''
    name = name.lower()
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    name = re.sub(r'\s+(jr\.?|sr\.?|[ivx]+)$', '', name)
    name = re.sub(r'\s+\([^)]+\)', '', name)
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def read_status_column(tab_name):
    """Read the existing Status column from the sheet and return a
    {normalized_player_name: status_value} mapping.  Returns an empty
    dict if the Status column doesn't exist yet."""
    result = subprocess.run(
        ['gws', 'sheets', 'spreadsheets', 'values', 'get',
         '--params', json.dumps({
             'spreadsheetId': SPREADSHEET_ID,
             'range': f'{tab_name}!1:1',
         })],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return {}
    lines = [l for l in result.stdout.splitlines()
             if not l.strip().startswith('Using keyring')]
    data = json.loads('\n'.join(lines))
    rows = data.get('values', [])
    if not rows:
        return {}

    header = rows[0]
    if 'Status' not in header:
        return {}

    status_idx = header.index('Status')
    player_idx = header.index('Player') if 'Player' in header else 0
    player_col = chr(ord('A') + player_idx)
    status_col = chr(ord('A') + status_idx)

    result = subprocess.run(
        ['gws', 'sheets', 'spreadsheets', 'values', 'get',
         '--params', json.dumps({
             'spreadsheetId': SPREADSHEET_ID,
             'range': f'{tab_name}!{player_col}:{status_col}',
         })],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return {}
    lines = [l for l in result.stdout.splitlines()
             if not l.strip().startswith('Using keyring')]
    data = json.loads('\n'.join(lines))
    rows = data.get('values', [])
    if not rows:
        return {}

    mapping = {}
    name_offset = 0
    status_offset = status_idx - player_idx
    for row in rows[1:]:
        if len(row) <= status_offset:
            continue
        name, status = row[name_offset], row[status_offset]
        if name and status:
            mapping[normalize_name(name)] = status

    print(f"  Saved {len(mapping)} existing Status values from {tab_name}")
    return mapping


def restore_status_column(tab_name, values, status_map):
    """Re-inject the Status column into the sheet after a fresh upload.
    `values` is the list-of-lists that was just written (header + rows).
    `status_map` is {normalized_name: status} from the prior read."""
    if not status_map:
        return

    header = values[0]
    name_idx = header.index('Player') if 'Player' in header else 0

    sheet_id = get_sheet_id(tab_name)
    if sheet_id is None:
        return

    # Clear all conditional formatting rules before the column insert so
    # they don't shift from col B (Status) to col C (the next data column).
    # The Apps Script will re-apply them on its next run.
    clear_cf = subprocess.run(
        ['gws', 'sheets', 'spreadsheets', 'get',
         '--params', json.dumps({'spreadsheetId': SPREADSHEET_ID,
                                 'fields': 'sheets.conditionalFormats,sheets.properties'})],
        capture_output=True, text=True,
    )
    if clear_cf.returncode == 0:
        lines = [l for l in clear_cf.stdout.splitlines()
                 if not l.strip().startswith('Using keyring')]
        cf_data = json.loads('\n'.join(lines))
        delete_requests = []
        for s in cf_data.get('sheets', []):
            if s['properties']['title'] != tab_name:
                continue
            for i, _ in enumerate(s.get('conditionalFormats', [])):
                delete_requests.append({
                    'deleteConditionalFormatRule': {
                        'sheetId': sheet_id,
                        'index': 0,  # always 0 because list shrinks after each delete
                    }
                })
        if delete_requests:
            subprocess.run(
                ['gws', 'sheets', 'spreadsheets', 'batchUpdate',
                 '--params', json.dumps({'spreadsheetId': SPREADSHEET_ID}),
                 '--json', json.dumps({'requests': delete_requests})],
                capture_output=True, text=True,
            )
            print(f"  Cleared {len(delete_requests)} conditional format rules from {tab_name}")

    # Insert a new column right after Player
    insert_idx = name_idx + 1
    insert_result = subprocess.run(
        ['gws', 'sheets', 'spreadsheets', 'batchUpdate',
         '--params', json.dumps({'spreadsheetId': SPREADSHEET_ID}),
         '--json', json.dumps({'requests': [{
             'insertDimension': {
                 'range': {
                     'sheetId': sheet_id,
                     'dimension': 'COLUMNS',
                     'startIndex': insert_idx,
                     'endIndex': insert_idx + 1,
                 },
                 'inheritFromBefore': False,
             }
         }]})],
        capture_output=True, text=True,
    )
    if insert_result.returncode != 0:
        stderr = [l for l in insert_result.stderr.splitlines() if 'keyring' not in l.lower()]
        print(f"  Warning inserting Status column: {' '.join(stderr)}")
        return

    # Build the Status column values
    status_col = [['Status']]
    restored = 0
    for row in values[1:]:
        player_name = row[name_idx] if name_idx < len(row) else ''
        norm = normalize_name(str(player_name))
        status = status_map.get(norm, '')
        if status:
            restored += 1
        status_col.append([status])

    # Write the column
    write_col_letter = chr(ord('A') + insert_idx)
    cell_range = f'{tab_name}!{write_col_letter}1:{write_col_letter}{len(status_col)}'
    body_json = json.dumps({'values': status_col})
    subprocess.run(
        ['gws', 'sheets', 'spreadsheets', 'values', 'update',
         '--params', json.dumps({
             'spreadsheetId': SPREADSHEET_ID,
             'range': cell_range,
             'valueInputOption': 'RAW',
         }),
         '--json', body_json],
        capture_output=True, text=True,
    )
    print(f"  Restored {restored} Status values to {tab_name}")


def upload_all():
    """Upload all cheatsheet CSVs to Google Sheets."""
    print(f"Uploading to Google Sheet: {SPREADSHEET_ID}")

    for tab_name, csv_path in TABS.items():
        if not os.path.exists(csv_path):
            print(f"  Skipping {tab_name}: {csv_path} not found")
            continue

        print(f"\n{tab_name}:")

        # Save existing Status column before overwriting
        status_map = read_status_column(tab_name)

        values = csv_to_values(csv_path)
        num_rows = len(values) + 10
        num_cols = len(values[0]) if values else 26
        resize_tab(tab_name, num_rows, num_cols)
        clear_tab(tab_name)
        write_tab(tab_name, values)
        format_tab(tab_name, num_rows, num_cols)

        # Restore the Status column if it existed
        restore_status_column(tab_name, values, status_map)

        pad_columns(tab_name)

    print(f"\nhttps://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")


if __name__ == '__main__':
    upload_all()
