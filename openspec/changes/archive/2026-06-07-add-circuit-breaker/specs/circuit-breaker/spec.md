## ADDED Requirements

### Requirement: Per-session EUR budget is configurable

The system SHALL read a per-session maximum EUR budget from environment
configuration and use that value to decide whether a graph run may continue.
If no explicit value is configured, the system SHALL use a documented default
budget suitable for local development.

#### Scenario: Budget configured in environment
- **WHEN** `AGENT_MAX_COST_EUR` is set to `0.05`
- **THEN** the graph uses `0.05` as the maximum cumulative session cost in EUR

#### Scenario: Budget missing from environment
- **WHEN** `AGENT_MAX_COST_EUR` is not set
- **THEN** the graph uses the documented default maximum session cost

---

### Requirement: Budget halt is recorded in AgentState

The system SHALL record budget halt status in `AgentState` when cumulative
`cost_eur` is greater than or equal to the configured maximum budget. The state
SHALL include whether execution halted, whether the budget was exceeded, and a
human-readable halt reason.

#### Scenario: Cost remains under budget
- **WHEN** `cost_eur` is lower than the configured maximum budget
- **THEN** the graph continues without setting budget halt state

#### Scenario: Cost reaches budget
- **WHEN** `cost_eur` is greater than or equal to the configured maximum budget
- **THEN** the graph records that execution halted because the EUR budget was exceeded

---

### Requirement: Budget halt stops additional graph work

The system SHALL stop the graph before executing additional tools or model
calls once the budget halt condition is true.

#### Scenario: Model call crosses budget before tool execution
- **WHEN** `call_model` returns a tool call and the updated cumulative `cost_eur` exceeds the budget
- **THEN** the graph routes to `END` without executing the requested tool call

#### Scenario: Model call remains under budget before tool execution
- **WHEN** `call_model` returns a tool call and the updated cumulative `cost_eur` remains under budget
- **THEN** the graph continues to the tools node

---

### Requirement: Recursion limit is configured for graph invocations

The system SHALL pass a configured `recursion_limit` in the LangGraph run config
for both Chainlit and CLI invocations.

#### Scenario: Chainlit invocation has recursion limit
- **WHEN** Chainlit streams graph events for a user message
- **THEN** the graph config includes the configured `recursion_limit`

#### Scenario: CLI invocation has recursion limit
- **WHEN** `python -m src.main` invokes the graph
- **THEN** the graph config includes the configured `recursion_limit`

---

### Requirement: Circuit breaker decisions are observable

The system SHALL print circuit-breaker halt decisions to stdout and surface the
halt reason in user-visible output.

#### Scenario: Budget halt is logged
- **WHEN** the graph halts because the EUR budget is exceeded
- **THEN** stdout includes a log line with the current cost, configured budget, and halt reason

#### Scenario: Budget halt is shown in Chainlit
- **WHEN** a Chainlit run halts because the EUR budget is exceeded
- **THEN** the user sees a message explaining that the run stopped because the budget was exceeded

#### Scenario: Recursion limit halt is shown in Chainlit
- **WHEN** a Chainlit run stops because LangGraph's recursion limit is exceeded
- **THEN** the user sees a message explaining that the run stopped because the loop limit was exceeded
