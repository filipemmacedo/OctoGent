# Add Orchestration Metrics in LangSmith

## Why

Step 6 made governance *events* (honeypot blocks, HITL decisions, budget halts)
observable in LangSmith, but the system still has no continuous *metrics* view
of orchestration health: how full the model's context window is, what each
step costs in EUR inside the trace, which graph nodes fail and how often, and
whether the trimmed 3-message prompt causes the agent to fabricate or miss
context it no longer has. For a reference implementation whose product is
auditability, these quantitative signals are the missing half of "show I
control": events prove individual incidents were handled; metrics prove the
system stays healthy between incidents.

## What Changes

- Attach per-step orchestration metadata to `call_model` runs in LangSmith:
  cumulative `tokens_in` / `tokens_out`, per-call prompt token count, the
  model's context window size, computed `context_window_pct`, and cumulative
  `cost_eur` — so utilization and EUR cost are chartable per step.
- Rely on automatic LangGraph node tracing for node-level error rate and
  latency (no new emit machinery); document the dashboard/filter recipes that
  surface error-rate-by-node and end-to-end latency/cost from those runs.
- Add an online LLM-as-judge evaluator that runs on **sampled production
  traces** in LangSmith, scoring whether the agent's response used data that
  was actually present in its (trimmed) context or fabricated/missed it.
  Scores land as LangSmith feedback (`context_groundedness`).
- Write a documentation file (`docs/langsmith-metrics.md`) explaining, for
  each metric, exactly where to find and how to read it in the LangSmith UI:
  which project, which run name, which metadata key, which feedback score,
  and which dashboard chart.
- All additions remain optional and non-blocking, consistent with the
  existing observability posture: no LangSmith, no behavior change.

## Capabilities

### New Capabilities
- `orchestration-metrics`: per-step context-window utilization and EUR cost
  metadata on model runs, node error/latency visibility from automatic
  traces, online LLM-as-judge context-groundedness scoring on sampled
  production traces, and operator documentation for reading each metric in
  LangSmith.

### Modified Capabilities

<!-- none: governance-observability requirements are unchanged; this change
     adds a sibling metrics capability and reuses its sanitization rules -->

## Impact

- `src/graph.py`: `call_model` node attaches metrics metadata to the current
  LangSmith run (reusing the existing token ledger values it already
  computes).
- `src/observability.py`: small helper(s) for metrics metadata attachment;
  reuses existing safe-emission and sanitization patterns.
- `src/config.py`: model context-window size config (env-driven, with a sane
  default for the configured model).
- LangSmith workspace (config-as-docs, not code): online evaluator rule with
  sampling rate; dashboard charts for utilization, cost, node error rate,
  latency.
- New `docs/langsmith-metrics.md` operator guide.
- No changes to tools, HITL, honeypot, or budget enforcement paths.
