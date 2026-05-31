## ADDED Requirements

### Requirement: Thread history is persisted to disk
The system SHALL persist each Chainlit thread (conversation) to a local SQLite database so that the sidebar shows all past conversations across browser refreshes and server restarts.

#### Scenario: Thread appears in sidebar after session
- **WHEN** a user completes a conversation in a session
- **THEN** that thread SHALL appear in the Chainlit sidebar in subsequent sessions

#### Scenario: Sidebar survives server restart
- **WHEN** the Chainlit server is restarted
- **THEN** all previously persisted threads SHALL still appear in the sidebar

### Requirement: Thread resume restores full agent state
The system SHALL restore the full LangGraph agent state (message history, token counts, cost ledger) when a thread is resumed from the sidebar.

#### Scenario: Resuming a thread from the sidebar
- **WHEN** a user clicks a thread in the Chainlit sidebar
- **THEN** the system SHALL reconnect to the LangGraph checkpointer using the thread's original `thread_id`
- **AND** subsequent messages SHALL continue the conversation from where it left off

#### Scenario: Token ledger continuity on resume
- **WHEN** a thread is resumed from the sidebar
- **THEN** token counts and EUR cost SHALL reflect the full session history (not reset to zero)

### Requirement: Anonymous single-user authentication
The system SHALL use a fixed anonymous user identity so the sidebar is available without any login screen or credentials.

#### Scenario: App starts without login prompt
- **WHEN** a user opens the Chainlit app
- **THEN** the system SHALL NOT prompt for login
- **AND** the sidebar SHALL display threads belonging to the anonymous user identity

### Requirement: New session starts a fresh thread
The system SHALL create a new `thread_id` for each new conversation so threads are distinct in the sidebar.

#### Scenario: New chat creates a new thread
- **WHEN** a user starts a new chat (via the "New Chat" button)
- **THEN** the system SHALL assign a fresh `thread_id` to the session
- **AND** the new thread SHALL appear in the sidebar separately from previous threads
