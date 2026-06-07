## ADDED Requirements

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
