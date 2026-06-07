## Why

The agent already observes token usage and EUR cost, but observation alone does
not prevent runaway model/tool loops or expensive GA4 interactions. This change
adds an enforceable circuit breaker so governance state can stop execution when
a configured budget or graph-step limit is reached.

## What Changes

- Add configurable per-session budget enforcement using cumulative
  `AgentState.cost_eur`.
- Add explicit state fields that record whether execution was halted and why.
- Add graph routing that stops before another model/tool cycle once the budget
  is exceeded.
- Standardize the LangGraph `recursion_limit` used by Chainlit and CLI
  invocations.
- Surface circuit-breaker decisions in logs and user-visible output.

## Capabilities

### New Capabilities

- `circuit-breaker`: Budget and loop-limit governance for stopping agent runs
  when configured execution limits are exceeded.

### Modified Capabilities

- `agent-loop`: The graph loop can now terminate because a governance circuit
  breaker tripped, not only because the model produced a final response.

## Impact

- `src/state.py` - add state fields for circuit-breaker status and stop reason.
- `src/graph.py` - add budget-check routing around the existing loop.
- `app.py` - pass recursion-limit config and display halt reasons in the UI.
- `src/main.py` - pass recursion-limit config for CLI runs.
- `.env.example` - document budget and recursion-limit configuration.
- OpenSpec specs - add `circuit-breaker` and update `agent-loop` behavior.
