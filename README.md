# Governed LangGraph Agent with Local GA4 MCP

This project is a LangGraph + OpenAI reference implementation for governed tool-calling agents. It can use local SQLite tools and, when configured, a separate local Google Analytics 4 MCP server.

The GA4 server is intentionally separated from the LangGraph agent:

```text
LangGraph agent -> MCP client config -> local GA4 OAuth MCP server -> Google Analytics APIs
```

The agent consumes MCP tools. The GA4 MCP server owns Google OAuth, token refresh, input validation, the configured GA4 property, and Google API calls.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Google Cloud OAuth Setup

1. Open Google Cloud Console and select or create a project.
2. Enable these APIs:
   - Google Analytics Data API
   - Google Analytics Admin API
3. Configure the OAuth consent screen.
   - For personal use, keep it in testing mode.
   - Add your own Google account as a test user if required.
   - The only Analytics scope needed is:

```text
https://www.googleapis.com/auth/analytics.readonly
```

4. Create OAuth credentials:
   - Application type: Desktop app
   - Copy the client ID and client secret.
5. Confirm the Google user you will authenticate with has Viewer or higher access to the GA4 property.

User OAuth is preferred here because this is for your own Google Analytics account and the first run should open a browser consent flow. Service accounts are better for unattended server automation, but they require granting a separate service account identity access to GA4 and are not the cleanest fit for a personal desktop MCP workflow.

## Environment

Copy `.env.example` to `.env` and fill in the values you need.

For the local GA4 OAuth MCP server:

```dotenv
GA_MCP_TRANSPORT=stdio
GA_MCP_COMMAND=python
GA_MCP_ARGS=-m ga4_mcp_server

GOOGLE_CLIENT_ID=your-google-oauth-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-oauth-client-secret
GOOGLE_PROJECT_ID=your-google-cloud-project-id
GA4_PROPERTY_ID=123456789
GA4_OAUTH_HOST=127.0.0.1
GA4_OAUTH_PORT=8080
```

`GA4_PROPERTY_ID` is the default property used by report tools when the caller omits `property_id`. This is deliberate: property selection belongs in MCP config, so the agent does not guess.

Optional:

```dotenv
GA4_TOKEN_PATH=C:\Users\you\AppData\Local\ga4-mcp\token.json
```

If unset, the server stores the OAuth token under a local user app/state directory. Token files are gitignored and must not be committed.

The OAuth callback defaults to:

```text
http://127.0.0.1:8080/
```

If you create a Google OAuth **Desktop app** client, Google supports loopback redirects for local apps and this is the recommended setup. If you use a **Web application** OAuth client instead, add the exact redirect URI above under Authorized redirect URIs in Google Cloud Console, or set `GA4_OAUTH_HOST` / `GA4_OAUTH_PORT` to match the URI you registered.

## Run the Local GA4 MCP Server

The server uses stdio for MCP clients:

```powershell
python -m ga4_mcp_server
```

On the first GA4 tool call, if no token exists, a browser OAuth consent flow opens. After login, credentials are saved locally for future runs. Access and refresh tokens are never printed.

## Run the LangGraph Agent

```powershell
python -m src.main
```

With `GA_MCP_TRANSPORT=stdio`, the LangGraph app launches the local GA4 MCP server and loads its tools. With no GA MCP config, the app runs SQLite-only.

## MCP Client Configuration

Claude Desktop / Cursor style:

```json
{
  "mcpServers": {
    "ga4": {
      "command": "python",
      "args": ["-m", "ga4_mcp_server"],
      "env": {
        "GOOGLE_CLIENT_ID": "your-google-oauth-client-id.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "your-google-oauth-client-secret",
        "GOOGLE_PROJECT_ID": "your-google-cloud-project-id",
        "GA4_PROPERTY_ID": "123456789"
      }
    }
  }
}
```

MCP Inspector example:

```powershell
npx @modelcontextprotocol/inspector python -m ga4_mcp_server
```

If the Inspector does not inherit your `.env`, pass the environment variables through the shell or configure them in the Inspector.

## GA4 MCP Tools

The server exposes exactly four read-only tools:

- `list_ga4_accounts`
- `list_ga4_properties`
- `run_ga4_report`
- `run_realtime_report`

There is no generic Google API proxy and no write-capable Analytics operation.

Example standard report arguments:

```json
{
  "start_date": "7daysAgo",
  "end_date": "today",
  "dimensions": ["date"],
  "metrics": ["activeUsers"]
}
```

Example realtime report arguments:

```json
{
  "dimensions": ["country"],
  "metrics": ["activeUsers"]
}
```

Example filter:

```json
{
  "start_date": "2026-06-01",
  "end_date": "2026-06-07",
  "dimensions": ["country"],
  "metrics": ["activeUsers"],
  "filters": {
    "field_name": "country",
    "string_value": "Portugal",
    "match_type": "EXACT"
  }
}
```

## Example Prompts

- List my GA4 accounts.
- List the GA4 properties I can access.
- Show active users by date for the last 7 days.
- Show realtime active users by country.

For report prompts, the agent should omit `property_id` unless you explicitly name another property. The MCP server uses `GA4_PROPERTY_ID` from its config by default.

## OAuth Flow Notes

1. A GA4 tool asks for credentials.
2. The server checks the local token file.
3. If the token is valid, the Google API call runs immediately.
4. If the token is expired and refreshable, the server refreshes it and saves the updated token.
5. If no token exists, the server starts a temporary localhost OAuth callback server and opens Google consent in the browser.
6. Google redirects back to localhost with an authorization code.
7. The server exchanges the code for tokens and stores them locally.

Common errors:

- Expired or revoked token: delete the local token file and call a GA4 tool again.
- Missing permissions: grant your Google user access to the GA4 account/property.
- Invalid property ID: check `GA4_PROPERTY_ID` in `.env`.
- API disabled: enable both Analytics APIs in Google Cloud Console.
- Quota error: wait or reduce request volume.
