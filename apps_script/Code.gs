// ---------------------------------------------------------------------------
// Yahoo Fantasy Ownership Enrichment for Cheatsheet
//
// Adds a "Status" column to the Hitters and Pitchers tabs showing whether
// each player is rostered (shows team name), on waivers, or a free agent.
// ---------------------------------------------------------------------------

var YAHOO_API_BASE = 'https://fantasysports.yahooapis.com/fantasy/v2';
var STATUS_COL_HEADER = 'Status';
var TAB_NAMES = ['Hitters', 'Pitchers'];

// Status filters the Yahoo API accepts
var YAHOO_STATUS = {
  TAKEN: 'T',
  WAIVERS: 'W'
};

// ---------------------------------------------------------------------------
// Entry points
// ---------------------------------------------------------------------------

/**
 * Main function — call manually or via time trigger.
 * Fetches ownership from Yahoo and writes the Status column on each tab.
 */
function updateOwnershipStatus() {
  var leagueKey = getLeagueKey_();
  if (!leagueKey) {
    throw new Error(
      'League key not configured. Run Setup > Set League Key from the menu, ' +
      'or set the YAHOO_LEAGUE_KEY script property manually.'
    );
  }

  Logger.log('Fetching ownership data for league: ' + leagueKey);

  // Discover the logged-in user's team name
  var myTeamName = getMyTeamName_(leagueKey);
  Logger.log('My team: ' + myTeamName);

  var takenMap = {};    // normalizedName -> team name
  var waiverMap = {};   // normalizedName -> waiver date string or true

  // Fetch rostered players (includes owner team name)
  var taken = fetchAllYahooPlayers_(leagueKey, YAHOO_STATUS.TAKEN);
  taken.forEach(function (p) {
    takenMap[normalizeName(p.name)] = p.ownerTeam || 'Rostered';
  });
  Logger.log('Rostered players: ' + Object.keys(takenMap).length);

  // Fetch waiver players
  var waivers = fetchAllYahooPlayers_(leagueKey, YAHOO_STATUS.WAIVERS);
  waivers.forEach(function (p) {
    waiverMap[normalizeName(p.name)] = p.waiverDate || true;
  });
  Logger.log('Waiver players: ' + Object.keys(waiverMap).length);

  // Anyone not rostered or on waivers is assumed to be a free agent —
  // skip fetching the full FA pool (thousands of pages) to stay well
  // within the Apps Script 6-minute execution limit.

  var ss = SpreadsheetApp.getActiveSpreadsheet();

  TAB_NAMES.forEach(function (tabName) {
    var sheet = ss.getSheetByName(tabName);
    if (!sheet) {
      Logger.log('Tab not found: ' + tabName + ', skipping.');
      return;
    }
    writeStatusColumn_(sheet, takenMap, waiverMap, myTeamName);
  });

  Logger.log('Ownership update complete.');
}

/**
 * Adds a custom menu to the spreadsheet UI.
 */
function onOpen() {
  SpreadsheetApp.getUi().createMenu('Fantasy Tools')
    .addItem('Update Ownership Status', 'updateOwnershipStatus')
    .addSeparator()
    .addItem('Set League Key…', 'promptLeagueKey')
    .addItem('Show Redirect URI (setup step)', 'showRedirectUri')
    .addItem('Authorize Yahoo', 'showYahooAuthUrl')
    .addToUi();
}

// ---------------------------------------------------------------------------
// Yahoo API – paginated player fetch
// ---------------------------------------------------------------------------

/**
 * Fetch all players with a given status from the Yahoo Fantasy API.
 * Paginates automatically (25 per page by default).
 *
 * Returns an array of {name, playerId, ownerTeam} objects.
 */
function getMyTeamName_(leagueKey) {
  var service = getYahooService_();
  var url = YAHOO_API_BASE + '/league/' + leagueKey + '/teams?format=json';
  var response = UrlFetchApp.fetch(url, {
    headers: { 'Authorization': 'Bearer ' + service.getAccessToken() },
    muteHttpExceptions: true
  });
  if (response.getResponseCode() !== 200) return '';

  var json = JSON.parse(response.getContentText());
  var leagueData = json.fantasy_content.league;
  var teamsObj = leagueData[1].teams;
  var count = parseInt(teamsObj.count, 10);

  for (var i = 0; i < count; i++) {
    var team = teamsObj[String(i)].team;
    if (!team) continue;
    var info = team[0];
    var isOwned = false;
    var teamName = '';
    for (var j = 0; j < info.length; j++) {
      if (info[j].name) teamName = info[j].name;
      if (info[j].is_owned_by_current_login !== undefined) {
        isOwned = (String(info[j].is_owned_by_current_login) === '1');
      }
    }
    if (isOwned) return teamName;
  }
  return '';
}

function fetchAllYahooPlayers_(leagueKey, status) {
  var service = getYahooService_();
  if (!service.hasAccess()) {
    throw new Error(
      'Yahoo OAuth not authorized. Run Fantasy Tools > Authorize Yahoo from the menu.'
    );
  }

  var players = [];
  var start = 0;
  var pageSize = 25;
  var hasMore = true;

  while (hasMore) {
    var url = YAHOO_API_BASE + '/league/' + leagueKey +
              '/players;status=' + status +
              ';start=' + start + ';count=' + pageSize +
              ';out=ownership?format=json';

    var response = UrlFetchApp.fetch(url, {
      headers: { 'Authorization': 'Bearer ' + service.getAccessToken() },
      muteHttpExceptions: true
    });

    var code = response.getResponseCode();
    if (code !== 200) {
      // Yahoo returns 400 when start is beyond total players
      if (code === 400 && start > 0) break;
      Logger.log('Yahoo API error (' + code + '): ' + response.getContentText().substring(0, 500));
      break;
    }

    var json = JSON.parse(response.getContentText());
    var leagueData = json.fantasy_content.league;

    // leagueData is an array: [leagueMeta, {players: ...}]
    var playersObj = leagueData[1].players;
    if (!playersObj) break;

    var count = parseInt(playersObj.count, 10);
    if (count === 0) break;

    for (var i = 0; i < count; i++) {
      var pData = playersObj[String(i)];
      if (!pData || !pData.player) continue;

      var info = parseYahooPlayer_(pData.player);
      if (info) players.push(info);
    }

    start += pageSize;
    if (count < pageSize) hasMore = false;
  }

  return players;
}

/**
 * Parse a single player entry from the Yahoo API response.
 */
function parseYahooPlayer_(playerArray) {
  // playerArray is [infoArray, ownershipObj?]
  var infoArray = playerArray[0];
  var name = '';
  var playerId = '';
  var ownerTeam = '';
  var waiverDate = '';

  for (var i = 0; i < infoArray.length; i++) {
    var item = infoArray[i];
    if (item.name) {
      name = item.name.full || '';
    }
    if (item.player_id !== undefined) {
      playerId = String(item.player_id);
    }
    if (item.ownership) {
      ownerTeam = item.ownership.owner_team_name || '';
      if (item.ownership.waiver_date) {
        waiverDate = item.ownership.waiver_date;
      }
    }
    if (item.transaction_data && item.transaction_data.source_team_name) {
      ownerTeam = ownerTeam || item.transaction_data.source_team_name;
    }
  }

  // Ownership may also be at playerArray[1]
  if (playerArray.length > 1 && playerArray[1]) {
    var ownership = playerArray[1].ownership;
    if (ownership) {
      if (!ownerTeam) ownerTeam = ownership.owner_team_name || '';
      if (!waiverDate && ownership.waiver_date) {
        waiverDate = ownership.waiver_date;
      }
    }
  }

  if (!name) return null;
  return { name: name, playerId: playerId, ownerTeam: ownerTeam, waiverDate: waiverDate };
}

// ---------------------------------------------------------------------------
// Sheet writing
// ---------------------------------------------------------------------------

/**
 * Read the sheet, find or create the Status column, and populate it.
 */
function writeStatusColumn_(sheet, takenMap, waiverMap, myTeamName) {
  var tabName = sheet.getName();
  var data = sheet.getDataRange().getValues();
  if (data.length < 2) return;

  var header = data[0];
  var nameColIdx = header.indexOf('Player');
  if (nameColIdx === -1) {
    Logger.log(tabName + ': no Player column found, skipping.');
    return;
  }

  // Find or create the Status column (right after Player)
  var statusColIdx = header.indexOf(STATUS_COL_HEADER);
  if (statusColIdx === -1) {
    var insertAfter = nameColIdx + 1; // 1-based column number
    sheet.insertColumnAfter(insertAfter);
    statusColIdx = nameColIdx + 1;
    sheet.getRange(1, statusColIdx + 1).setValue(STATUS_COL_HEADER);
    data = sheet.getDataRange().getValues();
    header = data[0];
    nameColIdx = header.indexOf('Player');
  }

  var statuses = [];
  var matched = 0;

  for (var r = 1; r < data.length; r++) {
    var playerName = String(data[r][nameColIdx]);
    var norm = normalizeName(playerName);
    var status = '';

    if (takenMap[norm] && myTeamName && takenMap[norm] === myTeamName) {
      status = 'My Team';
      matched++;
    } else if (takenMap[norm]) {
      status = takenMap[norm];
      matched++;
    } else if (waiverMap[norm]) {
      var wd = waiverMap[norm];
      if (typeof wd === 'string' && wd) {
        var parts = wd.split('-');
        status = 'Waivers (' + parseInt(parts[1], 10) + '/' + parseInt(parts[2], 10) + ')';
      } else {
        status = 'Waivers';
      }
      matched++;
    } else if (playerName) {
      status = 'FA';
      matched++;
    }

    statuses.push([status]);
  }

  // Write the entire Status column in one batch
  var range = sheet.getRange(2, statusColIdx + 1, statuses.length, 1);
  range.setValues(statuses);

  // Apply conditional formatting
  applyStatusFormatting_(sheet, statusColIdx, data.length);

  Logger.log(tabName + ': ' + matched + '/' + (data.length - 1) + ' players tagged.');
}

/**
 * Apply conditional formatting to the Status column:
 *   - "FA" -> green background
 *   - "Waivers" -> orange background
 *   - Team names (rostered) -> light grey text
 */
function applyStatusFormatting_(sheet, statusColIdx, numRows) {
  var lastCol = sheet.getLastColumn();
  var rowRange = sheet.getRange(2, 1, numRows - 1, lastCol);

  // Status column letter for formula references (e.g. "B")
  var statusColLetter = String.fromCharCode(65 + statusColIdx);

  // Clear existing conditional format rules that touch any column in the sheet
  var rules = sheet.getConditionalFormatRules();
  var newRules = rules.filter(function (rule) {
    var ruleRanges = rule.getRanges();
    for (var i = 0; i < ruleRanges.length; i++) {
      if (ruleRanges[i].getSheet().getName() === sheet.getName()) return false;
    }
    return true;
  });

  var myTeamRule = SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$' + statusColLetter + '2="My Team"')
    .setBackground('#c9daf8')
    .setRanges([rowRange])
    .build();

  var faRule = SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$' + statusColLetter + '2="FA"')
    .setBackground('#d9ead3')
    .setRanges([rowRange])
    .build();

  var waiverRule = SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=LEFT($' + statusColLetter + '2,7)="Waivers"')
    .setBackground('#fce5cd')
    .setRanges([rowRange])
    .build();

  var rosteredRule = SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied(
      '=AND(' +
        'LEN($' + statusColLetter + '2)>0,' +
        '$' + statusColLetter + '2<>"FA",' +
        'LEFT($' + statusColLetter + '2,7)<>"Waivers",' +
        '$' + statusColLetter + '2<>"My Team"' +
      ')'
    )
    .setFontColor('#999999')
    .setRanges([rowRange])
    .build();

  newRules.push(myTeamRule);
  newRules.push(faRule);
  newRules.push(waiverRule);
  newRules.push(rosteredRule);
  sheet.setConditionalFormatRules(newRules);
}

// ---------------------------------------------------------------------------
// Name normalisation (mirrors draft_tracker.py logic)
// ---------------------------------------------------------------------------

function normalizeName(name) {
  if (!name || typeof name !== 'string') return '';
  name = name.toLowerCase();
  // Strip accents: decompose then remove combining marks (U+0300..U+036F)
  name = name.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  // Remove Jr./Sr./roman numeral suffixes
  name = name.replace(/\s+(jr\.?|sr\.?|[ivx]+)$/, '');
  // Remove parenthetical suffixes like (Batter), (Pitcher)
  name = name.replace(/\s+\([^)]+\)/g, '');
  // Remove non-alphanumeric (keep spaces)
  name = name.replace(/[^\w\s]/g, '');
  // Collapse whitespace
  name = name.replace(/\s+/g, ' ').trim();
  return name;
}

// ---------------------------------------------------------------------------
// Config helpers
// ---------------------------------------------------------------------------

function getLeagueKey_() {
  return PropertiesService.getScriptProperties().getProperty('YAHOO_LEAGUE_KEY') || '';
}

function promptLeagueKey() {
  var ui = SpreadsheetApp.getUi();
  var current = getLeagueKey_();
  var result = ui.prompt(
    'Set Yahoo League Key',
    'Enter your Yahoo Fantasy league key (e.g. "449.l.12345").' +
    (current ? '\n\nCurrent: ' + current : ''),
    ui.ButtonSet.OK_CANCEL
  );
  if (result.getSelectedButton() === ui.Button.OK) {
    var key = result.getResponseText().trim();
    if (key) {
      PropertiesService.getScriptProperties().setProperty('YAHOO_LEAGUE_KEY', key);
      ui.alert('League key saved: ' + key);
    }
  }
}

// ---------------------------------------------------------------------------
// Time-driven trigger — run once from the Apps Script editor to install.
// After that, updateOwnershipStatus fires daily at ~6:35 AM ET automatically.
// ---------------------------------------------------------------------------

function createDailyTrigger() {
  // Remove any existing trigger for the same function to avoid duplicates
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === 'updateOwnershipStatus') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('updateOwnershipStatus')
    .timeBased()
    .atHour(6)
    .nearMinute(35)
    .everyDays(1)
    .inTimezone('America/New_York')
    .create();
  Logger.log('Daily trigger created for updateOwnershipStatus at ~6:35 AM ET.');
}

// ---------------------------------------------------------------------------
// Web app endpoint — deploy as a web app to trigger updates via URL/bookmark
// ---------------------------------------------------------------------------

function doGet() {
  try {
    updateOwnershipStatus();
    return HtmlService.createHtmlOutput(
      '<html><head><meta name="viewport" content="width=device-width,initial-scale=1">' +
      '<style>body{font-family:system-ui;text-align:center;padding:40px 20px;}</style></head>' +
      '<body><h2>Ownership updated!</h2>' +
      '<p>You can close this tab.</p></body></html>'
    ).setTitle('Fantasy Update');
  } catch (e) {
    return HtmlService.createHtmlOutput(
      '<html><head><meta name="viewport" content="width=device-width,initial-scale=1">' +
      '<style>body{font-family:system-ui;text-align:center;padding:40px 20px;}</style></head>' +
      '<body><h2>Error</h2><p>' + e.message + '</p></body></html>'
    ).setTitle('Fantasy Update');
  }
}
