## MODIFIED Requirements

### Requirement: ReAct graph loop executes tool calls until answer is ready or governance halts execution

The system SHALL implement a LangGraph `StateGraph` with nodes `call_model` and
`tools`, connected by `tools_condition` and circuit-breaker routing. The loop
SHALL continue invoking the model and executing tool calls until either the
model produces a response with no tool calls or a governance circuit breaker
halts execution, at which point the graph SHALL route to `END`.

#### Scenario: Agent answers a single-tool question
- **WHEN** the user asks a question answerable with one tool call and no circuit breaker trips
- **THEN** the graph executes `call_model -> tools -> call_model -> END` and returns the final AI message

#### Scenario: Agent answers a multi-tool question
- **WHEN** the user asks a question requiring multiple tool calls and no circuit breaker trips
- **THEN** the graph loops through `call_model -> tools` as many times as needed before routing to `END`

#### Scenario: Agent answers without any tools
- **WHEN** the user asks a general question requiring no data lookup
- **THEN** the graph executes `call_model -> END` directly without invoking `tools`

#### Scenario: Circuit breaker halts the loop
- **WHEN** a governance circuit breaker trips after `call_model`
- **THEN** the graph routes to `END` without executing additional tools or model calls
