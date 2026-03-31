// ---------------------------------------------------------------------------
// Yahoo OAuth2 configuration
//
// Uses the apps-script-oauth2 library. Add it to your script project:
//   Library ID: 1B7FSrk5Zi6L1rSxxTDgDEUsPzlukDsi4KGuTMorsTQHhGBzBkMun4iDF
//   Version: latest
// ---------------------------------------------------------------------------

var YAHOO_AUTH_URL = 'https://api.login.yahoo.com/oauth2/request_auth';
var YAHOO_TOKEN_URL = 'https://api.login.yahoo.com/oauth2/get_token';

/**
 * Build and return the Yahoo OAuth2 service.
 */
function getYahooService_() {
  var props = PropertiesService.getScriptProperties();
  var clientId = props.getProperty('YAHOO_CLIENT_ID');
  var clientSecret = props.getProperty('YAHOO_CLIENT_SECRET');

  if (!clientId || !clientSecret) {
    throw new Error(
      'Yahoo API credentials not configured. Set YAHOO_CLIENT_ID and ' +
      'YAHOO_CLIENT_SECRET in Script Properties (Project Settings > Script Properties).'
    );
  }

  return OAuth2.createService('yahoo')
    .setAuthorizationBaseUrl(YAHOO_AUTH_URL)
    .setTokenUrl(YAHOO_TOKEN_URL)
    .setClientId(clientId)
    .setClientSecret(clientSecret)
    .setCallbackFunction('authCallback')
    .setPropertyStore(PropertiesService.getUserProperties())
    .setScope('fspt-r')        // Fantasy Sports read-only
    .setTokenHeaders({
      'Authorization': 'Basic ' + Utilities.base64Encode(clientId + ':' + clientSecret)
    });
}

/**
 * OAuth2 callback — the redirect target after Yahoo authorizes.
 */
function authCallback(request) {
  var service = getYahooService_();
  var authorized = service.handleCallback(request);
  if (authorized) {
    return HtmlService.createHtmlOutput(
      '<h2>Yahoo authorization successful!</h2>' +
      '<p>You can close this tab and return to the spreadsheet.</p>'
    );
  } else {
    return HtmlService.createHtmlOutput(
      '<h2>Authorization denied.</h2>' +
      '<p>Please try again from the Fantasy Tools menu.</p>'
    );
  }
}

/**
 * Show the redirect URI that must be registered in the Yahoo developer app.
 * Run this FIRST, then paste the URL into your Yahoo app's Redirect URI field.
 */
function showRedirectUri() {
  var redirectUri = ScriptApp.getService().getUrl();
  // The OAuth2 library appends /usercallback to the script's web app URL
  // but the actual redirect URI it uses is based on the script ID.
  var scriptId = ScriptApp.getScriptId();
  var callbackUrl = 'https://script.google.com/macros/d/' + scriptId + '/usercallback';
  var html = HtmlService.createHtmlOutput(
    '<p><b>Copy this URL</b> and paste it into your Yahoo developer app\'s ' +
    '<b>Redirect URI(s)</b> field:</p>' +
    '<p style="word-break:break-all;font-family:monospace;background:#f0f0f0;padding:8px;">' +
    callbackUrl + '</p>' +
    '<p>Then click <b>Fantasy Tools &gt; Authorize Yahoo</b> to continue.</p>'
  ).setWidth(520).setHeight(200);
  SpreadsheetApp.getUi().showModalDialog(html, 'Yahoo Redirect URI');
}

/**
 * Show the Yahoo authorization URL so the user can click through.
 * Called from the Fantasy Tools menu.
 */
function showYahooAuthUrl() {
  var service = getYahooService_();
  if (service.hasAccess()) {
    SpreadsheetApp.getUi().alert('Yahoo is already authorized. You\'re all set!');
    return;
  }
  var authUrl = service.getAuthorizationUrl();
  var html = HtmlService.createHtmlOutput(
    '<p>Click the link below to authorize Yahoo Fantasy access:</p>' +
    '<p style="word-break:break-all;"><a href="' + authUrl + '" target="_blank">' + authUrl + '</a></p>' +
    '<p>After authorizing, return here and run "Update Ownership Status" from the menu.</p>'
  ).setWidth(500).setHeight(200);
  SpreadsheetApp.getUi().showModalDialog(html, 'Authorize Yahoo Fantasy');
}

/**
 * Reset Yahoo OAuth tokens (useful for re-authorization).
 */
function resetYahooAuth() {
  var service = getYahooService_();
  service.reset();
  Logger.log('Yahoo OAuth tokens cleared.');
}
