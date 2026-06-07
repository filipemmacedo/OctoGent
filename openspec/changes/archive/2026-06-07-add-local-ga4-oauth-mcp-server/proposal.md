## Why

The project currently consumes GA4 tools from an external MCP server, but it does not provide its own OAuth-based GA4 MCP server. Building a local server gives the reference agent a clean, inspectable boundary for Google Analytics access while keeping OAuth credentials and property selection outside the LangGraph agent loop.

## What Changes

- Add a local GA4 MCP server that authenticates with Google OAuth 2.0 as the user's own Google account.
- Expose a minimal read-only GA4 tool surface: `list_ga4_accounts`, `list_ga4_properties`, `run_ga4_report`, and `run_realtime_report`.
- Use only the `https://www.googleapis.com/auth/analytics.readonly` scope with the Google Analytics Data API and Google Analytics Admin API.
- Store OAuth tokens locally in a development-friendly location that is excluded from git and never logged.
- Require the default GA4 property ID to be configured in MCP server environment/config, so the agent does not guess which property to query.
- Keep the LangGraph application as an MCP client only; it loads GA4 tools from the local server through the existing MCP configuration path.
- Add setup documentation, `.env.example` entries, and MCP client configuration examples for Claude Desktop, Cursor, and MCP Inspector.

## Capabilities

### New Capabilities
- `local-ga4-oauth-mcp-server`: Covers the standalone local MCP server, OAuth login/token handling, read-only GA4 tools, input validation, and safe error handling.

### Modified Capabilities
- `mcp-ga4-tools`: Require GA4 property selection to come from MCP/client configuration instead of model inference when no explicit property ID is supplied by the user.

## Impact

- New GA4 MCP server package/module and README documentation.
- New dependencies for MCP server hosting, Google OAuth, Google Analytics Admin API, and Google Analytics Data API.
- `.env.example` additions for `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_PROJECT_ID`, and `GA4_PROPERTY_ID`.
- `.gitignore` updates for local OAuth token/cache files.
- Existing `src/mcp_tools.py` and system prompt may need small updates to reflect the local stdio MCP server and configured-property rule.
