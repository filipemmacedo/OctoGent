## ADDED Requirements

### Requirement: Tools are classified before execution

The system SHALL maintain an explicit governance classification for every tool
available to the graph. The classification SHALL include the tool name, source,
classification, and human-readable reason. SQLite tools SHALL be classified as
`safe` for this change, and GA4 MCP tools SHALL be classified as `sensitive`.

#### Scenario: SQLite tools are safe

- **WHEN** the graph is built with `list_tables`, `describe_table`, and
  `query_database`
- **THEN** the tool governance registry classifies those tools as `safe`

#### Scenario: GA4 MCP tools are sensitive

- **WHEN** GA4 MCP tools are loaded and passed into the graph
- **THEN** the tool governance registry classifies each GA4 MCP tool as
  `sensitive`

---

### Requirement: Sensitive tool calls interrupt before execution

The system SHALL inspect pending model-requested tool calls before `ToolNode`
executes them. If any pending tool call is classified as `sensitive`, the graph
SHALL interrupt with a structured approval request before executing any
sensitive tool.

#### Scenario: Sensitive GA4 report requires approval

- **WHEN** the latest AI message requests `run_ga4_report`
- **THEN** the graph interrupts before `run_ga4_report` executes and exposes the
  tool name, arguments, classification, and reason in the interrupt payload

#### Scenario: Safe SQLite query executes without approval

- **WHEN** the latest AI message requests only `query_database`
- **THEN** the graph routes directly to `ToolNode` without requesting human
  approval

---

### Requirement: Human approval decision resumes the graph

The system SHALL resume an interrupted graph with a human decision. The decision
SHALL support approve, edit, and reject outcomes.

#### Scenario: Human approves sensitive tool call

- **WHEN** the human approves a pending sensitive tool call
- **THEN** the graph resumes and executes the approved tool call

#### Scenario: Human edits sensitive tool arguments

- **WHEN** the human edits the arguments for a pending sensitive tool call
- **THEN** the graph resumes and executes the tool call with the edited
  arguments

#### Scenario: Human rejects sensitive tool call

- **WHEN** the human rejects a pending sensitive tool call
- **THEN** the graph does not execute the rejected tool call and returns the
  rejection to the model as a tool result

---

### Requirement: Human approval decisions are recorded in AgentState

The system SHALL record human approval decisions in `AgentState` so approval
history is inspectable and persisted with the graph checkpoint.

#### Scenario: Approval decision is persisted

- **WHEN** a human approves, edits, or rejects a sensitive tool call
- **THEN** `AgentState` includes a decision record with the tool call ID, tool
  name, classification, original arguments, final arguments when applicable,
  decision, reason or comment when provided, and timestamp

#### Scenario: State inspector shows HITL decisions

- **WHEN** Chainlit renders the state inspector after a human approval decision
- **THEN** the state inspector includes the recorded HITL decision summary

---

### Requirement: Chainlit provides structured approval controls

The Chainlit UI SHALL display a structured approval prompt for sensitive tool
interrupts. The prompt SHALL allow the human to approve, edit arguments, or
reject the pending sensitive tool call. A regular chat message SHALL NOT be
treated as governance approval.

#### Scenario: Chainlit shows pending sensitive call

- **WHEN** the graph interrupts for a sensitive tool call
- **THEN** Chainlit shows the pending tool name, arguments, classification, and
  reason with approve, edit, and reject controls

#### Scenario: Chat text is not approval

- **WHEN** a sensitive tool call is pending approval
- **THEN** a normal chat message such as `yes` is not treated as approval for
  that tool call

---

### Requirement: CLI provides approval fallback

The CLI SHALL provide a terminal approval fallback for sensitive tool
interrupts so `python -m src.main` can continue to demonstrate HITL behavior
without Chainlit.

#### Scenario: CLI asks for sensitive tool approval

- **WHEN** the graph interrupts for a sensitive tool call during CLI execution
- **THEN** the CLI prompts the user to approve, edit arguments, or reject before
  resuming the graph
