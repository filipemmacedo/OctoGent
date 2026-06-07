## 1. Project Structure and Dependencies

- [x] 1.1 Add the local GA4 MCP server module/package structure with separate files for server entrypoint, OAuth credentials, GA4 API wrappers, validation, and error handling.
- [x] 1.2 Add required Python dependencies for MCP server hosting, Google OAuth, Google Analytics Admin API, and Google Analytics Data API.
- [x] 1.3 Add gitignore coverage for local OAuth token/cache files and generated local credential artifacts.

## 2. OAuth and Configuration

- [x] 2.1 Implement environment-driven configuration for `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_PROJECT_ID`, `GA4_PROPERTY_ID`, and optional token path override.
- [x] 2.2 Implement readonly Google OAuth user login using `https://www.googleapis.com/auth/analytics.readonly`.
- [x] 2.3 Persist and refresh local OAuth credentials without logging access tokens or refresh tokens.
- [x] 2.4 Add clear configuration/authentication errors for missing OAuth config, expired/revoked tokens, and browser-login failures.

## 3. GA4 API Layer

- [x] 3.1 Implement GA4 Admin API account/property listing using authenticated user credentials.
- [x] 3.2 Implement GA4 Data API standard report execution.
- [x] 3.3 Implement GA4 Data API realtime report execution.
- [x] 3.4 Normalize Google API errors for missing permissions, invalid properties, disabled APIs, and quota/rate-limit failures.

## 4. Tool Schemas and Validation

- [x] 4.1 Implement validation for property IDs, account IDs, date ranges, dimensions, metrics, and optional structured filters.
- [x] 4.2 Expose `list_ga4_accounts` and `list_ga4_properties` as MCP tools.
- [x] 4.3 Expose `run_ga4_report` as an MCP tool that defaults to configured `GA4_PROPERTY_ID` when `property_id` is omitted.
- [x] 4.4 Expose `run_realtime_report` as an MCP tool that defaults to configured `GA4_PROPERTY_ID` when `property_id` is omitted.
- [x] 4.5 Ensure the MCP server does not expose arbitrary Google API call tools or write-capable GA operations.

## 5. LangGraph Client Integration

- [x] 5.1 Update MCP config summary and environment pass-through so the local stdio MCP server receives the configured GA4 property ID safely.
- [x] 5.2 Update the LangGraph system prompt guidance so the agent omits `property_id` for report tools when MCP config owns the default, and asks/lists instead of guessing when no property is configured.

## 6. Documentation and Examples

- [x] 6.1 Update `.env.example` with required Google OAuth and GA4 property variables.
- [x] 6.2 Add README setup steps for Google Cloud Console, enabled APIs, OAuth Desktop client creation, consent screen setup, install commands, and first-run OAuth login.
- [x] 6.3 Add example MCP client configuration for Claude Desktop, Cursor, MCP Inspector, and the existing LangGraph app.
- [x] 6.4 Add example test queries for account listing, property listing, standard reports, and realtime reports.
- [x] 6.5 Add notes explaining why user OAuth is preferred over service accounts for this personal project.

## 7. Verification

- [x] 7.1 Verify the MCP server starts locally over stdio.
- [x] 7.2 Verify first-run OAuth opens browser consent and stores local credentials.
- [x] 7.3 Verify `list_ga4_accounts` and `list_ga4_properties` return data for the authenticated user.
- [x] 7.4 Verify `run_ga4_report` and `run_realtime_report` return GA4 data using the configured property ID.
- [x] 7.5 Verify no secrets or refresh tokens are printed, committed, or included in `.env.example`.
