## Context

Greenfield project. No code exists. The goal is a working chat application where a LangGraph ReAct agent reasons over two data sources — a local SQLite e-commerce database and a live GA4 MCP server — and answers natural-language questions about their intersection (e.g., "which acquisition channel drives the most revenue?").

The system is designed as a learning scaffold: governance controls (circuit breaker, HITL, honeypot) will be added in subsequent steps. Every decision here must keep the core graph loop clean so those layers can be surgically inserted later without rewrites.

## Goals / Non-Goals

**Goals:**
- Full end-to-end path: chat input → LangGraph agent → tool calls → synthesized answer
- Persistent chat sessions on disk via `SqliteSaver` checkpointer
- Chainlit UI with session sidebar and live EUR cost display
- Token usage in `AgentState` from day one
- GA4 MCP connection with graceful SQLite-only fallback
- E-commerce seed data with a `ga_client_id` bridge column linking to GA4

**Non-Goals:**
- Authentication or multi-user isolation
- Circuit breaker, budget enforcement, or HITL (Steps 3–4)
- Honeypot / DB hardening (Step 5)
- Postgres checkpointer or LangSmith tracing (Step 6)
- Production deployment or error recovery beyond logging

## Decisions

### D1: Chainlit over Streamlit for the UI

**Decision:** Use Chainlit (`chainlit run app.py`).

**Rationale:** Chainlit is natively async — no `asyncio.run()` workarounds needed to bridge Streamlit's sync execution model with LangGraph's async graph and MCP tool calls. It also renders tool-call steps out of the box (user sees which tools fired and how long they took), which directly serves the "demonstrating control is the goal" principle from `CLAUDE.md`. Streamlit would require `st.cache_resource` hacks and a sync wrapper that could break under certain MCP client lifecycle scenarios.

**Alternative considered:** Streamlit with `@st.cache_resource` for the graph — rejected because MCP client reconnection in a cached resource is fragile during development iteration.

---

### D2: Custom ReAct graph over `create_react_agent` prebuilt

**Decision:** Build the graph manually: `START → call_model → tools_condition → tools → call_model → END`.

**Rationale:** `CLAUDE.md` explicitly calls this out. A custom graph exposes the seams where governance nodes (budget check, HITL interrupt, honeypot inspector) will be inserted in Steps 3–5. Using `create_react_agent` would require unwrapping it later. The manual graph is ~30 lines and trivially understood.

**Alternative considered:** `create_react_agent` for speed — rejected because it hides the graph topology that is the learning objective.

---

### D3: Token ledger in `AgentState` from day one

**Decision:** Add `tokens_in: int`, `tokens_out: int`, `cost_eur: float` to `AgentState` with plain `int`/`float` fields (no reducer — overwrite each time) accumulated via `get_usage_metadata_callback()` per node invocation.

**Rationale:** The user's primary concern is cost. Wiring the ledger in Step 1 means every message shows its EUR cost in the UI, making the constraint visible from the first test query. Adding it later would require a state schema migration. EUR price for `gpt-4o-mini`: input $0.15/MTok → ~€0.14/MTok, output $0.60/MTok → ~€0.55/MTok (USD/EUR ≈ 0.92).

**Alternative considered:** Add in Step 2 per the original roadmap — rejected because the user explicitly called cost awareness as a day-one requirement.

---

### D4: `gpt-4o-mini` as default model

**Decision:** Default `OPENAI_MODEL=gpt-4o-mini` in `.env.example`.

**Rationale:** 13× cheaper than `gpt-4.1`. Sufficient for SQL schema inspection, tool routing, and GA4 query construction. The model is env-configurable so upgrading is one-line change. The circuit breaker in Step 3 will make the upgrade decision data-driven anyway.

---

### D5: Two separate SQLite files

**Decision:** `data/ecommerce.db` for app data, `.checkpoints/chat_history.db` for LangGraph state.

**Rationale:** Mixing them would create schema conflicts (LangGraph's checkpoint tables alongside business tables) and make the `list_tables` tool confuse LangGraph internals with e-commerce schema. Separation is clean and matches how a real app would be structured.

---

### D6: `ga_client_id` bridge column in `users` table

**Decision:** Seed `users.ga_client_id` with plausible-format fake IDs (e.g., `"GA1.2.123456789.1717000000"`). Document that real IDs can be backfilled by querying GA4 once the agent is running.

**Rationale:** Real `client_id`s require a live GA4 query before the app exists. Fake IDs let the skeleton run immediately and teach the cross-source reasoning pattern. The agent will correctly formulate the join logic even if no matches return from GA4. The backfill path is a natural first real-world query once the skeleton is verified.

---

### D7: `SqliteSaver` checkpointer for session persistence

**Decision:** Use `langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver` (async variant, matches Chainlit's async runtime).

**Rationale:** Each Chainlit session gets a UUID `thread_id`. The checkpointer writes full graph state (all messages, token ledger) after every node. Resuming a session means passing the same `thread_id` to `graph.ainvoke()` — history reconstructs automatically. The UI sidebar lists sessions by reading distinct `thread_id`s from the checkpoint DB.

## Risks / Trade-offs

**[MCP client lifecycle]** → The `MultiServerMCPClient` must be entered as an async context manager. In Chainlit, we initialise it once in `@cl.on_chat_start` and store it in the Chainlit user session. If the GA4 MCP server is unreachable, `load_ga_tools()` returns `[]` and logs a warning — the agent runs SQLite-only without crashing.

**[Token accumulation across turns]** → `AgentState` accumulates tokens across the full session (not per message). The UI displays the running session total. Per-message cost requires threading the callback result back per invocation — deferred to Step 2 refinement.

**[Fake GA4 client IDs]** → Cross-source queries (SQLite users → GA4 sessions) will return no matches until real `ga_client_id`s are backfilled. The agent will correctly report "no matching sessions found" rather than hallucinating. This is acceptable for Step 1.

**[SqliteSaver async import]** → `AsyncSqliteSaver` requires `aiosqlite` as an extra dependency. Add to `requirements.txt`.

## Open Questions

- Should the Chainlit session sidebar show only the session UUID, or should the agent auto-generate a session title from the first message? (Deferred — can be added cosmetically without touching the graph.)
- EUR/USD conversion: hardcode at 0.92 or pull from env? (Hardcode for now; revisit in Step 2 when ledger is formalized.)
