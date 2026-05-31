## Why

This project has no code yet. We need a working walking skeleton — a chat UI backed by a LangGraph ReAct agent — so we have something real to run, query, and iterate on before adding governance controls. Step 1 establishes the full end-to-end path: user types a question, the agent reasons over SQLite e-commerce data and GA4 analytics via MCP, and answers with a traceable tool-call chain.

## What Changes

- New Python package under `src/` with agent state, tools, MCP loader, and LangGraph graph
- New Chainlit chat UI (`app.py`) with session sidebar and live token/cost display
- SQLite e-commerce database seeded on first run (`data/ecommerce.db`)
- LangGraph `SqliteSaver` checkpointer persisting all chat sessions to disk (`.checkpoints/chat_history.db`)
- Token usage (input/output tokens + EUR cost) tracked in `AgentState` from day one and displayed per message
- GA4 connection via MCP (`langchain-mcp-adapters`); app runs SQLite-only if `GA_MCP_URL` is not set
- Model defaulting to `gpt-4o-mini` (env-configurable); system prompt enforces discovery-before-query pattern
- `.env.example` with all required and optional variables

## Capabilities

### New Capabilities

- `agent-loop`: LangGraph ReAct loop — `call_model → tools_condition → tools → call_model` cycle with `ToolNode`, `tools_condition`, and `SqliteSaver` checkpointer
- `sqlite-tools`: Three LangChain `@tool` functions (`list_tables`, `describe_table`, `query_database`) plus `seed_database()` that populates e-commerce dummy data on first run
- `mcp-ga4-tools`: `load_ga_tools()` async loader via `MultiServerMCPClient`; returns empty list and logs a warning if `GA_MCP_URL` is unset
- `token-ledger`: Per-node token accumulation (`tokens_in`, `tokens_out`, `cost_eur`) in `AgentState` using `get_usage_metadata_callback()`; EUR pricing for `gpt-4o-mini`
- `chat-ui`: Chainlit app with chat window, session sidebar (lists all persisted thread IDs), and per-message cost badge

### Modified Capabilities

*(none — greenfield)*

## Impact

- **New files**: `app.py`, `src/state.py`, `src/tools.py`, `src/mcp_tools.py`, `src/graph.py`, `src/main.py`, `data/` (created at runtime), `.checkpoints/` (created at runtime), `.env.example`, `requirements.txt`
- **Dependencies added**: `langgraph`, `langchain`, `langchain-openai`, `langchain-community`, `langchain-mcp-adapters`, `chainlit`, `python-dotenv`, `openai`
- **External services**: OpenAI API (gpt-4o-mini), GA4 MCP server (optional)
- **No breaking changes** — greenfield project
