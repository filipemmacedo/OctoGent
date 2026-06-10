## Why

The agent currently treats SQLite tools as safe once the model requests them, which means prompt injection or model confusion can still steer the agent toward unauthorized database objects. Step 5 adds a honeypot canary surface so misuse is blocked before execution and recorded as an auditable governance event.

## What Changes

- Plant a fake sensitive SQLite canary table, `api_keys_backup`, that no legitimate user workflow should access.
- Hide honeypot objects from normal schema discovery so routine `list_tables` usage remains clean.
- Inspect pending SQLite tool calls before `ToolNode` execution and block any reference to honeypot objects.
- Record each honeypot block in `AgentState` with the tool call, matched object, reason, args, and timestamp.
- Return a governance `ToolMessage` to the model when a honeypot call is blocked, then continue the graph loop without executing the blocked tool.
- Extend tool governance classification with a `honeypot` outcome for dynamic per-call policy decisions.
- Show honeypot event summaries in Chainlit and CLI debug output.

## Capabilities

### New Capabilities

- `sqlite-honeypot-guard`: Detects, blocks, records, and surfaces SQLite honeypot access attempts before tool execution.

### Modified Capabilities

- `agent-loop`: Add a deny-only honeypot guard path before tool execution while preserving budget and HITL ordering.
- `sqlite-tools`: Add the seeded canary table and keep SQLite discovery/read behavior scoped away from honeypot objects.
- `human-tool-approval`: Clarify that honeypot calls are blocked and never offered for human approval.
- `chat-ui`: Display honeypot governance events in the state inspector.

## Impact

- `src/state.py` - add honeypot event fields to `AgentState`.
- `src/tool_policy.py` - extend classification types and policy helpers.
- `src/tools.py` - seed the canary table, filter discovery, and add defensive SQLite checks.
- `src/graph.py` - add or extend the pre-tool governance gate for honeypot detection and blocking.
- `app.py` - include honeypot event summaries in Chainlit session state and state inspector.
- `src/main.py` - include honeypot event summaries in CLI debug output.
- `openspec/specs/*` - update the behavioral contract for database misuse controls.
