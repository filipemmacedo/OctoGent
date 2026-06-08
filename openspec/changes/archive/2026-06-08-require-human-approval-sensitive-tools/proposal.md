## Why

The agent can already observe and halt runaway cost, but it still executes all
model-requested tools automatically once the circuit breaker permits the run.
Sensitive external data access, especially authenticated GA4 MCP calls, needs a
human approval gate so the system can demonstrate control before side effects,
quota usage, or private analytics disclosure happen.

## What Changes

- Add human-in-the-loop approval before executing tools classified as
  `sensitive`.
- Classify SQLite tools as `safe` and GA4 MCP tools as `sensitive` in an
  explicit governance registry.
- Add an approval gate between budget checking and `ToolNode` execution.
- Surface pending sensitive tool calls in Chainlit with structured approve,
  edit, and reject controls.
- Resume interrupted graph execution with the human decision and record that
  decision in `AgentState`.
- Provide a CLI fallback approval path for sensitive tools.
- Preserve current automatic execution for `safe` tools.

## Capabilities

### New Capabilities

- `human-tool-approval`: Human approval, argument editing, rejection, and audit
  state for sensitive tool calls.

### Modified Capabilities

- `agent-loop`: The graph loop routes model-requested tool calls through a
  human approval gate before sensitive tools can execute.

## Impact

- `src/state.py` - add HITL approval/audit fields to `AgentState`.
- `src/graph.py` - add tool classification policy and pre-tool approval gate
  using LangGraph `interrupt()`.
- `app.py` - render Chainlit approval controls and resume the interrupted graph
  with `Command(resume=...)`.
- `src/main.py` - provide terminal approval/edit/reject fallback for CLI runs.
- OpenSpec specs - add `human-tool-approval` and update `agent-loop` behavior.
