## Purpose

Define the Chainlit chat interface, session visibility, state inspector behavior, and trace correlation requirements.

## Requirements

### Requirement: Chat window displays conversation with tool step visibility
The system SHALL render an async Chainlit chat interface where each user message triggers the agent and the response is streamed back. Tool call steps (tool name, duration) SHALL be visible as collapsible child steps on the assistant message.

#### Scenario: User sends a message and sees the answer
- **WHEN** the user types a question and submits
- **THEN** the assistant response appears in the chat window after the agent completes

#### Scenario: Tool calls are visible as steps
- **WHEN** the agent calls `list_tables` or `query_database`
- **THEN** a collapsible step is shown under the assistant message indicating which tool was called

---

### Requirement: Session sidebar lists all persisted sessions
The system SHALL display a sidebar listing all existing chat sessions by their `thread_id`. The user SHALL be able to select a previous session to resume it, which loads the full message history from the `SqliteSaver` checkpoint DB.

#### Scenario: Previous sessions appear in sidebar on startup
- **WHEN** the app starts and checkpoint DB contains prior sessions
- **THEN** the sidebar lists each session's `thread_id` (or a derived short label)

#### Scenario: Selecting a session restores history
- **WHEN** the user clicks a session in the sidebar
- **THEN** the chat window shows all previous messages from that session

#### Scenario: New session button creates fresh thread
- **WHEN** the user clicks "New Session"
- **THEN** a new UUID `thread_id` is generated and the chat window clears

---

### Requirement: EUR cost displayed per session
The system SHALL display the running session cost in EUR in the chat interface after each assistant response. The display SHALL update after every agent invocation.

#### Scenario: Cost badge shown after response
- **WHEN** the assistant finishes a response
- **THEN** a cost indicator is visible near the response

#### Scenario: Cost starts at zero for new sessions
- **WHEN** a new session is started
- **THEN** the cost display shows EUR 0.000000

---

### Requirement: App runs with `chainlit run app.py`
The system SHALL be launchable with the standard Chainlit command from the project root. All graph initialisation (MCP tool loading, checkpointer setup) SHALL complete during the `@cl.on_chat_start` lifecycle hook before the first user message is accepted.

#### Scenario: App starts without error when all env vars set
- **WHEN** `.env` contains valid `OPENAI_API_KEY`, `OPENAI_MODEL`, and optionally `GA_MCP_URL`
- **THEN** `chainlit run app.py` starts without exceptions and the UI is accessible

#### Scenario: App starts in SQLite-only mode when GA_MCP_URL absent
- **WHEN** `GA_MCP_URL` is not set in `.env`
- **THEN** the app starts successfully and a warning is logged; SQLite tools are available

---

### Requirement: State inspector displays honeypot governance events
The Chainlit state inspector SHALL display whether honeypot events have occurred and SHALL summarize recent honeypot blocks using the tool name, matched object, and action.

#### Scenario: Honeypot count shown after block
- **WHEN** Chainlit renders the state inspector after a honeypot access attempt is blocked
- **THEN** the inspector shows a non-zero honeypot event count

#### Scenario: Recent honeypot event is summarized
- **WHEN** Chainlit renders the state inspector after one or more honeypot access attempts are blocked
- **THEN** the inspector includes the most recent honeypot event summary with the matched object `api_keys_backup`

---

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
