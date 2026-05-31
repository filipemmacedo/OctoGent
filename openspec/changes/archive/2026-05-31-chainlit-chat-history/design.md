## Context

The app has two persistence layers that serve different purposes:

- **LangGraph `AsyncSqliteSaver`** (`.checkpoints/chat_history.db`) — stores the full agent state (messages as LangChain objects, token counts, cost). This is the source of truth for conversation state.
- **Chainlit data layer** (missing) — stores thread metadata and display-level message copies for the UI sidebar. Without it, the sidebar is empty and sessions are ephemeral from Chainlit's perspective.

The current workaround (`_list_existing_sessions()` + action buttons) queries the LangGraph checkpoint DB on every new chat start and shows up to 10 past `thread_id`s as clickable actions. This is functional but not the native Chainlit sidebar experience.

## Goals / Non-Goals

**Goals:**
- Thread history appears in the Chainlit sidebar and persists across browser refreshes and server restarts
- Clicking a thread in the sidebar fully restores the conversation (including LangGraph agent state)
- No login screen — anonymous single-user experience
- All data stays on disk (no cloud services)

**Non-Goals:**
- Multi-user support or user authentication
- Thread search or tagging
- Cloud/remote storage
- Replacing the LangGraph checkpointer (it stays as agent state source of truth)

## Decisions

### Decision 1: Use `literalai` / Chainlit's built-in SQLAlchemy data layer

**Chosen**: Install `literalai` and use `cl.SQLAlchemyDataLayer` with a local SQLite URI (`sqlite+aiosqlite:///./data/chainlit.db`).

**Alternatives considered**:
- *Custom `cl.BaseDataLayer`*: Read/write directly to the LangGraph checkpoint DB. Eliminates data duplication but requires implementing ~10 interface methods, many non-trivial. Maintenance burden outweighs the benefit for a local tool.
- *Literal AI cloud*: Requires `LITERAL_API_KEY` and network access. Not disk-based.

**Rationale**: The built-in layer is well-tested and gives the full sidebar experience with minimal code. Data duplication is acceptable — both DBs are local SQLite files under `data/` and `checkpoints/`.

### Decision 2: Fixed anonymous user via `@cl.header_auth_callback`

**Chosen**: Return a hardcoded `cl.User(identifier="local", metadata={"role": "user"})` from a header auth callback. No login screen, no credentials.

**Rationale**: This is a single-user local tool. Chainlit requires a user identity to associate threads with; a fixed anonymous user satisfies that without any login friction.

### Decision 3: `@cl.on_chat_resume` bridges Chainlit → LangGraph

**Chosen**: When a thread is resumed from the sidebar, `on_chat_resume` receives the Chainlit thread dict containing the original `thread_id`. We store that `thread_id` in user session and rebuild the graph with the same `AsyncSqliteSaver` checkpointer. LangGraph automatically restores full state from the checkpoint.

**Rationale**: This keeps LangGraph as the single source of truth for agent state. Chainlit handles UI display; LangGraph handles message history and token ledger.

### Decision 4: Remove the action-button workaround

The `_list_existing_sessions()` function and the `cl.Action` resume buttons in `on_chat_start` become redundant once the sidebar is active. Removing them reduces complexity and avoids duplicate resume paths.

## Risks / Trade-offs

- **Dual storage duplication**: Messages are stored both in Chainlit's DB (as display steps) and in the LangGraph checkpoint DB (as LangChain message objects). → Acceptable for a local tool; both files are small.
- **`CHAINLIT_AUTH_SECRET` must be set**: Chainlit raises an error at startup if the secret is missing when a data layer is configured. → Document clearly in `.env.example`; fail fast with a clear error message.
- **`literalai` version coupling**: Chainlit's data layer API is tied to the `literalai` package version. → Pin the version in `requirements.txt`.

## Migration Plan

1. Add `literalai` to `requirements.txt` and `pip install`
2. Add `CHAINLIT_AUTH_SECRET` to `.env` and `.env.example`
3. Update `app.py` (auth callback + data layer init + `on_chat_resume` + remove workaround)
4. Restart the Chainlit server — existing LangGraph checkpoints remain intact and resumable via sidebar from the first new session onward

No rollback needed; the LangGraph checkpoint DB is unaffected. Reverting means removing the three additions and the `CHAINLIT_AUTH_SECRET` env var.
