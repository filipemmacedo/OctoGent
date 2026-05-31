## ADDED Requirements

### Requirement: AgentState tracks cumulative token usage and EUR cost
The system SHALL include `tokens_in: int`, `tokens_out: int`, and `cost_eur: float` fields in `AgentState`. After each `call_model` node execution, these fields SHALL be updated by adding the tokens consumed in that node invocation to the running session totals.

#### Scenario: Tokens accumulate across turns
- **WHEN** the agent makes three separate model calls in one session
- **THEN** `tokens_in` equals the sum of input tokens from all three calls

#### Scenario: Fresh session starts at zero
- **WHEN** a new session is started with a new `thread_id`
- **THEN** `tokens_in`, `tokens_out`, and `cost_eur` all start at `0`

---

### Requirement: Token usage captured via LangChain callback
The system SHALL use `get_usage_metadata_callback()` from `langchain_core.callbacks` to capture token usage per `call_model` node invocation. The callback result SHALL be used to update the ledger fields in the returned state.

#### Scenario: Usage metadata captured per node call
- **WHEN** `call_model` completes
- **THEN** the callback provides non-zero `input_tokens` and `output_tokens` values that are added to state

---

### Requirement: EUR cost calculated using gpt-4o-mini pricing
The system SHALL calculate EUR cost as:
- Input: `tokens_in × (0.15 / 1_000_000) × 0.92`  (USD price × EUR/USD rate)
- Output: `tokens_out × (0.60 / 1_000_000) × 0.92`

The EUR/USD rate (0.92) and per-token prices SHALL be defined as module-level constants, not hardcoded inline.

#### Scenario: Cost calculated correctly for 1000 input tokens
- **WHEN** a call consumes 1000 input tokens and 0 output tokens
- **THEN** `cost_eur` increases by approximately €0.000138

#### Scenario: Cost accumulates across turns
- **WHEN** two model calls are made in the same session
- **THEN** `cost_eur` equals the sum of costs from both calls

---

### Requirement: Token ledger is observable in logs
The system SHALL print a log line after each `call_model` node execution showing the tokens used in that call and the running session total cost in EUR. Format: `[tokens] +{in}in/{out}out | session total: €{cost_eur:.6f}`.

#### Scenario: Log printed after every model call
- **WHEN** `call_model` completes
- **THEN** a line matching the format above is printed to stdout
