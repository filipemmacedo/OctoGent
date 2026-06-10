## MODIFIED Requirements

### Requirement: Tools are classified before execution
The system SHALL maintain an explicit governance classification for every tool
available to the graph. The classification SHALL include the tool name, source,
classification, and human-readable reason. SQLite tools SHALL be statically
classified as `safe`, GA4 MCP tools SHALL be classified as `sensitive`, and
SQLite tool calls that reference registered canary objects SHALL be dynamically
classified as `honeypot`.

#### Scenario: SQLite tools are safe
- **WHEN** the graph is built with `list_tables`, `describe_table`, and
  `query_database`
- **THEN** the tool governance registry classifies those tools as `safe`

#### Scenario: GA4 MCP tools are sensitive
- **WHEN** GA4 MCP tools are loaded and passed into the graph
- **THEN** the tool governance registry classifies each GA4 MCP tool as
  `sensitive`

#### Scenario: SQLite canary access is honeypot
- **WHEN** a pending SQLite tool call references `api_keys_backup`
- **THEN** the pre-tool governance decision classifies that specific call as `honeypot`

## ADDED Requirements

### Requirement: Honeypot calls are not human-approvable
The system SHALL treat honeypot-classified tool calls as deny-only. Honeypot calls SHALL be blocked before the human approval interrupt and SHALL NOT present approve, edit, or reject controls.

#### Scenario: Honeypot call skips approval UI
- **WHEN** the latest AI message requests access to `api_keys_backup`
- **THEN** the graph blocks the call without invoking `interrupt()` for human approval
