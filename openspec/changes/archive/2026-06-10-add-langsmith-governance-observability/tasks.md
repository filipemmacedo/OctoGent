## 1. Observability Helpers

- [x] 1.1 Add `src/observability.py` with helpers for governance tags, run metadata, and safe event sanitization.
- [x] 1.2 Add a traceable `emit_honeypot_blocked` helper that emits `governance_event=honeypot_blocked` with tags including `governance`, `security`, `honeypot`, and `blocked`.
- [x] 1.3 Add a traceable `emit_hitl_decision` helper that emits `governance_event=hitl_decision` with decision, tool name, source, and classification.
- [x] 1.4 Add a traceable `emit_budget_halt` helper that emits `governance_event=budget_halt` with halt reason and cost/budget values.
- [x] 1.5 Ensure all observability helpers catch/log their own failures and never change graph routing or state updates.

## 2. Graph Integration

- [x] 2.1 Emit honeypot observability only after `honeypot_guard` creates a real `honeypot_events` record.
- [x] 2.2 Emit budget halt observability only when `budget_check` sets `halted=True` and `budget_exceeded=True`.
- [x] 2.3 Emit HITL observability after approve/edit/reject decisions are recorded in `hitl_decisions`.
- [x] 2.4 Preserve existing `AgentState` as the source of truth for honeypot events, HITL decisions, budget state, and token/cost ledger.
- [x] 2.5 Confirm normal `honeypot_guard` execution without a matched canary does not emit a `honeypot_blocked` event.

## 3. Invocation Metadata

- [x] 3.1 Extend graph run config construction to include governance tags and metadata without removing `thread_id` or `recursion_limit`.
- [x] 3.2 Pass Chainlit interface metadata and Chainlit thread ID into graph streaming invocations.
- [x] 3.3 Pass CLI interface metadata and CLI thread ID into graph invocations.
- [x] 3.4 Ensure trace metadata is inherited by child LangGraph/LangChain runs in LangSmith.

## 4. Configuration and Documentation

- [x] 4.1 Update `.env.example` with optional `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, and `LANGSMITH_ENDPOINT` entries.
- [x] 4.2 Document recommended LangSmith filters for governance investigations, including `tag:honeypot` and `governance_event=honeypot_blocked`.
- [x] 4.3 Document that seeing the `honeypot_guard` node in LangSmith is normal and does not by itself indicate intrusion.
- [x] 4.4 Keep LangSmith optional so local SQLite-only runs work without LangSmith credentials.

## 5. Verification

- [x] 5.1 Verify `python -m compileall src app.py` passes.
- [x] 5.2 Verify a normal SQLite question runs without emitting a `honeypot_blocked` event.
- [x] 5.3 Verify a canary access attempt records `honeypot_events` and emits a LangSmith-searchable `honeypot_blocked` event when tracing is enabled.
- [x] 5.4 Verify a sensitive GA4-style tool call still interrupts for HITL and emits `hitl_decision` after approve/edit/reject.
- [x] 5.5 Verify a low-budget scenario halts before tool execution and emits `budget_halt`.
- [x] 5.6 Verify the app runs with LangSmith environment variables absent.
- [x] 5.7 Verify LangSmith traces include interface and thread metadata for both Chainlit and CLI.
