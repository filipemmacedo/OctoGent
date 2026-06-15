# Design: Add Chainlit Human Feedback

## Context

Chainlit renders 👍/👎 controls on assistant messages whenever a data layer is
configured. `app.py` already configures `SQLAlchemyDataLayer` over the local
SQLite Chainlit DB, so the UI side is nearly free: ratings arrive as calls to
`data_layer.upsert_feedback(feedback)` / `delete_feedback(feedback_id)`, where
`feedback.forId` is the id of the rated message (a row in the `steps` table),
`feedback.value` is `1`/`0`, and `feedback.comment` is optional text.

What does not exist is the link from a rated Chainlit message to the LangSmith
trace that produced it. A turn in `_handle_message` runs one or more
`graph.astream_events(...)` invocations (one per HITL resume), each of which is
its own LangSmith root run. LangChain's `RunnableConfig` accepts a caller-chosen
`run_id`, which becomes the root run id — so the app can know the trace id
up-front without any LangSmith API round trip.

Existing conventions that constrain this design (`src/observability.py`):
observability is optional and non-blocking, helpers never raise, and chartable
metrics are recorded as LangSmith feedback scores.

## Goals / Non-Goals

**Goals:**
- A user rating on an agent answer becomes a `user_score` feedback score
  (1.0 / 0.0, with comment) on the LangSmith root run of the invocation that
  produced that answer.
- Re-rating updates the existing score; deleting the rating in Chainlit deletes
  it in LangSmith.
- Ratings work (locally persisted) even when LangSmith is unconfigured.
- Ratings on messages from resumed threads still resolve to the right trace
  after an app restart.

**Non-Goals:**
- No CLI feedback surface.
- No LLM-as-judge evaluators, datasets, or annotation queues (future changes).
- No independent quality feedback on intermediate tool steps or system/halt
  messages. If Chainlit submits feedback for its HITL `**Selected:** ...`
  status message, treat it as feedback on the related final answer rather than
  as a separate artifact.
- No change to `AgentState` or graph topology.

## Decisions

### 1. Use Chainlit's built-in feedback UI via a data-layer subclass

Subclass `SQLAlchemyDataLayer` (e.g. `LangSmithFeedbackDataLayer`) and override
`upsert_feedback` / `delete_feedback` to first call `super()` (local
persistence) and then forward to LangSmith via a never-raise helper.

*Alternative considered:* custom `cl.Action` buttons attached to each answer.
Rejected — duplicates UI Chainlit already provides, needs custom callbacks and
state, and loses the native persistence/edit/delete semantics.

### 2. Pre-generate the root `run_id` per `astream_events` invocation

In `_handle_message`, generate `run_id = uuid4()` for **each** loop iteration
(initial invocation and every HITL resume) and pass it through
`build_graph_config(..., run_id=...)` into the `RunnableConfig`. The last
invocation of the loop is the one that produced the final answer, so its
`run_id` is the trace to attribute feedback to.

*Alternative considered:* one `run_id` reused across resumes. Rejected — each
`astream_events` call creates a distinct root run; reusing the id would
collide in LangSmith.

*Alternative considered:* fish the run id out of `astream_events` events.
Rejected — the v2 event stream's top-level `run_id` is available, but
pre-generating keeps the dependency direction simple (app decides, LangSmith
receives) and works identically when tracing is disabled.

### 3. Persist the message→trace link in Chainlit message metadata

When sending the final answer, attach `{"langsmith_run_id": str(run_id)}` as
the `cl.Message` metadata (stored in the `steps` table by the data layer), and
also cache `{message_id: run_id}` in an in-process dict for the fast path.

On `upsert_feedback`, resolve `feedback.forId` → run id via the in-memory map,
falling back to reading the step's metadata from the Chainlit DB. The fallback
is what keeps ratings on resumed threads working after a restart.

Chainlit also renders feedback controls on HITL action/status messages such as
`**Selected:** Approve` if those rows are persisted as assistant messages. The
approval status rows should be persisted as `system_message` rows so they do
not look like answer-quality targets. As a safety net, if Chainlit still submits
feedback for a status message, resolve it to the next assistant answer in the
same thread that has `langsmith_run_id` metadata, then record the same
`user_score` against that answer's root run. Other messages without a
resolvable run id remain local-only.

*Alternative considered:* in-memory map only. Rejected — breaks the resumed
thread case, which the project explicitly supports (thread persistence +
checkpoint restore).

### 4. Idempotent LangSmith feedback via deterministic feedback id

Derive the LangSmith feedback id as `uuid5(NAMESPACE, chainlit_feedback_key)`
(keyed on the rated message id). `create_feedback(feedback_id=...)` then makes
re-rating an upsert instead of an append, and `delete_feedback` can target the
same id without storing any extra mapping.

*Alternative considered:* create a new feedback row per click. Rejected — a
user toggling 👍→👎 would leave both scores on the trace and corrupt averages.

### 5. Forwarding lives in `src/observability.py`

New helpers `log_user_feedback(run_id, score, comment)` and
`delete_user_feedback(run_id, message_id)` follow the existing pattern: reuse
`_get_feedback_client()`, no-op when `langsmith` is absent or unconfigured,
catch-and-print on failure. Feedback key: `user_score` (LangSmith's
conventional key for end-user ratings), scores `1.0` / `0.0`.

## Risks / Trade-offs

- [Forwarding adds a synchronous HTTP call inside a UI callback] → acceptable:
  it runs on a user click, not in the agent loop; wrap in try/except so UI
  persistence never fails because LangSmith is down. (The known sync-POST
  latency in `_log_step_metric_feedback` is a separate, pre-existing concern —
  out of scope here.)
- [Rating arrives for a message with no resolvable run id (old threads created
  before this change)] → resolve to no-op with a printed notice; local
  persistence still succeeds.
- [HITL turns span multiple root runs, but feedback lands only on the last
  one] → documented behavior: the rated artifact is the final answer, and the
  last run contains it. Cross-run analysis can still join on `thread_id`
  metadata, which every run already carries.
- [LangSmith tracing disabled (`LANGSMITH_TRACING` unset) while API key
  present, or vice versa] → helpers attempt the call and degrade silently,
  same contract as the rest of `src/observability.py`.

## Migration Plan

Additive, no migration: existing threads simply lack the metadata link, and
ratings on them stay local-only. Rollback = revert the data-layer subclass to
`SQLAlchemyDataLayer`; locally persisted feedback rows remain valid.

## Open Questions

- None blocking. If Chainlit's feedback payload shape differs across versions
  (`value` as int vs strategy enum), pin behavior to the version in
  `requirements.txt` during implementation.
