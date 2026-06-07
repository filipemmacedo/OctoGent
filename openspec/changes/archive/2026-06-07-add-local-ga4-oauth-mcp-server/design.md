## Context

The current LangGraph application already knows how to consume GA4 tools from an MCP server through `src/mcp_tools.py`, but the GA4 MCP server itself is external. This change adds a local OAuth-based MCP server while preserving the agent application as a client. The server is for personal/local use: it authenticates as the user's Google account, requests read-only Analytics scope, stores tokens locally, and exposes only a small fixed GA4 tool surface.

The clean architecture boundary is:

```text
LangGraph agent -> MCP client config -> local GA4 MCP server -> Google Analytics APIs
```

OAuth credentials, token refresh, GA4 API clients, property configuration, input validation, and Google error mapping belong in the MCP server. The LangGraph agent should not know refresh tokens, call Google APIs directly, or infer which GA4 property to use.

## Goals / Non-Goals

**Goals:**
- Provide a local stdio MCP server for GA4 with OAuth user login.
- Use only the Google Analytics readonly OAuth scope.
- Expose only `list_ga4_accounts`, `list_ga4_properties`, `run_ga4_report`, and `run_realtime_report`.
- Require `GA4_PROPERTY_ID` in the MCP server configuration as the default property for report tools.
- Allow an explicit user-supplied `property_id` only when it is validated; otherwise report tools use the configured property.
- Keep the existing LangGraph app organized as an MCP consumer, not a GA4/OAuth implementation.
- Document setup, Google Cloud Console OAuth steps, MCP client configs, and example queries.

**Non-Goals:**
- No service account flow for this personal project.
- No arbitrary Google API proxying or generic Admin/Data API call tool.
- No write or management operations for GA accounts, properties, users, access bindings, or configuration.
- No enterprise token vault, multi-user auth, or hosted HTTP deployment in this change.
- No budget, HITL, honeypot, or persistence roadmap work in this change.

## Decisions

### Decision: Local MCP server is a separate package/module

Add a dedicated server module, for example `ga4_mcp_server/`, instead of embedding GA4 OAuth inside `src/graph.py` or `src/mcp_tools.py`.

Rationale: the agent should load tools through MCP exactly as it would for any external data source. This keeps Google auth and API details outside graph state and makes future governance controls easier to place around tool calls.

Alternative considered: put OAuth and GA4 client code directly into LangChain tools in `src/tools.py`. This is simpler initially, but it blurs the trust boundary and makes MCP configuration examples less meaningful.

### Decision: User OAuth desktop flow, not service accounts

Use Google OAuth 2.0 installed-app/local-server flow with `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_PROJECT_ID`, and `GA4_PROPERTY_ID` coming from environment variables.

Rationale: this is a personal project for the user's own Google Analytics account. User OAuth matches the desired "first run opens browser consent" workflow and avoids granting GA property permissions to a service account identity.

Alternative considered: service account credentials. Service accounts are useful for unattended backend jobs and shared automation, but they are a worse default for a personal desktop MCP server because they require separate GA access grants and do not represent the user's logged-in account.

### Decision: Tokens stored locally and excluded from git

Persist OAuth credentials in a local token file under a development-friendly app/cache directory, with a configurable override if needed. The token file path and token contents must not be logged, committed, or surfaced to the model.

Rationale: persisted refresh tokens are required so MCP clients can call tools after the first browser login. Local-only storage is sufficient for this project, provided `.gitignore` excludes the location and logs redact token details.

Alternative considered: OS keychain. It is more secure, but adds platform-specific dependencies and setup complexity that are not necessary for the first local implementation.

### Decision: Configured default property ID drives report tools

`GA4_PROPERTY_ID` is required for the MCP server's report tools. If `run_ga4_report` or `run_realtime_report` is called without `property_id`, the server uses this configured property. If a caller supplies `property_id`, the server validates it before calling Google APIs.

Rationale: the user wants the property chosen in MCP config so the agent does not guess. The MCP server is the right enforcement point because it receives tool calls from any client, not only this LangGraph app.

Alternative considered: put the default property only in the LangGraph system prompt. That helps the model but does not enforce the rule for Claude Desktop, Cursor, MCP Inspector, or malformed calls.

### Decision: Use fixed, typed tool schemas

Each MCP tool receives typed parameters and validates property IDs, dates, dimensions, metrics, and optional filters before building Google client requests. Filters should start with a small structured subset rather than arbitrary raw API payloads.

Rationale: validation prevents accidental broad API access, keeps tool behavior predictable, and makes errors understandable.

Alternative considered: accept raw GA4 API request JSON for flexibility. This would be faster to build but violates the "do not allow arbitrary API calls" requirement.

### Decision: Safe error normalization

Google exceptions should be mapped into concise user-facing errors for expired/revoked OAuth, missing permissions, invalid property IDs, API-disabled cases, and quota/rate-limit failures. Error logs should include categories and request context but never tokens.

Rationale: MCP clients need actionable errors, and the project goal values observable control.

## Risks / Trade-offs

- Expired or revoked refresh token -> Tell the user how to re-authenticate by deleting the local token file or running an auth reset command.
- Google OAuth app not configured correctly -> README must call out Desktop OAuth client type, consent screen setup, enabled Admin/Data APIs, and readonly scope.
- MCP stdio server launches in a non-interactive context -> First-run OAuth may fail if no browser is available; document running the server manually once to complete login.
- GA4 metric/dimension compatibility errors -> Surface Google's validation message safely and suggest using simpler known-good dimensions/metrics first.
- Filter support can become complex -> Start with a constrained filter format and expand only after the core report flow works.
- Local token file is sensitive -> Gitignore token/cache paths and never print credential JSON or refresh tokens.

## Migration Plan

1. Add the local GA4 MCP server module and dependencies.
2. Add `.env.example` entries and `.gitignore` exclusions for OAuth token/cache files.
3. Update the existing MCP client configuration docs to point `GA_MCP_TRANSPORT=stdio` at the local server.
4. Update the LangGraph system prompt/config summary so report tools rely on the configured MCP property by default.
5. Verify with MCP Inspector or an MCP client, then verify the LangGraph app can load the local GA4 MCP tools.

Rollback is simple because this is additive: remove the local MCP server config and return to SQLite-only or any other external GA MCP server configuration.

## Open Questions

- Should the local token file default to a repo-local ignored directory such as `.ga4-mcp/token.json`, or an OS user cache directory such as `%APPDATA%/ga4-mcp/token.json`?
- How much structured filter support is needed in the first implementation: exact string filters only, or also numeric/date comparisons?
