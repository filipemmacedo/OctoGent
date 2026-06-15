# Tasks: Add Orchestration Metrics in LangSmith

## 1. Config

- [x] 1.1 Add `get_model_context_window()` to `src/config.py` reading `AGENT_MODEL_CONTEXT_WINDOW` (positive int, default 128000), reusing the `_warn_invalid_env` fallback pattern
- [x] 1.2 Document `AGENT_MODEL_CONTEXT_WINDOW` in `.env.example` with a comment noting it must match the configured model

## 2. Metrics attachment in observability layer

- [x] 2.1 Add `attach_model_step_metrics(metrics: dict)` to `src/observability.py`: numeric-only metadata via `get_current_run_tree()` `add_metadata` + `patch()` on the current run only, no-op when LangSmith is absent, try/except with printed warning on failure
- [x] 2.2 Add a small pure helper that builds the metrics dict (`step_input_tokens`, `step_output_tokens`, `cumulative_tokens_in`, `cumulative_tokens_out`, `cumulative_cost_eur`, `model_context_window`, `context_window_pct` rounded to 2 decimals) so it is unit-testable without LangSmith

## 3. Wire into call_model

- [x] 3.1 In `src/graph.py` `call_model`, after the usage callback, build the metrics dict from `new_in`/`new_out`, the updated ledger values, and `get_model_context_window()`, and call `attach_model_step_metrics(...)`
- [x] 3.2 Extend the existing `[tokens]` print line to include `ctx {context_window_pct}%` so utilization is visible in CLI/Chainlit logs too

## 4. Online context-groundedness evaluator (LangSmith workspace)

- [x] 4.1 Write the LLM-as-judge prompt for `context_groundedness` (score 0–1 + comment; judge evaluates the response strictly against the run's recorded trimmed input) and version it in the docs file
- [x] 4.2 Configure the online evaluator in the LangSmith project: rule on root runs / `call_model` runs, sampling rate (start ~10%), feedback key `context_groundedness`; record every configuration value in the docs so setup is reproducible

## 5. Operator documentation

- [x] 5.1 Write `docs/langsmith-metrics.md` with one section per metric — context window utilization, cumulative EUR cost, error rate by node, end-to-end latency & token/cost totals, context groundedness — each stating: where the value originates, exact run name / metadata key / feedback key, LangSmith UI filter steps, and dashboard chart recipe
- [x] 5.2 Include the disambiguation notes: AgentState EUR ledger is authoritative vs LangSmith USD estimate; node-run errors vs governance events; judge LLM spend is outside the agent budget breaker and controlled by sampling rate
- [x] 5.3 Include the online evaluator setup walkthrough (rule, filter, sample rate, judge prompt, feedback key) and the judge prompt text from 4.1

## 6. Data retrieval hit rate (added during implementation, see design D6)

- [x] 6.1 Add `classify_tool_result_hit` + `log_tool_data_hits` to `src/observability.py`: per-tool-result `data_hit` feedback (1.0/0.0) on the `tools` run, tool name in comment, never raises
- [x] 6.2 Wrap `ToolNode` in `src/graph.py` with `tools_with_metrics` (same retry policy, no routing change) calling `log_tool_data_hits` after execution
- [x] 6.3 Document metric 6 in `docs/langsmith-metrics.md`: chart recipe, heuristic limits, and why this is the analogue of an offload hit rate (no offloaded context store exists)
- [x] 6.4 Unit tests: hit/miss classification for all known output formats, per-message feedback logging, no-op and failure-swallowing paths

## 7. Tests & verification

- [x] 7.1 Unit tests: context window config getter (default, invalid, valid) and the metrics-dict helper (values, rounding, trimmed-prompt semantics)
- [x] 7.2 Unit test: `attach_model_step_metrics` is a safe no-op without LangSmith and swallows attachment exceptions without affecting the returned state
- [x] 7.3 Manual verification: run a session with LangSmith enabled, confirm `call_model` runs show the metrics metadata, dashboards chart `context_window_pct` and `cumulative_cost_eur`, and a sampled run receives `context_groundedness` feedback; capture findings in the docs if UI steps differ
