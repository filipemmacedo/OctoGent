## ADDED Requirements

### Requirement: Governance events are emitted as searchable LangSmith traces
The system SHALL emit structured LangSmith-observable records for actual governance events. Event records SHALL include a stable event type, action, classification, source, timestamp, and safe identifying fields needed for investigation.

#### Scenario: Honeypot block emits observable event
- **WHEN** the graph blocks a SQLite tool call because it references `api_keys_backup`
- **THEN** the system emits an observable event with governance event type `honeypot_blocked`, tag `honeypot`, action `blocked`, and matched object `api_keys_backup`

#### Scenario: Guard execution without block does not emit honeypot event
- **WHEN** the `honeypot_guard` node runs and finds no honeypot reference
- **THEN** the system does not emit a `honeypot_blocked` event

#### Scenario: HITL decision emits observable event
- **WHEN** a human approves, edits, or rejects a sensitive tool call
- **THEN** the system emits an observable event with governance event type `hitl_decision` and the final decision value

#### Scenario: Budget halt emits observable event
- **WHEN** the graph halts because cumulative `cost_eur` reaches the configured budget
- **THEN** the system emits an observable event with governance event type `budget_halt` and the halt reason

---

### Requirement: Governance observability is optional and non-blocking
The system SHALL preserve all governance behavior when LangSmith tracing is disabled, missing, or unavailable. Observability emission failures SHALL NOT permit blocked tools, skip HITL, bypass budget halts, or fail a user request.

#### Scenario: LangSmith environment missing
- **WHEN** LangSmith environment variables are not configured
- **THEN** the agent still blocks honeypot calls, records `honeypot_events`, interrupts for sensitive tools, and halts on budget normally

#### Scenario: Observability emission fails
- **WHEN** a governance observability helper raises or cannot emit a trace
- **THEN** the graph continues using the original governance decision and records the event in `AgentState`

---

### Requirement: Governance trace payloads are sanitized
The system SHALL avoid sending secrets, OAuth tokens, credential values, canary row data, or raw sensitive payloads to LangSmith. Trace payloads SHALL include safe summaries such as tool name, classification, source, matched object, action, reason, timestamp, and argument keys or redacted argument summaries.

#### Scenario: Honeypot event payload excludes row data
- **WHEN** a honeypot access attempt is traced
- **THEN** the trace metadata includes `matched_object=api_keys_backup` and does not include fake canary table row values

#### Scenario: Tool args are summarized
- **WHEN** a governance event includes tool arguments
- **THEN** the observable payload contains either redacted arguments or argument key summaries rather than full sensitive values

---

### Requirement: LangSmith configuration is documented
The system SHALL document the environment variables needed for LangSmith tracing and project selection, while keeping tracing optional for local development.

#### Scenario: Developer reviews environment example
- **WHEN** a developer opens `.env.example`
- **THEN** it lists optional LangSmith tracing configuration including `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, and `LANGSMITH_ENDPOINT`

#### Scenario: Tracing disabled by default
- **WHEN** a developer runs the app without LangSmith variables
- **THEN** the app runs without requiring LangSmith credentials
