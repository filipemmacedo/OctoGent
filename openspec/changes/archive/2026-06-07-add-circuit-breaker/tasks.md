## 1. Configuration

- [x] 1.1 Add `.env.example` entries for `AGENT_MAX_COST_EUR` and `AGENT_RECURSION_LIMIT`.
- [x] 1.2 Add config parsing helpers for budget and recursion limit with documented local defaults.
- [x] 1.3 Ensure invalid config values fail clearly or fall back with an observable warning.

## 2. State Schema

- [x] 2.1 Extend `AgentState` with circuit-breaker fields for halted status, budget exceeded status, and halt reason.
- [x] 2.2 Update CLI state debug output to include the new circuit-breaker fields.
- [x] 2.3 Update Chainlit state inspector output to include the new circuit-breaker fields.

## 3. Graph Circuit Breaker

- [x] 3.1 Add a budget-check routing function that reads cumulative `cost_eur` from state.
- [x] 3.2 Route `call_model` through the budget check before `tools_condition`.
- [x] 3.3 When budget is exceeded, return/persist halt state and route to `END` before additional tools or model calls.
- [x] 3.4 Print an observable budget halt log line with current cost, configured budget, and halt reason.

## 4. Invocation Loop Limits

- [x] 4.1 Pass configured `recursion_limit` in Chainlit `graph.astream_events()` config.
- [x] 4.2 Pass configured `recursion_limit` in CLI `graph.ainvoke()` config.
- [x] 4.3 Catch LangGraph recursion-limit failures in Chainlit and show a clear loop-limit halt message.
- [x] 4.4 Catch LangGraph recursion-limit failures in CLI and print a clear loop-limit halt message.

## 5. User-Facing Halt Output

- [x] 5.1 Show a Chainlit message when the final state indicates a budget halt.
- [x] 5.2 Preserve the normal final assistant answer path when no circuit breaker trips.
- [x] 5.3 Ensure cost badge and state inspector still render after budget halts when final state is available.

## 6. Verification

- [x] 6.1 Run the app with a very low `AGENT_MAX_COST_EUR` and verify a budget halt is logged and shown in Chainlit.
- [x] 6.2 Run the CLI with a very low `AGENT_MAX_COST_EUR` and verify the graph stops before further tool/model cycles.
- [x] 6.3 Run with a low `AGENT_RECURSION_LIMIT` and verify Chainlit/CLI show loop-limit halt messages.
- [x] 6.4 Run a normal SQLite-only query under budget and verify the existing tool loop still works.
- [x] 6.5 Run a normal GA4 query under budget and verify MCP tool usage still works when configured.
