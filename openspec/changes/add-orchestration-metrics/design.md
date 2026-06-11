# Design: Add Orchestration Metrics in LangSmith

## Context

Step 6 (`governance-observability`) gave us event-shaped observability:
`emit_honeypot_blocked`, `emit_hitl_decision`, `emit_budget_halt` in
`src/observability.py`, each a sanitized `@traceable` emission plus
trace-marking via `get_current_run_tree()`. What does not exist yet:

- `call_model` (src/graph.py) computes per-call token deltas and cumulative
  `tokens_in` / `tokens_out` / `cost_eur` in the token ledger, but none of
  those numbers are attached to the LangSmith run — they live only in
  `AgentState` and stdout prints.
- The prompt is trimmed to the current turn before invocation, so context
  pressure is real but invisible: nothing reports how full the model's
  context window is, and nothing checks whether trimming makes the agent
  fabricate facts that were in dropped messages.
- LangGraph already traces every node (`call_model`, `budget_check`,
  `honeypot_guard`, `approval_gate`, `tools`) as child runs with status and
  latency, but nobody has written down how to turn that into
  error-rate-by-node or latency dashboards, so the signal is effectively
  unused.

Constraints carried over from Step 6: observability must stay optional and
non-blocking; payloads must stay sanitized (no message content, no secrets);
`AgentState` remains the source of truth and LangSmith the investigation
surface.

## Goals / Non-Goals

**Goals:**

- Per-step metrics metadata on `call_model` runs: this call's prompt/output
  tokens, cumulative ledger values, model context window size, and computed
  `context_window_pct`.
- Cumulative `cost_eur` visible inside traces alongside LangSmith's own
  USD cost estimate.
- An online LLM-as-judge evaluator on sampled production traces scoring
  `context_groundedness` (did the response use only data available in its
  trimmed context, or fabricate/miss?), with the judge prompt versioned in
  the repo.
- An operator doc (`docs/langsmith-metrics.md`) that tells a reader exactly
  where each metric lives in the LangSmith UI and how to chart it.

**Non-Goals:**

- No offloaded-memory / retrieval hit-rate metric: this project has no
  memory database to offload to; the trimming-groundedness judge is the
  honest analogue.
- No replacement of the EUR ledger or budget enforcement; metrics are
  read-only annotations.
- No offline eval datasets or CI eval runs (could be a later change).
- No Langfuse integration; LangSmith covers everything required here.
- No new graph nodes — metrics must not change the orchestration loop.

## Decisions

### D1: Attach metrics as run metadata via `get_current_run_tree()`, not a new traced run

`call_model` already runs inside a LangSmith-traced node run. A new helper in
`src/observability.py` — `attach_model_step_metrics(metrics: dict)` — gets the
current run tree, calls `add_metadata(...)` + `patch()` on the **current run
only** (not parents), and swallows all failures with a printed warning,
mirroring `_mark_active_trace_incident`.

- *Why not a `@traceable` event like the governance emitters?* Metrics are
  per-step continuous values, not incidents; a separate run per step would
  double run volume and make charting harder. Dashboard charts group by run
  name + metadata key, which works best when the numbers sit on the
  `call_model` run itself.
- *Why not patch parent runs too?* Honeypot marking walks parents because an
  incident must be findable from the root trace. Step metrics on the root
  would be overwritten by each step; per-node metadata is the correct grain.

Metadata keys (flat, snake_case, numeric): `step_input_tokens`,
`step_output_tokens`, `cumulative_tokens_in`, `cumulative_tokens_out`,
`cumulative_cost_eur`, `model_context_window`, `context_window_pct`
(0–100, rounded to 2 decimals). Numeric-only values keep the payload
trivially sanitized — no message content is ever attached.

**Amendment (verified during implementation):** LangSmith dashboards can
filter and group by metadata but cannot chart metadata values on the Y-axis;
only feedback scores and built-in metrics are chartable. The metadata-only
plan made metrics 1–2 inspectable but not chartable. Resolution:
`attach_model_step_metrics` additionally mirrors the chartable subset —
`context_window_pct`, `cumulative_cost_eur`, `step_input_tokens` — as
feedback scores on the same run via a module-level lazy LangSmith `Client`
(`client.create_feedback(run_id=..., trace_id=..., key=..., score=...)`).
Metadata stays the full payload for trace inspection/filtering; feedback is
additive. Each mirrored key is a synchronous POST per model step — an
accepted latency trade-off; failures are swallowed per key with a printed
warning, and a failed client construction is cached so it is not retried
every step. These system-metric feedback keys share the feedback namespace
with the judge's `context_groundedness` score; the docs call this out.

### D2: Context window size from env config with model-appropriate default

New getter in `src/config.py`: `get_model_context_window()` reading
`AGENT_MODEL_CONTEXT_WINDOW` (int, must be > 0), defaulting to `128000`
(gpt-4o-class). Follows the existing `_warn_invalid_env` pattern.
`context_window_pct = step_input_tokens / window * 100` — utilization is a
property of *this call's prompt*, not cumulative ledger tokens, because the
prompt is trimmed each turn.

- *Alternative considered:* querying the provider for the window size —
  rejected; no stable API for it, and `.env`-driven config is the project
  convention.

### D3: Node error rate and latency are documentation, not code

LangGraph node runs already carry name, status (error/success), and latency.
The deliverable is a documented dashboard recipe (monitor charts filtered by
run name within the tracing project), not new emit code.

- *Alternative considered:* emitting explicit `node_error` events — rejected
  as duplication of what the tracer already records; Step 6's lesson was to
  emit explicit events only where automatic traces are *ambiguous* (guard ran
  vs. guard blocked). Errors are not ambiguous.

### D4: Online evaluator configured in LangSmith, judge prompt versioned in repo

The hallucination/missing-context judge runs as a LangSmith **online
evaluator** (Rules on the tracing project): LLM-as-judge over **sampled**
production traces (recommended starting sample rate 10–25%), filtered to
root runs, writing a `context_groundedness` feedback score (0–1) plus
comment. The judge prompt text lives in the repo
(`docs/langsmith-metrics.md` or a sibling prompt file) so it is reviewable
and versioned, then pasted/configured in the LangSmith UI.

- *Why online vs. offline dataset evals?* The user explicitly chose online
  sampled production scoring. Offline eval suites remain a possible future
  change.
- *Why a feedback score, not metadata?* Feedback is LangSmith's native
  primitive for quality scores: filterable, chartable over time, and
  aggregated in monitor views.
- *Trust note:* the judge reads trace inputs/outputs already stored in
  LangSmith; existing sanitization rules (Step 6) still govern what reaches
  LangSmith in the first place, so the judge sees nothing new.

### D5: One operator doc, structured per metric

`docs/langsmith-metrics.md` with one section per metric:
1. context window utilization, 2. cumulative EUR cost, 3. error rate by
node, 4. end-to-end latency & token/cost totals, 5. context groundedness
(judge). Each section states: where the value originates (code/config or
automatic tracing or evaluator), the exact run name / metadata key /
feedback key to look for, how to filter for it in the LangSmith UI, how to
chart it in a dashboard, and how to interpret it (including the
EUR-ledger-vs-LangSmith-USD-cost caveat and the "guard node ran ≠ incident"
style disambiguation). The doc also contains the online-evaluator setup
steps and the judge prompt, since workspace configuration cannot be checked
into code.

### D6 (added during implementation): data_hit feedback as the offload-hit-rate analogue

The original metric list included "offload hit rate," which presupposes an
offloaded context store this project deliberately does not have (proposal
non-goal). Decision, confirmed with the user: reinterpret it as **data
retrieval hit rate** — the `tools` node wraps `ToolNode` and, after
execution, logs feedback `data_hit` (1.0/0.0) per tool result on the `tools`
run via `log_tool_data_hits`. Classification is a documented text heuristic
over known no-data/error output formats (`DATA_MISS_MARKERS`).
`latency_to_retrieve` is covered by the built-in latency on `tools` runs;
the queried tool name goes in the feedback comment. Honeypot-blocked calls
never reach the node, so they are excluded by construction. The docs state
explicitly that this is not a literal offload hit rate and that
trimming-induced context loss is `context_groundedness`'s job; if a real
offload/recall tool is added later, its results flow through the same node
and `data_hit` covers it unchanged.

## Risks / Trade-offs

- [Per-step `patch()` adds a network call per model step] → patching is
  fire-and-forget through the LangSmith client's background queue, wrapped in
  try/except; failure prints a warning and never blocks the loop.
- [Online judge adds LLM spend on the LangSmith side] → sampling rate is the
  control; the doc states the cost lever explicitly and recommends starting
  low. This spend is outside the agent's EUR budget breaker — the doc calls
  that out so nobody assumes the circuit breaker covers it.
- [`AGENT_MODEL_CONTEXT_WINDOW` can drift from the actual model] → default
  matches the project's configured model; doc notes to update the env var
  when changing models. Worst case the percentage is wrong but harmless.
- [Two cost numbers (ledger EUR vs LangSmith USD) may confuse readers] →
  doc explicitly designates the state ledger as authoritative for governance
  and LangSmith's number as a cross-check.
- [Judge scores on trimmed-context traces require the judge to see what the
  model saw] → the `call_model` run's traced input *is* the trimmed prompt,
  so the judge evaluates against exactly the right context; the doc's judge
  prompt instructs scoring against the run's own inputs only.

## Open Questions

- Exact sample rate for the online evaluator (start 10%? 25%?) — operator
  choice at setup time; doc recommends a starting point and the trade-off.
- Whether to also surface `context_window_pct` in the Chainlit state
  inspector — nice-to-have, deferred unless trivial during implementation.
