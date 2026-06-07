## Context

The current graph already records cumulative token usage and EUR cost in
`AgentState`. Chainlit streams graph events, persists state by `thread_id`, and
shows the state inspector and session cost badge after each turn. The missing
governance layer is enforcement: the app can show that a run is getting
expensive, but it does not yet stop the agent before another model/tool cycle.

The existing graph shape should remain recognizable:
`START -> call_model -> tools_condition -> tools -> call_model -> END`.
Circuit-breaker logic should be inserted around this loop rather than replacing
it.

## Goals / Non-Goals

**Goals:**

- Enforce a configurable per-session EUR budget using cumulative
  `AgentState.cost_eur`.
- Stop the graph before executing additional tools or model calls once the
  budget is exceeded.
- Standardize the graph recursion limit for both Chainlit and CLI entry points.
- Preserve the existing token ledger and message persistence behavior.
- Make every halt observable in stdout and in user-facing output.

**Non-Goals:**

- No human approval workflow in this change; that belongs to Step 4.
- No honeypot/canary blocking in this change; that belongs to Step 5.
- No Postgres checkpointer migration in this change.
- No dynamic pricing lookup or exchange-rate integration.

## Decisions

### D1: Budget is enforced in the graph after `call_model`

After `call_model` updates `tokens_in`, `tokens_out`, and `cost_eur`, route
through a budget-check decision before `tools_condition`. If the cumulative
cost exceeds the configured limit, route to `END`; otherwise continue through
the existing tool/no-tool routing.

Rationale: `call_model` is where new spend is observed. Checking immediately
after it prevents the next tool call or model cycle from starting when the run
is already over budget.

Alternative considered: check only before `call_model`. That avoids beginning a
model call when already over budget, but misses the moment when a just-completed
call crosses the limit and could still allow a follow-up tool execution.

### D2: Use state fields for budget halt status

Add explicit state fields such as `halted`, `halt_reason`, and
`budget_exceeded`. The budget check returns these fields when it trips, and the
UI reads them from final state to display the halt reason.

Rationale: Governance state should be inspectable and persisted, consistent
with the project principle that state is where governance lives.

Alternative considered: only print a log line. That is observable during a live
run but not durable or inspectable from resumed sessions.

### D3: Recursion limit is enforced through LangGraph run config

Read a configurable recursion limit from `.env` and pass it in the graph config
for Chainlit and CLI invocations. If LangGraph raises a recursion-limit error,
catch it at the entry point, log a clear halt reason, and display it to the user.

Rationale: LangGraph already provides a tested step limit. Using it avoids
duplicating graph-step accounting inside state.

Alternative considered: maintain a custom step counter in `AgentState`. This
would be more state-visible, but it adds extra reducer/schema complexity and
can drift from LangGraph's own recursion accounting.

### D4: Configuration defaults should be safe for local development

Add `.env.example` entries for `AGENT_MAX_COST_EUR` and
`AGENT_RECURSION_LIMIT`. Missing budget config should use a conservative local
default rather than unlimited execution.

Rationale: This is a governed-agent reference implementation. The default
should demonstrate control immediately, while still being easy to override.

Alternative considered: make budget optional/unlimited unless configured. That
is convenient but undermines the Step 3 demonstration.

## Risks / Trade-offs

- [Budget can only be checked after a model call reports usage] -> Use a small
  default budget and stop before any additional tools/model cycles once crossed.
- [LangGraph recursion errors may not return final graph state] -> Handle the
  exception in Chainlit/CLI and surface a clear user-facing halt message.
- [Too-low local defaults may interrupt normal demos] -> Document the `.env`
  settings clearly and keep defaults small but adjustable.
- [Budget checks could obscure final answers if they trip on the final model
  call] -> Prefer governance visibility: if budget is exceeded, show the halt
  reason and preserve the ledger so the user can see why execution stopped.
