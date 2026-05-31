## 1. Project Scaffold

- [x] 1.1 Create `src/` package directory with `__init__.py`
- [x] 1.2 Create `data/` and `.checkpoints/` directories (add `.gitkeep`, gitignore the `.db` files)
- [x] 1.3 Write `requirements.txt` with all dependencies: `langgraph`, `langchain`, `langchain-openai`, `langchain-community`, `langchain-mcp-adapters`, `chainlit`, `python-dotenv`, `openai`, `aiosqlite`
- [x] 1.4 Write `.env.example` with all variables: `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-4o-mini`, `GA_MCP_URL`, `GA_MCP_AUTH`, `GA_MCP_TRANSPORT=streamable_http`

## 2. AgentState

- [x] 2.1 Write `src/state.py`: define `AgentState` as a `TypedDict` with `messages: Annotated[list, add_messages]`, `tokens_in: int`, `tokens_out: int`, `cost_eur: float`

## 3. SQLite Tools + Seed Data

- [x] 3.1 Write `src/tools.py`: implement `list_tables`, `describe_table`, `query_database` as LangChain `@tool` functions connecting to `data/ecommerce.db`
- [x] 3.2 Add SELECT-only guard to `query_database` (reject any statement not starting with `SELECT`)
- [x] 3.3 Write `seed_database()` function: create and populate `products` (10+ rows, 3 categories), `users` (15 rows with `ga_client_id` in `GA1.2.<n>.<ts>` format), `orders` (30 rows, mixed statuses), `order_items`; skip if data already exists
- [x] 3.4 Call `seed_database()` at module import time so it runs on first `import src.tools`

## 4. MCP / GA4 Tools

- [x] 4.1 Write `src/mcp_tools.py`: implement async `load_ga_tools()` that reads env vars and returns `await client.get_tools()` inside the MCP context manager
- [x] 4.2 Add guard: if `GA_MCP_URL` is not set, log warning and return `[]`

## 5. Token Ledger

- [x] 5.1 Define EUR pricing constants in `src/graph.py`: `PRICE_INPUT_PER_TOKEN`, `PRICE_OUTPUT_PER_TOKEN`, `EUR_USD_RATE`
- [x] 5.2 In the `call_model` node, use `get_usage_metadata_callback()` to capture token usage and update `tokens_in`, `tokens_out`, `cost_eur` in the returned state delta
- [x] 5.3 Print log line after each `call_model` in format: `[tokens] +{in}in/{out}out | session total: €{cost_eur:.6f}`

## 6. LangGraph Graph

- [x] 6.1 Write `src/graph.py`: implement `build_graph(tools)` that creates a `StateGraph(AgentState)` with `call_model` and `tools` nodes, wired with `tools_condition`
- [x] 6.2 Load model with `init_chat_model(os.getenv("OPENAI_MODEL", "gpt-4o-mini"))`, bind all tools
- [x] 6.3 Write system prompt: instructs agent to always call `list_tables` → `describe_table` → `query_database` for SQLite questions; explains `ga_client_id` is the bridge to GA4
- [x] 6.4 Configure `AsyncSqliteSaver` from `.checkpoints/chat_history.db` as the graph checkpointer
- [x] 6.5 Return the compiled graph from `build_graph()`

## 7. CLI Entry Point

- [x] 7.1 Write `src/main.py`: async `main()` that calls `load_ga_tools()`, calls `build_graph(tools)`, then runs a simple `input()` loop invoking `graph.ainvoke()` with a fixed `thread_id="cli-session"`, printing the final AI message
- [x] 7.2 Verify `python -m src.main` runs end-to-end with at least one SQLite question

## 8. Chainlit UI

- [x] 8.1 Write `app.py`: `@cl.on_chat_start` hook that loads GA tools, builds graph, stores compiled graph and a new UUID `thread_id` in `cl.user_session`
- [x] 8.2 Write `@cl.on_message` handler: invokes the graph with the user message and current `thread_id`, streams the final AI message back to the Chainlit UI
- [x] 8.3 Display tool call steps as Chainlit `Step` objects so the user can see which tools fired
- [x] 8.4 After each response, append a cost badge message: `💰 €{cost_eur:.6f} this session`
- [x] 8.5 Add session sidebar: on startup, query the checkpoint DB for distinct `thread_id`s and render them as a Chainlit action list; clicking one sets the session's `thread_id` to resume that history
- [x] 8.6 Verify `chainlit run app.py` starts, accepts a message, and returns an answer with visible cost

## 9. Verification

- [x] 9.1 Ask the agent: "What tables do you have access to?" — confirm it calls `list_tables`
- [x] 9.2 Ask: "What are the top 5 products by total revenue?" — confirm it calls `describe_table` then `query_database`
- [x] 9.3 Ask a GA4 question (if MCP is live) — confirm it routes to GA4 tools
- [x] 9.4 Restart the app, select a previous session from the sidebar — confirm message history loads
- [x] 9.5 Send several messages and confirm the EUR cost accumulates correctly in the badge
- [x] 9.6 Try "DROP TABLE products" — confirm the tool rejects it with the SELECT-only error
