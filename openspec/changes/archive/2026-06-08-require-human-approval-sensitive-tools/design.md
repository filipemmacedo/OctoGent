## Context

The current agent uses a custom LangGraph loop with `call_model`,
`budget_check`, and a prebuilt `ToolNode`. Step 3 added budget and recursion
limits, so the graph can stop runaway execution, but tool execution is still
automatic once a model call produces tool calls. The two tool sources have
different trust profiles: local SQLite tools are deterministic and read-only,
while GA4 MCP tools access authenticated external analytics data and may use API
quota.

The graph already uses `AsyncSqliteSaver`, and Chainlit already preserves the
thread ID and graph state across resumed sessions. That makes the project ready
for LangGraph's modern `interrupt()` and `Command(resume=...)` human-in-the-loop
pattern.

## Goals / Non-Goals

**Goals:**

- Require human approval before executing sensitive tool calls.
- Classify tools explicitly in code rather than relying on model prompt text.
- Treat GA4 MCP tools as sensitive by default and SQLite tools as safe for this
  step.
- Let a human approve, edit arguments, or reject a sensitive tool call.
- Record pending approvals and human decisions in `AgentState`.
- Keep safe SQLite tool execution automatic.
- Preserve the existing budget-check and recursion-limit behavior.
- Support Chainlit as the main approval surface and CLI as a fallback surface.

**Non-Goals:**

- No honeypot/canary table or SQL canary blocking; that belongs to Step 5.
- No per-user authorization roles or multi-approver workflow.
- No write-capable GA4 operations; the GA4 MCP server remains read-only.
- No migration from SQLite checkpointer to Postgres.
- No approval for every model response; only sensitive tool calls are gated.

## Decisions

### D1: Classify tools from the source lists

Build a tool governance registry before compiling the graph. SQLite tools are
registered as `safe`; GA4 MCP tools are registered as `sensitive`.

Rationale: `app.py` and `src.main.py` already load SQLite and GA4 tools as
separate lists before merging them. Preserving that boundary makes
classification deterministic and avoids brittle name-prefix or description
parsing.

Alternative considered: ask the model to decide whether a tool is sensitive.
Rejected because governance policy must be deterministic and auditable, not
model-inferred.

### D2: Insert an approval gate before `ToolNode`

Add a graph node after `budget_check` and before `tools`. If the latest AI
message contains only safe tool calls, route directly to `tools`. If it contains
one or more sensitive calls, the approval node calls `interrupt()` with a
structured payload describing the pending calls.

Rationale: The gate sits exactly at the control point where the model has
requested tools but no tool side effect or external access has happened yet.

Alternative considered: wrap individual tools. Rejected because approval logic
would be spread across tool implementations and would be harder to audit,
especially for MCP tools loaded dynamically.

### D3: Chainlit uses structured approval controls

Chainlit should detect graph interrupts, display the pending tool call name,
arguments, classification, and reason, and collect one of three decisions:
approve, edit args, or reject. It then resumes the same graph thread with
`Command(resume=...)`.

Rationale: Approval is governance state, not chat intent. Structured controls
avoid treating ordinary messages like "yes" as authorization.

Alternative considered: allow the user to type approval into chat. Rejected
because natural-language replies are ambiguous and difficult to audit.

### D4: Rejected tool calls are returned to the model as tool results

When a sensitive call is rejected, the approval node should append a
`ToolMessage` for the rejected tool call explaining that a human rejected it,
then route back to `call_model`. The model can then produce a final answer that
acknowledges the denied access.

Rationale: Tool-calling models expect every tool call to receive a matching tool
result. Returning rejection as a tool result keeps the transcript valid.

Alternative considered: end the graph immediately after rejection. Rejected
because it prevents the assistant from giving the user a useful final response.

### D5: Edited arguments replace the pending tool call before execution

When a human edits arguments, the approval node should update the pending AI
message's tool call arguments and then route to `tools`. The decision record
should keep both original and edited arguments.

Rationale: Editing is approval with a constrained correction. The actual tool
execution should use exactly what the human approved.

Alternative considered: create a new model call asking the model to restate the
tool call with edited args. Rejected because it adds cost and can drift from the
approved values.

### D6: HITL state is append-only audit data

Add state fields for pending approval metadata and a cumulative list of HITL
decisions. Decision records include tool call ID, tool name, classification,
original args, final args, decision, reason/comment, and timestamp.

Rationale: The project principle is that governance lives in state. Approval
history should be inspectable in Chainlit and durable in checkpoints.

Alternative considered: only print approval events. Rejected because logs are
less durable and cannot be inspected from resumed graph state.

## Risks / Trade-offs

- [Interrupt streaming shape differs between LangGraph versions] -> Verify the
  local event payloads in Chainlit before finalizing the UI handling.
- [Edited args may fail schema validation] -> Let the underlying tool or
  `ToolNode` return the validation error and route back to the model.
- [Multiple sensitive tool calls in one AI message complicate UI] -> Approve,
  edit, or reject the pending calls as a batch in Step 4; defer per-call
  multi-step approval unless needed later.
- [GA4 list operations are read-only but still sensitive] -> Classify all GA4
  MCP tools as sensitive for a conservative enterprise-governance demo.
- [CLI approval interrupts async flow] -> Use a simple blocking terminal prompt
  as fallback; Chainlit remains the primary experience.

## Migration Plan

1. Add HITL state fields with safe defaults so existing checkpoints continue to
   load with `.get(...)` fallback access.
2. Add tool policy construction where SQLite and GA4 tool lists are still
   separate.
3. Insert the approval gate into the graph without replacing the existing
   budget and tool execution nodes.
4. Update Chainlit and CLI entry points to resume interrupts.
5. Verify safe SQLite questions still run without approval and GA4 questions
   pause for human decision.

Rollback is straightforward: route `budget_check` directly to `tools` again and
ignore HITL state fields in the UI.

## Open Questions

- Should Step 4 approve all sensitive calls in a model message as one batch, or
  require separate decisions per tool call? The first implementation should use
  batch approval unless the UI becomes confusing.
- Should edited args be captured through a compact JSON text box or a fuller
  form built from each tool schema? A JSON text box is sufficient for Step 4;
  schema-driven forms can come later.
