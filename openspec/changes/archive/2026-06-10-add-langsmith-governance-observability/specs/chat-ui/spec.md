## ADDED Requirements

### Requirement: Chainlit traces can be correlated with chat sessions
The Chainlit UI SHALL pass trace metadata that allows a LangSmith trace to be correlated with the Chainlit thread that produced it.

#### Scenario: Chainlit thread ID appears in trace metadata
- **WHEN** Chainlit streams a graph run for a user message
- **THEN** the run metadata includes the Chainlit thread ID used as the LangGraph `thread_id`

#### Scenario: Resumed session keeps same trace correlation key
- **WHEN** a user resumes a Chainlit thread and sends another message
- **THEN** the graph run metadata uses the same thread ID as the resumed checkpoint state

---

### Requirement: Chainlit state inspector remains the local governance view
The Chainlit state inspector SHALL continue to display local governance state even when LangSmith observability is enabled.

#### Scenario: Honeypot state remains visible in Chainlit
- **WHEN** a honeypot block is recorded and LangSmith tracing is enabled
- **THEN** the Chainlit state inspector still shows the `honeypot_events` count and recent event summary

#### Scenario: LangSmith disabled does not reduce UI state
- **WHEN** LangSmith tracing is disabled
- **THEN** the Chainlit state inspector still displays token, cost, halt, HITL, and honeypot state
