## ADDED Requirements

### Requirement: Model steps attach orchestration metrics metadata to their LangSmith run
The system SHALL attach numeric orchestration metrics as metadata to the current LangSmith run of each `call_model` step: this call's input and output token counts, cumulative `tokens_in`, `tokens_out`, and `cost_eur` from the token ledger, the configured model context window size, and the computed context window utilization percentage for this call's prompt.

#### Scenario: Metrics metadata attached after a model call
- **WHEN** `call_model` completes a model invocation while LangSmith tracing is active
- **THEN** the current `call_model` run's metadata includes `step_input_tokens`, `step_output_tokens`, `cumulative_tokens_in`, `cumulative_tokens_out`, `cumulative_cost_eur`, `model_context_window`, and `context_window_pct`

#### Scenario: Utilization reflects the trimmed prompt, not the cumulative ledger
- **WHEN** the prompt sent to the model has been trimmed to the current turn
- **THEN** `context_window_pct` is computed from this call's input tokens divided by the configured context window, independent of the cumulative ledger totals

#### Scenario: Metrics payload contains no message content
- **WHEN** metrics metadata is attached to a run
- **THEN** the attached values are numeric only and include no prompt text, message content, tool arguments, or secrets

---

### Requirement: Chartable step metrics are mirrored as feedback scores
The system SHALL mirror the chartable step metrics — `context_window_pct`, `cumulative_cost_eur`, and `step_input_tokens` — as LangSmith feedback scores on the same `call_model` run, because LangSmith dashboards can only chart feedback scores, not metadata values. Feedback mirroring SHALL be additive to metadata attachment and SHALL reuse a single LangSmith client instance.

#### Scenario: Chartable keys logged as feedback
- **WHEN** step metrics are attached to a `call_model` run while LangSmith tracing is active
- **THEN** feedback scores `context_window_pct`, `cumulative_cost_eur`, and `step_input_tokens` are created on that run with the same numeric values as the metadata

#### Scenario: Feedback failure does not affect metadata or the agent
- **WHEN** a feedback creation call fails or the LangSmith client cannot be constructed
- **THEN** the system prints a warning, metadata attachment is unaffected, and the model step completes normally

#### Scenario: No feedback without tracing
- **WHEN** LangSmith is not installed or there is no active run
- **THEN** no feedback creation is attempted

---

### Requirement: Tool data retrieval results are scored as data_hit feedback
The system SHALL score every executed tool result as a hit (1.0, returned usable data) or miss (0.0, empty result, not-found marker, or error) and log it as LangSmith feedback `data_hit` on the `tools` run with the tool name in the comment. This is the documented analogue of an offload hit rate: the agent has no offloaded context store, so the metric measures retrieval quality against the agent's data stores (SQLite, GA4). Scoring SHALL be non-blocking and SHALL NOT alter tool results or routing.

#### Scenario: Hit and miss scored per tool result
- **WHEN** the `tools` node executes tool calls while LangSmith tracing is active
- **THEN** each resulting tool message produces one `data_hit` feedback score of 1.0 for usable data or 0.0 for known no-data or error outputs

#### Scenario: Honeypot-blocked calls are excluded
- **WHEN** a tool call is blocked by the honeypot guard before the `tools` node
- **THEN** no `data_hit` feedback is produced for it

#### Scenario: Scoring failure does not affect tool execution
- **WHEN** feedback logging fails or LangSmith is unavailable
- **THEN** tool results are returned to the graph unchanged and the loop continues normally

---

### Requirement: Model context window size is configurable via environment
The system SHALL read the model context window size from the `AGENT_MODEL_CONTEXT_WINDOW` environment variable, validated as a positive integer, with a default appropriate to the configured model when the variable is unset or invalid. Invalid values SHALL produce a printed warning and fall back to the default.

#### Scenario: Default window when unset
- **WHEN** `AGENT_MODEL_CONTEXT_WINDOW` is not set
- **THEN** the system uses the documented default context window size

#### Scenario: Invalid value falls back with warning
- **WHEN** `AGENT_MODEL_CONTEXT_WINDOW` is set to a non-integer or non-positive value
- **THEN** the system prints a config warning and uses the default

---

### Requirement: Metrics attachment is optional and non-blocking
The system SHALL preserve all agent and governance behavior when LangSmith is disabled, unavailable, or when metrics attachment fails. A metrics attachment failure SHALL NOT fail the model step, alter the token ledger, or change routing.

#### Scenario: LangSmith not configured
- **WHEN** LangSmith environment variables are not configured
- **THEN** `call_model` completes normally and the token ledger updates as before, with no metrics emission attempted beyond a safe no-op

#### Scenario: Attachment failure is swallowed
- **WHEN** attaching metrics metadata raises an exception
- **THEN** the system prints a warning and the graph continues with the model response and updated ledger

---

### Requirement: Online context-groundedness judging on sampled production traces
The system SHALL provide a versioned LLM-as-judge prompt and documented LangSmith online-evaluator configuration that scores sampled production traces for context groundedness: whether the agent's response used only information available in the trimmed prompt it was actually given, or fabricated/assumed unavailable information. Scores SHALL be recorded as LangSmith feedback under a stable key (`context_groundedness`) with a judge comment.

#### Scenario: Judge prompt is versioned in the repository
- **WHEN** a reviewer inspects the repository
- **THEN** the exact judge prompt used by the online evaluator is present in the documentation and reviewable in version control

#### Scenario: Evaluator scores against the run's own inputs
- **WHEN** the online evaluator scores a sampled trace
- **THEN** the judge evaluates the response against the trimmed prompt recorded as that run's input, producing a `context_groundedness` feedback score between 0 and 1

#### Scenario: Sampling limits judge cost
- **WHEN** the online evaluator is configured per the documentation
- **THEN** it applies a sampling rate to production traces rather than scoring every run, and the documentation states the cost trade-off

---

### Requirement: Operator documentation explains how to read each metric in LangSmith
The system SHALL include a documentation file (`docs/langsmith-metrics.md`) that, for each metric — context window utilization, cumulative EUR cost, error rate by node, end-to-end latency and token/cost totals, and context groundedness — states where the value originates, the exact run name, metadata key, or feedback key to inspect, how to filter and chart it in the LangSmith UI, and how to interpret it.

#### Scenario: Each metric has a reading recipe
- **WHEN** an operator opens `docs/langsmith-metrics.md`
- **THEN** every metric section identifies the LangSmith location (run name, metadata key, or feedback key) and the UI steps to view and chart it

#### Scenario: Node error rate and latency documented from automatic traces
- **WHEN** the operator follows the error-rate-by-node section
- **THEN** the documentation explains how to filter automatic LangGraph node runs (`call_model`, `budget_check`, `honeypot_guard`, `approval_gate`, `tools`) by name and error status in dashboards, without any custom emission code

#### Scenario: Cost authority is disambiguated
- **WHEN** the operator reads the cost section
- **THEN** the documentation states that the `AgentState` EUR ledger is authoritative for governance and budget enforcement, and that LangSmith's built-in USD cost estimate is a cross-check

#### Scenario: Online evaluator setup is reproducible
- **WHEN** an operator follows the documentation's evaluator setup section
- **THEN** they can configure the LangSmith online evaluator (rule, filter, sampling rate, judge prompt, feedback key) without information outside the repository other than workspace credentials
