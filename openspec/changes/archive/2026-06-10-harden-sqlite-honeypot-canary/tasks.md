## 1. Honeypot Registry and SQLite Tool Hardening

- [x] 1.1 Add a SQLite honeypot registry with `api_keys_backup`, classification `honeypot`, and a human-readable reason.
- [x] 1.2 Add helper logic to detect honeypot object references in table names and SQL text, including quoted SQLite identifier forms.
- [x] 1.3 Update `seed_database()` so it ensures `api_keys_backup` exists with fake credential-looking rows even when business tables are already seeded.
- [x] 1.4 Update `list_tables` to exclude honeypot objects from normal discovery.
- [x] 1.5 Add defensive honeypot rejection inside `describe_table`.
- [x] 1.6 Add defensive honeypot rejection inside `query_database`.

## 2. Graph Governance Guard

- [x] 2.1 Extend `ToolClassification` to include `honeypot`.
- [x] 2.2 Add `honeypot_events` to `AgentState` with an additive reducer.
- [x] 2.3 Add a graph-level honeypot guard that inspects pending tool calls before the approval gate.
- [x] 2.4 Have the guard block any batch containing a honeypot call before `ToolNode` execution.
- [x] 2.5 Record honeypot block events in `AgentState` with tool call ID, tool name, source, classification, matched object, args, action, reason, and timestamp.
- [x] 2.6 Append governance rejection `ToolMessage` entries for blocked honeypot calls and route back to `call_model`.
- [x] 2.7 Preserve existing budget halt behavior so budget trips route to `END` before honeypot inspection.
- [x] 2.8 Preserve existing HITL behavior so sensitive non-honeypot tools still interrupt for approval.

## 3. Chainlit and CLI Observability

- [x] 3.1 Restore `honeypot_events` from checkpoint state during Chainlit session resume.
- [x] 3.2 Store latest `honeypot_events` in Chainlit user session after graph execution.
- [x] 3.3 Update the Chainlit state inspector to show honeypot event count and recent event summaries.
- [x] 3.4 Update CLI debug output to show honeypot event count.
- [x] 3.5 Ensure honeypot blocks are printed or logged with matched object and reason.

## 4. Verification

- [x] 4.1 Verify `list_tables` returns normal business tables and does not include `api_keys_backup`.
- [x] 4.2 Verify `describe_table("api_keys_backup")` is rejected defensively.
- [x] 4.3 Verify `query_database("SELECT * FROM api_keys_backup")` is rejected defensively.
- [x] 4.4 Verify a graph invocation that requests canary access records a honeypot event and does not execute the SQLite query.
- [x] 4.5 Verify a normal SQLite question still follows list -> describe -> query without approval or honeypot blocks.
- [x] 4.6 Verify a GA4 sensitive tool call still triggers HITL approval when no honeypot call is present.
- [x] 4.7 Verify a low-budget scenario still halts before honeypot inspection or tool execution.
