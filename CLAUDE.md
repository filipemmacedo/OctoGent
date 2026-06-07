# CLAUDE.md - Governed Agent

Project context. Read this fully before acting.

## What this is

A LangGraph + OpenAI tool-calling agent built as a **reference implementation
for governed agentic systems**. It is not a feature demo: the whole point is to
demonstrate *control* over four pillars that matter for enterprise/corporate AI
adoption:

1. **Orchestration & state management** - LangGraph StateGraph, tool-calling loop
2. **Token & cost awareness** - per-node usage tracking + EUR cost, so agents
   cannot get lost or burn money unnoticed
3. **Database / misuse control** - a honeypot canary surface that detects and
   alerts on abuse (confused agent OR prompt injection)
4. **Human-in-the-loop** - approve / edit / reject sensitive actions, with
   feedback written back into state

Guiding principle: **the state object is where governance lives.** The token
ledger, budget flags, feedback, and tool classification all live in graph state
so the system can *show* what it is doing and why. Auditability is the product.

## Domain & access points

A tool-calling assistant over **two tools of deliberately different trust**:

- **SQLite** (`src/tools.py`) - local, owned schema, low cost, deterministic.
  This is the honeypot's future home. Exposed as native LangChain `@tool`s.
- **Google Analytics 4** (`src/mcp_tools.py`, `ga4_mcp_server/`) - loaded through
  `langchain-mcp-adapters`. External, real cost, sensitive analytics data. This
  is where budget + HITL controls matter most.

The agent sees one toolset; the governance layer treats the two differently.

## Current status: Steps 1-2 complete, GA4 running

The current implementation is beyond the original skeleton:

- LangGraph tool-calling loop is working.
- SQLite tools are working.
- GA4 tools are installed and loaded through MCP.
- A local OAuth-based GA4 MCP server exists under `ga4_mcp_server/`.
- Chainlit UI exists in `app.py`, with a persisted SQLite data layer.
- LangGraph state is persisted with `AsyncSqliteSaver` in `.checkpoints/`.
- Token/cost ledger is implemented in `AgentState` and shown in logs/UI.
- The model prompt is trimmed to the last 3 messages before invocation; the
  persisted graph state and token ledger remain cumulative.

Important files:

```
app.py             # Chainlit UI, session persistence, MCP status, state inspector, cost badge
src/state.py       # AgentState: messages + tokens_in + tokens_out + cost_eur
src/tools.py       # SQLite tools (list_tables, describe_table, query_database) + seed
src/mcp_tools.py   # HTTP/stdio MCP config + GA4 tool loading
src/graph.py       # build_graph(): call_model -> tools_condition -> tools -> loop
src/main.py        # CLI entry point: python -m src.main
ga4_mcp_server/    # Local OAuth GA4 MCP server
requirements.txt   # LangGraph/LangChain/OpenAI/MCP/Chainlit deps
.env.example       # OpenAI, GA4 MCP, local OAuth, Chainlit auth config
```

The orchestration loop in `src/graph.py` is still the key seam:
`START -> call_model --(tool calls?)--> tools -> call_model --(else)--> END`,
using prebuilt `ToolNode` + `tools_condition`. Keep it clean; add controls
around it rather than replacing the loop.

## Build roadmap (do strictly in order)

- **Step 1 - Skeleton.** Done.
- **Step 2 - Token ledger.** Done.
  - `AgentState` tracks `tokens_in`, `tokens_out`, and `cost_eur`.
  - `src/graph.py` uses `get_usage_metadata_callback()` around model calls.
  - Spend is printed after each `call_model` node.
  - Chainlit displays a per-session EUR cost badge and state inspector.
- **Step 2.5 - UI/persistence + local GA4 MCP.** Done.
  - Chainlit thread persistence is implemented.
  - LangGraph checkpoints restore full agent state across resumed threads.
  - Local OAuth GA4 MCP server is implemented and archived in OpenSpec.
- **Step 3 - Circuit breaker.** Next.
  - Add budget config via `.env`, e.g. `AGENT_MAX_COST_EUR`.
  - Add a state-visible halt path if cumulative `cost_eur` exceeds the budget.
  - Set/standardize graph `recursion_limit` in invocation config.
  - Make halt decisions observable in logs/UI.
- **Step 4 - Human-in-the-loop.**
  - Use modern `interrupt()` inside a node, resumed with `Command(resume=...)`.
  - Interrupt before executing any tool classified `sensitive`.
  - Human can approve / edit args / reject; decision is written to state.
  - Requires a checkpointer. On resume the node re-executes from the top, so any
    charged call or side effect before `interrupt()` must be idempotent.
- **Step 5 - DB hardening + honeypot.**
  - Keep DB access scoped/read-only.
  - Plant a canary table in SQLite, e.g. `api_keys_backup`, that no legitimate
    query should touch.
  - Pre-execution inspect every query/tool call; any reference to honeypot
    objects is blocked, logged, and alerted.
  - Introduce state-visible tool classification: `safe`, `sensitive`,
    `honeypot`.
- **Step 6 - Persistence + observability.**
  - Consider swapping SQLite checkpointer for Postgres when resume-days-later or
    multi-user durability is needed.
  - Add tracing (LangSmith or Langfuse) as the auditable "show I control" view.

## Key technical facts

- LangGraph loop: `from langgraph.prebuilt import ToolNode, tools_condition`.
- Model: `from langchain.chat_models import init_chat_model`, then
  `init_chat_model(...).bind_tools(tools)`.
- State uses reducers (`add_messages`); schema changes must be deliberate.
- Token tracking uses `get_usage_metadata_callback()` from
  `langchain_core.callbacks`.
- The token ledger is cumulative even though the prompt sent to the model is
  trimmed to the last 3 messages.
- MCP client: `from langchain_mcp_adapters.client import MultiServerMCPClient`;
  `tools = await client.get_tools()`.
- MCP config supports:
  - HTTP: `GA_MCP_URL`, `GA_MCP_AUTH`, `GA_MCP_TRANSPORT=streamable_http`
  - Local stdio: `GA_MCP_TRANSPORT=stdio`, `GA_MCP_COMMAND`, `GA_MCP_ARGS`
- The local GA4 MCP server handles OAuth tokens; the LangGraph app should not
  know refresh tokens or call Google APIs directly.
- HITL should use `interrupt()` + `Command(resume=...)`, not old
  `interrupt_before` / `interrupt_after`.

## Conventions

- Config via `.env` only. Never hardcode secrets, URLs, OAuth tokens, property
  IDs, or budgets.
- Async throughout: use `graph.ainvoke(...)` / `graph.astream_events(...)`.
- Main interactive UI: `chainlit run app.py`.
- CLI path: `python -m src.main`.
- With no GA MCP config, the app runs SQLite-only.
- SQLite tools follow discovery-before-query: list -> describe -> query.
- Keep governance visible: every budget, honeypot, HITL, or routing decision
  should print/log what happened and why.

## Workflow: OpenSpec (spec-driven development)

This project uses OpenSpec for all non-trivial changes. The `openspec/`
directory is the **source of truth**. Update the spec before changing code,
never the other way around.

- **One roadmap step = one OpenSpec change.** Do not bundle steps.
- Start each step with `/opsx:propose "<step description>"`, then move through
  the artifacts in order: proposal -> design -> specs -> tasks -> implement.
- The proposal defines *why/what*, not *how*. Do not jump to code until the
  proposal and specs are agreed.
- Honor artifact locks: tasks stay blocked until design + specs exist.
- When a step is implemented and verified, archive the change and update this
  file so context stays current.
- Keep changes observable: demonstrating control is the goal.

Next OpenSpec change:

`/opsx:propose "Step 3: halt the graph when EUR budget or recursion limits are exceeded"`
