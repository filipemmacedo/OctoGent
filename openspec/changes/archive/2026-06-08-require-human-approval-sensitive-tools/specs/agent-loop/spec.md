## MODIFIED Requirements

### Requirement: ReAct graph loop executes tool calls until answer is ready or governance halts execution

The system SHALL implement a LangGraph `StateGraph` with nodes `call_model`,
`budget_check`, a human approval gate, and `tools`, connected by conditional
routing. The loop SHALL continue invoking the model and executing approved tool
calls until either the model produces a response with no tool calls or a
governance control halts or interrupts execution. Sensitive tool calls SHALL
route through the approval gate before `ToolNode` execution.

#### Scenario: Agent answers a single-tool safe question

- **WHEN** the user asks a question answerable with one safe tool call and no
  circuit breaker trips
- **THEN** the graph executes
  `call_model -> budget_check -> approval_gate -> tools -> call_model -> END`
  and returns the final AI message without human approval

#### Scenario: Agent pauses before sensitive tool execution

- **WHEN** the user asks a question requiring a sensitive tool call and no
  circuit breaker trips
- **THEN** the graph executes `call_model -> budget_check -> approval_gate` and
  interrupts before the sensitive tool executes

#### Scenario: Agent resumes after sensitive tool approval

- **WHEN** the human approves a pending sensitive tool call
- **THEN** the graph resumes through `tools -> call_model -> END` and returns
  the final AI message

#### Scenario: Agent answers a multi-tool question

- **WHEN** the user asks a question requiring multiple approved or safe tool
  calls and no circuit breaker trips
- **THEN** the graph loops through approval and tool execution as many times as
  needed before routing to `END`

#### Scenario: Agent answers without any tools

- **WHEN** the user asks a general question requiring no data lookup
- **THEN** the graph executes `call_model -> budget_check -> END` directly
  without invoking approval or tools

#### Scenario: Circuit breaker halts the loop

- **WHEN** a governance circuit breaker trips after `call_model`
- **THEN** the graph routes to `END` without requesting human approval or
  executing additional tools or model calls
