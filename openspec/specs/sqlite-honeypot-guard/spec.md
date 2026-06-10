## Purpose

Define SQLite honeypot canary registration, detection, blocking, and audit behavior.

## Requirements

### Requirement: SQLite honeypot objects are registered for governance
The system SHALL maintain an explicit list of SQLite honeypot objects. The initial honeypot registry SHALL include the table `api_keys_backup` with a human-readable reason explaining that no legitimate workflow should access it.

#### Scenario: Canary table is registered
- **WHEN** the graph inspects SQLite governance configuration
- **THEN** `api_keys_backup` is present as a honeypot object with classification `honeypot`

---

### Requirement: Pending SQLite tool calls are inspected for honeypot references
The system SHALL inspect pending model-requested SQLite tool calls before `ToolNode` execution. If a `describe_table` or `query_database` call references a registered honeypot object in its arguments, the call SHALL be classified as `honeypot`.

#### Scenario: Query references canary table
- **WHEN** the latest AI message requests `query_database` with SQL containing `api_keys_backup`
- **THEN** the pre-tool governance guard classifies the tool call as `honeypot`

#### Scenario: Describe table references canary table
- **WHEN** the latest AI message requests `describe_table` with `table_name` equal to `api_keys_backup`
- **THEN** the pre-tool governance guard classifies the tool call as `honeypot`

#### Scenario: Quoted canary identifier is detected
- **WHEN** the latest AI message requests `query_database` with SQL containing `"api_keys_backup"`, `[api_keys_backup]`, or `` `api_keys_backup` ``
- **THEN** the pre-tool governance guard classifies the tool call as `honeypot`

---

### Requirement: Honeypot tool calls are blocked before execution
The system SHALL block any pending tool-call batch that includes a honeypot-classified call before `ToolNode` executes. Honeypot blocks SHALL be deny-only and SHALL NOT request human approval.

#### Scenario: Honeypot query does not execute
- **WHEN** the latest AI message requests `query_database` against `api_keys_backup`
- **THEN** the graph blocks the call before SQLite execution

#### Scenario: Honeypot blocks before HITL
- **WHEN** a pending tool-call batch contains a honeypot SQLite call and a sensitive GA4 call
- **THEN** the graph blocks the batch as honeypot misuse and does not show a human approval prompt

---

### Requirement: Honeypot blocks are recorded in AgentState
The system SHALL record each honeypot block in `AgentState`. Each record SHALL include the tool call ID, tool name, source, classification, matched object, original arguments, action, reason, and timestamp.

#### Scenario: Block event is persisted
- **WHEN** the graph blocks a honeypot SQLite call
- **THEN** `AgentState.honeypot_events` includes a record for that blocked call

---

### Requirement: Honeypot blocks are returned to the model as tool results
The system SHALL append rejection `ToolMessage` entries for blocked honeypot tool calls and route back to `call_model` so the model can answer without executing the blocked database access.

#### Scenario: Model receives block result
- **WHEN** a honeypot SQLite call is blocked
- **THEN** the next model invocation receives a tool result explaining that governance blocked the honeypot access
