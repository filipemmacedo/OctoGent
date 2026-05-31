## 1. Dependencies & Environment

- [x] 1.1 Add `literalai` to `requirements.txt` and install it
- [x] 1.2 Add `CHAINLIT_AUTH_SECRET` (random string) to `.env` and document it in `.env.example`

## 2. Chainlit Data Layer Setup

- [x] 2.1 Add `@cl.header_auth_callback` to `app.py` returning a fixed anonymous `cl.User(identifier="local")`
- [x] 2.2 Instantiate `cl.SQLAlchemyDataLayer` with `sqlite+aiosqlite:///./data/chainlit.db` and set it as the active data layer at module level in `app.py`

## 3. Thread Resume Hook

- [x] 3.1 Add `@cl.on_chat_resume` callback that reads `thread["metadata"]["thread_id"]` and stores it in user session, rebuilds the graph with the existing checkpointer so LangGraph restores full agent state
- [x] 3.2 Update `on_chat_start` to store the new `thread_id` into the Chainlit thread metadata so `on_chat_resume` can retrieve it

## 4. Cleanup

- [x] 4.1 Remove `_list_existing_sessions()` function and the `cl.Action` resume buttons from `on_chat_start`

## 5. Verification

- [x] 5.1 Run the app — started at http://localhost:8000, DB tables confirmed, JWT auth working
- [x] 5.2 Refresh the browser and confirm the thread is still visible in the sidebar
- [x] 5.3 Click the thread in the sidebar and confirm the conversation history is restored and a follow-up message continues correctly
- [x] 5.4 Restart the server and confirm threads persist
