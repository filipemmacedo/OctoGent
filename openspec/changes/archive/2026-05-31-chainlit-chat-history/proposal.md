## Why

Chainlit's sidebar shows no thread history because no data layer is configured — every session is ephemeral and previous conversations are lost when the browser is refreshed. The LangGraph checkpointer already persists agent state to disk, but Chainlit has no awareness of it, so the sidebar remains empty.

## What Changes

- Install `literalai` (Chainlit's SQLAlchemy-backed data layer package)
- Add `CHAINLIT_AUTH_SECRET` to `.env` (required for Chainlit to sign sessions, even for anonymous use)
- Add a header auth callback that returns a fixed anonymous user so Chainlit has a user identity to associate threads with
- Configure `cl.SQLAlchemyDataLayer` pointing to a local SQLite file (`data/chainlit.db`)
- Add `@cl.on_chat_resume` callback that restores the `thread_id` into user session and reconnects the graph to the existing LangGraph checkpointer, so conversation state is fully recovered
- Remove the manual `_list_existing_sessions()` workaround and the ad-hoc action buttons (replaced by the native sidebar)

## Capabilities

### New Capabilities

- `chainlit-thread-persistence`: Persist Chainlit threads and messages to a local SQLite database so the sidebar shows conversation history across sessions, and resuming a thread restores the full LangGraph agent state via the checkpointer.

### Modified Capabilities

<!-- No existing capability spec requirements are changing. -->

## Impact

- `app.py` — add auth callback, data layer init, `on_chat_resume` hook; remove `_list_existing_sessions` and action buttons
- `requirements.txt` — add `literalai`
- `.env` / `.env.example` — add `CHAINLIT_AUTH_SECRET`
- `data/chainlit.db` — new SQLite file created at runtime (already gitignored via `data/`)
