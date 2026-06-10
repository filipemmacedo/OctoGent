## ADDED Requirements

### Requirement: Graph invocations carry governance trace context
The system SHALL include stable tags and metadata in graph invocation config so LangSmith traces can be correlated with governance runs. Metadata SHALL identify the app, interface, thread ID, and governance observability version without changing graph routing behavior.

#### Scenario: CLI invocation includes trace context
- **WHEN** `python -m src.main` invokes the graph
- **THEN** the graph config includes tags or metadata identifying the interface as `cli` and the active thread ID

#### Scenario: Chainlit invocation includes trace context
- **WHEN** Chainlit invokes or streams the graph for a user message
- **THEN** the graph config includes tags or metadata identifying the interface as `chainlit` and the active thread ID

#### Scenario: Trace context does not change routing
- **WHEN** graph invocation metadata is present
- **THEN** existing budget, honeypot, HITL, tool execution, and model routing behavior remains unchanged

---

### Requirement: Governance event emission follows state decisions
The system SHALL emit governance observability records only after the corresponding governance decision has been made in graph state or node logic.

#### Scenario: Honeypot trace follows block event
- **WHEN** `honeypot_guard` creates a `honeypot_events` record
- **THEN** the observable honeypot trace uses that event record as its source

#### Scenario: Budget trace follows halt decision
- **WHEN** `budget_check` sets `halted=True` and `budget_exceeded=True`
- **THEN** the observable budget halt trace uses the halt reason from state output
