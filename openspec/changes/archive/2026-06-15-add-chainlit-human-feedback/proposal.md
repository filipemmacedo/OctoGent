# Add Chainlit Human Feedback

## Why

The observability layer measures cost, context, governance events, and tool
data hits, but has **no signal for answer quality**: nothing records whether a
user found an agent response good or bad. Human 👍/👎 feedback is the cheapest,
highest-signal quality metric available, and it is the calibration baseline for
any future LLM-as-judge evaluators. Chainlit already ships a feedback UI that
activates with the existing data layer, so the missing piece is wiring those
ratings to the LangSmith trace that produced the answer.

## What Changes

- Enable Chainlit's built-in 👍/👎 (+ optional comment) controls on agent
  answer messages, persisted through the existing SQLAlchemy data layer.
- Associate each agent answer message with the LangSmith root run (trace) of
  the graph invocation that produced it, so a rating can be attributed to the
  exact trace.
- Forward each feedback action to LangSmith as a `user_score` feedback score
  (1.0 = thumbs up, 0.0 = thumbs down, comment attached), idempotently — a
  changed rating updates the score rather than duplicating it.
- Keep the forwarding optional and non-blocking, matching the existing
  observability conventions: with LangSmith unconfigured, local feedback
  persistence still works and nothing raises.
- CLI (`python -m src.main`) is out of scope; feedback is a Chainlit-surface
  feature.

## Capabilities

### New Capabilities

- `human-feedback`: capture per-answer human quality ratings in the Chainlit
  UI, link each rating to the LangSmith trace that produced the answer, and
  record it as a `user_score` feedback score for dashboards and evaluator
  calibration.

### Modified Capabilities

<!-- No existing spec's requirements change. chat-ui rendering, the data layer,
     and governance-observability event semantics stay as specified; this change
     adds a new capability alongside them. -->

## Impact

- `app.py`: pre-generate a per-invocation `run_id` for `graph.astream_events`,
  store the run id on the final answer message (metadata + in-memory map), and
  swap `SQLAlchemyDataLayer` for a thin subclass whose `upsert_feedback` /
  `delete_feedback` also forward to LangSmith.
- `src/observability.py`: new `log_user_feedback(...)` helper following the
  existing never-raise, optional-LangSmith pattern.
- `src/config.py`: `build_graph_config` accepts an optional `run_id`.
- No schema change to `AgentState`; no new dependencies (`langsmith` and the
  Chainlit data layer are already in use).
- Dashboards: `user_score` becomes a chartable feedback key alongside the
  existing `context_window_pct` / `data_hit` scores.
