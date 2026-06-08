## 1. Tool Policy and State

- [x] 1.1 Add HITL fields to `AgentState` for pending approval metadata and cumulative decision history.
- [x] 1.2 Add a tool governance policy structure that records tool name, source, classification, and reason.
- [x] 1.3 Build tool policies from the separate SQLite and GA4 tool lists before merging tools for graph construction.
- [x] 1.4 Pass tool policies into `build_graph()` from both Chainlit and CLI entry points.
- [x] 1.5 Update Chainlit state inspector and CLI debug output to show HITL pending/decision summaries.

## 2. Graph Approval Gate

- [x] 2.1 Add an approval gate node between `budget_check` and `tools`.
- [x] 2.2 Route safe-only tool calls directly from the approval gate to `ToolNode`.
- [x] 2.3 For sensitive tool calls, call LangGraph `interrupt()` with structured tool approval payload.
- [x] 2.4 On approve resume, record the approval decision and route to `ToolNode`.
- [x] 2.5 On edit resume, replace pending tool call arguments, record original and edited args, and route to `ToolNode`.
- [x] 2.6 On reject resume, append matching rejection `ToolMessage` entries, record the rejection decision, and route back to `call_model`.
- [x] 2.7 Preserve existing budget halt behavior so budget trips route to `END` before approval or tool execution.

## 3. Chainlit Approval UI

- [x] 3.1 Detect LangGraph tool approval interrupts during `graph.astream_events()`.
- [x] 3.2 Render pending sensitive tool details with structured approve, edit, and reject controls.
- [x] 3.3 Resume the interrupted graph thread with `Command(resume=...)` for approve decisions.
- [x] 3.4 Provide a JSON argument editing path and resume with edited args.
- [x] 3.5 Resume rejected tool calls with a rejection reason or comment.
- [x] 3.6 Ensure normal chat messages are not treated as approval while an interrupt is pending.

## 4. CLI Approval Fallback

- [x] 4.1 Detect graph interrupts during CLI invocation.
- [x] 4.2 Prompt in the terminal for approve, edit args, or reject.
- [x] 4.3 Resume the CLI graph with `Command(resume=...)` using the selected decision.
- [x] 4.4 Continue printing state debug output after approval, edit, or rejection.

## 5. Verification

- [x] 5.1 Run a SQLite-only question and verify no approval is requested.
- [x] 5.2 Run a GA4 account/property listing prompt and verify approval is requested before the MCP tool executes.
- [x] 5.3 Approve a GA4 tool call in Chainlit and verify the tool executes and the decision is visible in state.
- [x] 5.4 Edit a GA4 report tool call in Chainlit and verify the edited args are used.
- [x] 5.5 Reject a GA4 tool call in Chainlit and verify the tool does not execute and the model receives a rejection tool result.
- [x] 5.6 Repeat approve/reject coverage through the CLI fallback.
- [x] 5.7 Run a low-budget scenario and verify budget halt still happens before approval or tool execution.
