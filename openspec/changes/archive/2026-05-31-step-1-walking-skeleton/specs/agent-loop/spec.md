## ADDED Requirements

### Requirement: ReAct graph loop executes tool calls until answer is ready
The system SHALL implement a LangGraph `StateGraph` with nodes `call_model` and `tools`, connected by `tools_condition`. The loop SHALL continue invoking the model and executing tool calls until the model produces a response with no tool calls, at which point the graph SHALL route to `END`.

#### Scenario: Agent answers a single-tool question
- **WHEN** the user asks a question answerable with one tool call
- **THEN** the graph executes `call_model → tools → call_model → END` and returns the final AI message

#### Scenario: Agent answers a multi-tool question
- **WHEN** the user asks a question requiring multiple tool calls (e.g., list tables, then describe, then query)
- **THEN** the graph loops through `call_model → tools` as many times as needed before routing to `END`

#### Scenario: Agent answers without any tools
- **WHEN** the user asks a general question requiring no data lookup
- **THEN** the graph executes `call_model → END` directly without invoking `tools`

---

### Requirement: Graph uses SqliteSaver checkpointer for session persistence
The system SHALL configure the compiled graph with an `AsyncSqliteSaver` checkpointer stored at `.checkpoints/chat_history.db`. Every invocation SHALL pass a `thread_id` in the config so state is persisted and resumable across process restarts.

#### Scenario: Session survives app restart
- **WHEN** the app is restarted and the user selects a previous session
- **THEN** the full message history from that session is reconstructed from the checkpoint DB

#### Scenario: Multiple concurrent sessions are isolated
- **WHEN** two different `thread_id` values are used
- **THEN** their message histories do not mix

---

### Requirement: Graph is built once and reused across requests
The system SHALL build and compile the graph (including loading MCP tools) once at application startup. The compiled graph SHALL be cached and reused for all subsequent invocations without being rebuilt per message.

#### Scenario: MCP tools loaded once
- **WHEN** the application starts
- **THEN** `load_ga_tools()` is called exactly once and the resulting tools are bound to the model for the lifetime of the process

---

### Requirement: System prompt enforces discovery-before-query pattern
The system SHALL include a system message instructing the model to always call `list_tables` before querying SQLite, and `describe_table` on any table before writing a query against it.

#### Scenario: Agent discovers schema before querying
- **WHEN** the user asks a data question and the agent has not yet seen the schema
- **THEN** the agent calls `list_tables`, then `describe_table` for relevant tables, then `query_database` — in that order
