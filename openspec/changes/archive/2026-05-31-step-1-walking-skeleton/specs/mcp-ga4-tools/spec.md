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
