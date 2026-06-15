## 1. Observability helpers

- [x] 1.1 Add `log_user_feedback(run_id, score, comment, message_id)` to
      `src/observability.py`: deterministic feedback id via
      `uuid5(NAMESPACE, message_id)`, key `user_score`, reuse
      `_get_feedback_client()`, never raise, print on failure
- [x] 1.2 Add `delete_user_feedback(message_id)` deriving the same
      deterministic feedback id; never raise
- [x] 1.3 Unit tests: helpers no-op cleanly when `langsmith` is absent or the
      client fails, and the feedback id derivation is stable

## 2. Run id plumbing

- [x] 2.1 Extend `build_graph_config(...)` in `src/config.py` with an optional
      `run_id` parameter that sets `run_id` in the returned config
- [x] 2.2 In `app.py::_handle_message`, generate a fresh `uuid4()` per
      `astream_events` invocation (initial call and each HITL resume), pass it
      through `build_graph_config`, and keep the last invocation's run id
- [x] 2.3 Attach `{"langsmith_run_id": <last run id>}` as metadata on the final
      answer `cl.Message` and cache `{message_id: run_id}` in an in-process map
- [x] 2.4 Unit tests: config carries `run_id`; multi-invocation turns produce
      distinct run ids with the last one attributed to the answer

## 3. Feedback data layer

- [x] 3.1 Create `LangSmithFeedbackDataLayer(SQLAlchemyDataLayer)` in `app.py`
      (or a small module) overriding `upsert_feedback`: call `super()` first,
      resolve `feedback.forId` → run id (in-memory map, then steps-table
      metadata fallback), then `log_user_feedback`; print a notice and skip
      forwarding when unresolvable
- [x] 3.2 Override `delete_feedback`: call `super()` first, then
      `delete_user_feedback`; failures never block local deletion
- [x] 3.3 Register the subclass in the `@cl.data_layer` factory
- [x] 3.4 Unit tests: value→score mapping (1→1.0, 0→0.0), comment passthrough,
      metadata fallback resolution, unresolvable-message no-op
- [x] 3.5 Resolve feedback on Chainlit HITL `**Selected:** ...` status
      messages to the next assistant answer with `langsmith_run_id`, with unit
      coverage
- [x] 3.6 Persist HITL approval status rows as `system_message` and repair old
      persisted `**Selected:** ...` rows at startup so Chainlit does not present
      them as answer-feedback targets
- [x] 3.7 Suppress Chainlit tool-run rows, render state/cost as system messages,
      and send the final answer last so it is the clear feedback target
- [x] 3.8 Preserve Chainlit's default scorable run parent for final answer
      messages so the built-in feedback controls render

## 4. Verification & docs

- [x] 4.1 Manual check with LangSmith configured: rate an answer 👍, verify a
      single `user_score=1.0` on the correct trace; toggle to 👎 and verify one
      feedback with score 0.0; remove the rating and verify deletion
- [x] 4.2 Manual check on a resumed thread after app restart: rating an older
      answer still lands on the original trace
- [x] 4.3 Manual check with LangSmith unconfigured: rating persists locally,
      no errors
- [x] 4.4 Update `CLAUDE.md` (current status + key facts: `user_score` is the
      human quality signal; feedback UI is data-layer driven)
