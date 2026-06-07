## ADDED Requirements

### Requirement: GA4 tools loaded from MCP server at startup
The system SHALL provide an async `load_ga_tools()` function that connects to the GA4 MCP server using `MultiServerMCPClient` with configuration read from environment variables (`GA_MCP_URL`, `GA_MCP_AUTH`, `GA_MCP_TRANSPORT`). The function SHALL return a list of LangChain-compatible tools.

#### Scenario: Tools loaded when MCP server is reachable
- **WHEN** `GA_MCP_URL` is set and the MCP server responds
- **THEN** `load_ga_tools()` returns a non-empty list of tools that can be bound to the model

#### Scenario: Empty list returned when URL is not configured
- **WHEN** `GA_MCP_URL` is not set in the environment
- **THEN** `load_ga_tools()` returns an empty list and logs a warning: "GA_MCP_URL not set — running SQLite-only"

---

### Requirement: Application runs in SQLite-only mode when GA4 is unavailable
The system SHALL handle the case where `load_ga_tools()` returns an empty list gracefully. The agent SHALL still answer questions using SQLite tools alone, without errors or crashes.

#### Scenario: Agent answers SQLite question without GA4
- **WHEN** `GA_MCP_URL` is not configured and the user asks an e-commerce question
- **THEN** the agent answers using only SQLite tools and does not attempt any MCP calls

#### Scenario: Agent informs user GA4 is unavailable
- **WHEN** `GA_MCP_URL` is not configured and the user asks a GA4 analytics question
- **THEN** the agent responds that GA4 data is not available in the current configuration

---

### Requirement: MCP transport is configurable via environment
The system SHALL read `GA_MCP_TRANSPORT` from the environment (defaulting to `"streamable_http"`) and pass it to `MultiServerMCPClient`. Authorization SHALL be passed via the `Authorization` header using the value of `GA_MCP_AUTH`.

#### Scenario: Default transport used when not specified
- **WHEN** `GA_MCP_TRANSPORT` is not set
- **THEN** the client connects using `"streamable_http"` transport

#### Scenario: Auth header sent when GA_MCP_AUTH is set
- **WHEN** `GA_MCP_AUTH` is set to a bearer token value
- **THEN** the MCP client includes `"Authorization": "<value>"` in its request headers

#### Scenario: Local stdio server configured from environment
- **WHEN** `GA_MCP_TRANSPORT` is set to `"stdio"` and `GA_MCP_COMMAND` is set
- **THEN** the MCP client config uses the configured command, parsed args from `GA_MCP_ARGS`, and passes through configured Google credential and project environment variables

---

### Requirement: GA4 property selection is configuration-driven
The system SHALL treat GA4 property selection as MCP server/client configuration and SHALL NOT require the LangGraph agent to guess a property ID for report tools.

#### Scenario: Configured property is summarized safely
- **WHEN** GA4 MCP configuration includes `GA4_PROPERTY_ID`
- **THEN** the application prints a log-safe MCP configuration summary showing that a default property ID is configured

#### Scenario: Agent prompt uses configured property guidance
- **WHEN** `GA4_PROPERTY_ID` is configured for the MCP server
- **THEN** the agent system prompt instructs the model to omit `property_id` for GA4 report tools unless the user explicitly names another property

#### Scenario: Agent does not invent property IDs
- **WHEN** `GA4_PROPERTY_ID` is not configured and the user asks for a GA4 report without specifying a property
- **THEN** the agent asks for a property ID or lists available properties instead of inventing a property ID

#### Scenario: MCP server enforces property default
- **WHEN** a local GA4 MCP report tool is called without `property_id`
- **THEN** the MCP server uses its configured `GA4_PROPERTY_ID` or rejects the call if no default is configured
