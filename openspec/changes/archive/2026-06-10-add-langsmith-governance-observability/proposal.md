## Why

Governance controls are now visible in `AgentState`, Chainlit, CLI output, and stdout, but they are not easy to search, filter, or investigate across runs. Step 6 adds LangSmith observability so honeypot blocks, HITL decisions, and budget halts can be reviewed in a central trace timeline.

## What Changes

- Add a governance observability layer that emits structured LangSmith trace metadata/tags for governance events.
- Record honeypot blocks as explicit traceable events only when a block actually occurs, not merely when the `honeypot_guard` node runs.
- Attach per-run governance metadata for cost, budget halt state, HITL decision counts, and honeypot event counts.
- Keep `AgentState` as the source of truth; observability is a mirrored investigation surface, not policy authority.
- Configure observability via `.env`, with safe no-op behavior when LangSmith tracing is not configured.
- Document how to filter LangSmith traces for governance events.

## Capabilities

### New Capabilities
- `governance-observability`: Emits structured, searchable observability records for governance events and run-level governance state.

### Modified Capabilities
- `agent-loop`: Add trace metadata/tags around governance decisions while preserving existing routing and state behavior.
- `chat-ui`: Ensure Chainlit graph invocations carry useful LangSmith run metadata for session-level investigation.

## Impact

- `src/observability.py` - new helper module for traceable governance event emission and run metadata construction.
- `src/graph.py` - call observability helpers from governance nodes, especially honeypot blocks and budget halts.
- `app.py` - pass Chainlit thread/session metadata into graph run configs where appropriate.
- `src/main.py` - pass CLI thread/session metadata into graph run configs where appropriate.
- `.env.example` - document LangSmith environment variables and project naming.
- `CLAUDE.md` - update roadmap/status so Step 5 is complete and Step 6 is the next proposed change.
- `openspec/specs/*` - add or modify behavioral contracts for governance observability.
