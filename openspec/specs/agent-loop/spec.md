## Purpose

Define the governed LangGraph orchestration loop, persistence behavior, routing controls, and run-level trace context.

## Requirements

### Requirement: ReAct graph loop executes tool calls until answer is ready or governance halts execution
The system SHALL implement a LangGraph `StateGraph` with nodes `call_model`,
`budget_check`, a honeypot guard, a human approval gate, and `tools`, connected
by conditional routing. The loop SHALL continue invoking the model and executing
approved or safe tool calls until either the model produces a response with no
tool calls or a governance control halts, blocks, or interrupts execution.
Honeypot SQLite tool calls SHALL be blocked before `ToolNode` execution, and
sensitive non-honeypot tool calls SHALL route through the approval gate before
`ToolNode` execution.

#### Scenario: Agent answers a single-tool safe question
- **WHEN** the user asks a question answerable with one safe tool call and no
  circuit breaker trips
- **THEN** the graph executes
  `call_model -> budget_check -> honeypot_guard -> approval_gate -> tools -> call_model -> END`
  and returns the final AI message without human approval

#### Scenario: Agent pauses before sensitive tool execution
- **WHEN** the user asks a question requiring a sensitive tool call and no
  circuit breaker trips
- **THEN** the graph executes `call_model -> budget_check -> honeypot_guard -> approval_gate` and
  interrupts before the sensitive tool executes

#### Scenario: Agent blocks honeypot tool execution
- **WHEN** the user asks a question that causes the model to request SQLite access to a honeypot object
- **THEN** the graph executes `call_model -> budget_check -> honeypot_guard`, appends a governance rejection tool result, and routes back to `call_model` without executing the blocked tool

#### Scenario: Agent resumes after sensitive tool approval
- **WHEN** the human approves a pending sensitive tool call
- **THEN** the graph resumes through `tools -> call_model -> END` and returns
  the final AI message

#### Scenario: Agent answers a multi-tool question
- **WHEN** the user asks a question requiring multiple approved or safe tool
  calls and no circuit breaker trips
- **THEN** the graph loops through honeypot inspection, approval, and tool execution as many times as
  needed before routing to `END`

#### Scenario: Agent answers without any tools
- **WHEN** the user asks a general question requiring no data lookup
- **THEN** the graph executes `call_model -> budget_check -> END` directly
  without invoking honeypot inspection, approval, or tools

#### Scenario: Circuit breaker halts the loop
- **WHEN** a governance circuit breaker trips after `call_model`
- **THEN** the graph routes to `END` without requesting human approval, inspecting honeypot calls, or
  executing additional tools or model calls

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
- **THEN** the agent calls `list_tables`, then `describe_table` for relevant tables, then `query_database` - in that order

---

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
