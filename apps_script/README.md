# Fantasy Cheatsheet — Ownership Status (Google Apps Script)

Adds a **Status** column to the Hitters and Pitchers tabs in the cheatsheet
spreadsheet, showing whether each player is rostered (with the team name),
on waivers, or a free agent in your Yahoo Fantasy league.

Runs entirely in the cloud via Google Apps Script — no local machine needed.

## Setup

### 1. Open the Apps Script editor

1. Open the cheatsheet spreadsheet in Google Sheets.
2. Go to **Extensions > Apps Script**.
3. This opens the script editor in a new tab.

### 2. Add the OAuth2 library

1. In the script editor, click the **+** next to **Libraries** in the left sidebar.
2. Paste the library ID:
   ```
   1B7FSrk5Zi6L1rSxxTDgDEUsPzlukDsi4KGuTMorsTQHhGBzBkMun4iDF
   ```
3. Click **Look up**, select the latest version, and click **Add**.

### 3. Create the script files

Create two files in the script editor (click **+** next to **Files** > **Script**):

- **Code.gs** — paste the contents of `Code.gs` from this directory.
- **OAuth.gs** — paste the contents of `OAuth.gs` from this directory.

Delete the default empty `Code.gs` if one was auto-created.

### 4. Get the redirect URI

Before creating Yahoo credentials, you need the callback URL:

1. Reload the spreadsheet so the **Fantasy Tools** menu appears.
2. Click **Fantasy Tools > Show Redirect URI (setup step)**.
3. Copy the URL shown (it looks like
   `https://script.google.com/macros/d/{SCRIPT_ID}/usercallback`).

You'll paste this into the Yahoo app in the next step.

### 5. Get Yahoo API credentials

You need a **Web Application** on Yahoo (not "Installed Application") so it
accepts the Apps Script redirect URI.

> **Note:** The draft tracker's `oauth2.json` credentials were created as an
> Installed Application and won't work here. You need a separate Web Application.

1. Go to [Yahoo Developer Apps](https://developer.yahoo.com/apps/create/).
2. Create an app:
   - **Application Name**: anything (e.g. "Fantasy Cheatsheet")
   - **Application Type**: **Web Application**
   - **Home Page URL**: `https://docs.google.com` (anything valid)
   - **Redirect URI(s)**: paste the callback URL from step 4
   - **API Permissions**: check **Fantasy Sports** (Read)
3. Copy the **Client ID (Consumer Key)** and **Client Secret (Consumer Secret)**.

### 6. Configure script properties

1. In the Apps Script editor, go to **Project Settings** (gear icon in the left sidebar).
2. Scroll to **Script Properties** and add these three:

| Property             | Value                                        |
|----------------------|----------------------------------------------|
| `YAHOO_CLIENT_ID`    | Your Yahoo consumer key                      |
| `YAHOO_CLIENT_SECRET` | Your Yahoo consumer secret                  |
| `YAHOO_LEAGUE_KEY`   | Your league key (e.g. `449.l.12345`)         |

To find your league key: go to your Yahoo Fantasy league page. The URL will be
something like `https://baseball.fantasysports.yahoo.com/b1/12345`. The league
key is `{game_id}.l.{league_number}`. For MLB 2026 the game ID is typically
`449` — so the key would be `449.l.12345`.

Alternatively, after authorizing Yahoo, you can check the league key via the
Yahoo Fantasy API or from the `draft_tracker.py` output.

### 7. Authorize Yahoo

1. Reload the spreadsheet (close and reopen, or refresh the page).
2. A **Fantasy Tools** menu should appear in the menu bar.
3. Click **Fantasy Tools > Authorize Yahoo**.
4. Click the authorization link in the dialog, sign in to Yahoo, and grant access.
5. Return to the spreadsheet.

### 8. Test it

Click **Fantasy Tools > Update Ownership Status**. The script will:
- Fetch rostered, waiver, and free agent players from Yahoo.
- Add a **Status** column (column B) to each tab.
- Color-code: green for FA, orange for Waivers, grey text for rostered.

Check **View > Executions** in the Apps Script editor to see logs if anything
goes wrong.

### 9. Set up automatic updates

1. In the Apps Script editor, click the **clock icon** (Triggers) in the left sidebar.
2. Click **+ Add Trigger**.
3. Configure:
   - **Function**: `updateOwnershipStatus`
   - **Event source**: Time-driven
   - **Type**: Hour timer
   - **Interval**: Every 4 hours (or your preference)
4. Click **Save**.

The status column will now refresh automatically throughout the day.

## How it works

1. Calls the Yahoo Fantasy API to get three player lists:
   - **Taken** (status=T): players on someone's team — includes the owner team name.
   - **Waivers** (status=W): players on the waiver wire.
   - **Free Agents** (status=FA): players available for immediate pickup.
2. Reads the `Player` column from each sheet tab.
3. Matches using normalized names (lowercase, no accents, no Jr./Sr. suffixes)
   — same logic as `draft_tracker.py`.
4. Writes the status to column B and applies conditional formatting.

## Interaction with local uploads

When `upload_to_sheets.py` runs locally, it clears and rewrites each tab,
which removes the Status column. The updated `upload_to_sheets.py` now
preserves the Status column across uploads. If the Status column is lost
for any reason, the next scheduled trigger (or a manual run from the menu)
will recreate it.

## Troubleshooting

- **"Yahoo OAuth not authorized"**: Run Fantasy Tools > Authorize Yahoo.
- **"League key not configured"**: Run Fantasy Tools > Set League Key,
  or add `YAHOO_LEAGUE_KEY` in Script Properties.
- **Players showing blank status**: The name in the cheatsheet doesn't match
  Yahoo's name. Check the execution log for unmatched player names.
- **"Exceeded maximum execution time"**: The 6-minute Apps Script limit was
  hit. This shouldn't happen for normal league sizes, but if it does,
  reduce the number of free agents fetched by adjusting the pagination
  limit in `fetchAllYahooPlayers_`.
