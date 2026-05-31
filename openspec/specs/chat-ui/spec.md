## ADDED Requirements

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
- **THEN** a cost indicator (e.g., "💰 €0.0012 this session") is visible near the response

#### Scenario: Cost starts at zero for new sessions
- **WHEN** a new session is started
- **THEN** the cost display shows €0.000000

---

### Requirement: App runs with `chainlit run app.py`
The system SHALL be launchable with the standard Chainlit command from the project root. All graph initialisation (MCP tool loading, checkpointer setup) SHALL complete during the `@cl.on_chat_start` lifecycle hook before the first user message is accepted.

#### Scenario: App starts without error when all env vars set
- **WHEN** `.env` contains valid `OPENAI_API_KEY`, `OPENAI_MODEL`, and optionally `GA_MCP_URL`
- **THEN** `chainlit run app.py` starts without exceptions and the UI is accessible

#### Scenario: App starts in SQLite-only mode when GA_MCP_URL absent
- **WHEN** `GA_MCP_URL` is not set in `.env`
- **THEN** the app starts successfully and a warning is logged; SQLite tools are available
