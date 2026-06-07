## ADDED Requirements

### Requirement: Local GA4 MCP server starts over stdio
The system SHALL provide a local MCP server that can be launched by a Python module command and communicates with MCP clients over stdio.

#### Scenario: Server starts successfully
- **WHEN** the user runs the configured Python module command for the GA4 MCP server
- **THEN** the server starts without requiring the LangGraph application to be running

#### Scenario: MCP client discovers tools
- **WHEN** an MCP client connects to the local GA4 MCP server over stdio
- **THEN** the server exposes exactly the GA4 tools `list_ga4_accounts`, `list_ga4_properties`, `run_ga4_report`, and `run_realtime_report`

### Requirement: Google OAuth uses readonly user credentials
The system SHALL authenticate to Google using OAuth 2.0 user login with only the `https://www.googleapis.com/auth/analytics.readonly` scope.

#### Scenario: First run opens OAuth login
- **WHEN** no local OAuth token exists and a GA4 tool requires Google credentials
- **THEN** the server starts a browser-based OAuth consent flow for the configured Google OAuth client

#### Scenario: Tokens are saved locally
- **WHEN** the OAuth consent flow completes successfully
- **THEN** the server saves credentials locally for future runs without printing access tokens or refresh tokens

#### Scenario: Readonly scope is requested
- **WHEN** the OAuth consent URL is generated
- **THEN** the requested scopes include `https://www.googleapis.com/auth/analytics.readonly` and no Google Analytics write scopes

### Requirement: Configuration is environment-driven
The system SHALL read Google OAuth and GA4 configuration from environment variables and SHALL NOT hardcode secrets, project IDs, or property IDs.

#### Scenario: Required OAuth config is missing
- **WHEN** `GOOGLE_CLIENT_ID` or `GOOGLE_CLIENT_SECRET` is missing
- **THEN** the server returns a clear configuration error before attempting OAuth

#### Scenario: Default property config is missing
- **WHEN** `GA4_PROPERTY_ID` is missing and a report tool is called without an explicit `property_id`
- **THEN** the server rejects the call with a clear configuration error

#### Scenario: Environment example documents config
- **WHEN** `.env.example` is inspected
- **THEN** it includes `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_PROJECT_ID`, and `GA4_PROPERTY_ID` with empty or placeholder values

### Requirement: GA4 account listing is read-only
The system SHALL provide `list_ga4_accounts` to return Google Analytics accounts available to the authenticated user.

#### Scenario: Accounts are returned
- **WHEN** the authenticated user has access to one or more GA accounts
- **THEN** `list_ga4_accounts` returns account resource names and display names without exposing OAuth tokens

#### Scenario: User has no account access
- **WHEN** the authenticated user has no accessible GA accounts
- **THEN** `list_ga4_accounts` returns an empty list with a clear message

### Requirement: GA4 property listing is read-only
The system SHALL provide `list_ga4_properties` to return GA4 properties available to the authenticated user.

#### Scenario: Properties are returned
- **WHEN** the authenticated user has access to GA4 properties
- **THEN** `list_ga4_properties` returns property IDs, resource names, display names, property types, and parent account references

#### Scenario: Properties can be filtered by account
- **WHEN** `list_ga4_properties` is called with an account identifier
- **THEN** the server returns only properties belonging to that account after validating the account identifier

### Requirement: GA4 standard reports are constrained and validated
The system SHALL provide `run_ga4_report` for Google Analytics Data API reports with validated `property_id`, `start_date`, `end_date`, `dimensions`, `metrics`, and optional filters.

#### Scenario: Report uses configured property by default
- **WHEN** `run_ga4_report` is called without `property_id` and `GA4_PROPERTY_ID` is configured
- **THEN** the server queries the configured property ID

#### Scenario: Explicit property is validated
- **WHEN** `run_ga4_report` is called with `property_id`
- **THEN** the server validates the property identifier before calling the Google Analytics Data API

#### Scenario: Invalid report input is rejected
- **WHEN** `run_ga4_report` receives malformed dates, empty dimensions, empty metrics, invalid property IDs, or unsupported filters
- **THEN** the server rejects the request before calling Google APIs

#### Scenario: Report returns GA4 data
- **WHEN** `run_ga4_report` receives valid report input for an accessible property
- **THEN** the server returns dimension headers, metric headers, rows, row count, and quota metadata when available

### Requirement: GA4 realtime reports are constrained and validated
The system SHALL provide `run_realtime_report` for Google Analytics Data API realtime reports with validated `property_id`, `dimensions`, and `metrics`.

#### Scenario: Realtime report uses configured property by default
- **WHEN** `run_realtime_report` is called without `property_id` and `GA4_PROPERTY_ID` is configured
- **THEN** the server queries the configured property ID

#### Scenario: Invalid realtime input is rejected
- **WHEN** `run_realtime_report` receives empty dimensions, empty metrics, or an invalid property ID
- **THEN** the server rejects the request before calling Google APIs

#### Scenario: Realtime report returns GA4 data
- **WHEN** `run_realtime_report` receives valid input for an accessible property
- **THEN** the server returns dimension headers, metric headers, rows, and row count

### Requirement: Google API errors are normalized safely
The system SHALL map Google OAuth and Google Analytics API failures to clear MCP tool errors without exposing secrets or refresh tokens.

#### Scenario: OAuth token is expired or revoked
- **WHEN** Google rejects the saved OAuth credentials because they are expired, revoked, or cannot be refreshed
- **THEN** the server returns an authentication error that explains how to re-run the OAuth flow

#### Scenario: Missing permissions are reported
- **WHEN** the authenticated user does not have permission to access the requested GA account or property
- **THEN** the server returns a missing-permission error without retrying arbitrary alternative properties

#### Scenario: Quota errors are reported
- **WHEN** Google Analytics returns a quota or rate-limit error
- **THEN** the server returns a quota error that includes the safe Google error category and omits credential values

### Requirement: Setup documentation is complete
The system SHALL include README documentation for installing, configuring, authenticating, and testing the local GA4 MCP server.

#### Scenario: README includes Google Cloud setup
- **WHEN** the README is inspected
- **THEN** it explains enabling the Google Analytics Data API and Admin API, creating an OAuth Desktop client, configuring the OAuth consent screen, and setting the readonly scope

#### Scenario: README includes MCP client examples
- **WHEN** the README is inspected
- **THEN** it includes example MCP client configuration for local stdio use and example prompts for Claude Desktop, Cursor, or MCP Inspector
