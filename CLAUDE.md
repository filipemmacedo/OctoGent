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
  Includes the honeypot canary table and defensive access checks. Exposed as
  native LangChain `@tool`s.
- **Google Analytics 4** (`src/mcp_tools.py`, `ga4_mcp_server/`) - loaded through
  `langchain-mcp-adapters`. External, real cost, sensitive analytics data. This
  is where budget + HITL controls matter most.

The agent sees one toolset; the governance layer treats the two differently.

## Current status: Steps 1-6 implemented

The current implementation is beyond the original skeleton:

- LangGraph tool-calling loop is working.
- SQLite tools are working.
- GA4 tools are installed and loaded through MCP.
- A local OAuth-based GA4 MCP server exists under `ga4_mcp_server/`.
- Chainlit UI exists in `app.py`, with a persisted SQLite data layer.
- LangGraph state is persisted with `AsyncSqliteSaver` in `.checkpoints/`.
- Token/cost ledger is implemented in `AgentState` and shown in logs/UI.
- Circuit breaker controls are implemented: `AGENT_MAX_COST_EUR`,
  `AGENT_RECURSION_LIMIT`, state-visible halt fields, and Chainlit/CLI halt
  output.
- HITL controls are implemented with `interrupt()` / `Command(resume=...)`:
  sensitive GA4 tools require structured approve/edit/reject decisions before
  `ToolNode` execution.
- SQLite honeypot controls are implemented: `api_keys_backup` is seeded with
  fake credential-looking rows, hidden from normal discovery, defensively
  rejected in SQLite tools, blocked at graph level before HITL/tool execution,
  and recorded in `AgentState.honeypot_events`.
- The model prompt is trimmed to the last 3 messages before invocation; the
  persisted graph state and token ledger remain cumulative.
- Step 6 LangSmith observability is implemented for governance events.
  LangSmith traces may show graph nodes like `honeypot_guard`; that only means
  the guard ran. A real canary incident is indicated by `honeypot_events` and
  explicit `governance_event=honeypot_blocked` trace metadata/tags.
- Orchestration metrics are implemented: each `call_model` run gets
  `step_input_tokens`, `step_output_tokens`, `cumulative_tokens_in`,
  `cumulative_tokens_out`, `cumulative_cost_eur`, `model_context_window`, and
  `context_window_pct` as LangSmith metadata, with the chartable subset
  (`context_window_pct`, `cumulative_cost_eur`, `step_input_tokens`) mirrored
  as feedback scores. Tool results are scored as `data_hit` (1.0/0.0) on the
  `tools` run, excluding honeypot-blocked calls. `AGENT_MODEL_CONTEXT_WINDOW`
  configures the context window. `docs/langsmith-metrics.md` documents how to
  read every metric (including the `context_groundedness` online evaluator)
  in the LangSmith UI.
- Human feedback is implemented: Chainlit's built-in 👍/👎 controls (data-layer
  driven, via `LangSmithFeedbackDataLayer` in `app.py`) mirror ratings to
  LangSmith as the `user_score` feedback score on the root run that produced
  the answer. `user_score` is the human answer-quality signal. Each
  `astream_events` invocation gets a pre-generated `run_id`; the final answer
  message stores it as `langsmith_run_id` metadata so ratings on resumed
  threads still resolve after a restart.

Important files:

```
app.py             # Chainlit UI, session persistence, MCP status, state inspector, cost/halt output
src/state.py       # AgentState: messages + tokens/cost + halt + HITL + honeypot event fields
src/tools.py       # SQLite tools (list_tables, describe_table, query_database) + seed + defensive honeypot checks
src/honeypot.py    # SQLite honeypot registry, identifier detection, and governance error helpers
src/mcp_tools.py   # HTTP/stdio MCP config + GA4 tool loading
src/config.py      # governance config: budget and recursion limit
src/graph.py       # build_graph(): call_model -> budget_check -> honeypot_guard -> approval_gate/tools/END
src/observability.py # LangSmith governance event emitters, trace metadata, and sanitization
src/main.py        # CLI entry point: python -m src.main, with recursion-limit handling
ga4_mcp_server/    # Local OAuth GA4 MCP server
requirements.txt   # LangGraph/LangChain/OpenAI/MCP/Chainlit deps
.env.example       # OpenAI, GA4 MCP, local OAuth, Chainlit auth config
```

The orchestration loop in `src/graph.py` is still the key seam:
`START -> call_model -> budget_check --(tool calls?)--> honeypot_guard ->
approval_gate -> tools -> call_model` or `END`. Keep it clean; add controls
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
- **Step 3 - Circuit breaker.** Done.
  - Add budget config via `.env`, e.g. `AGENT_MAX_COST_EUR`.
  - Add a state-visible halt path if cumulative `cost_eur` exceeds the budget.
  - Set/standardize graph `recursion_limit` in invocation config.
  - Make halt decisions observable in logs/UI.
- **Step 4 - Human-in-the-loop.** Done.
  - Use modern `interrupt()` inside a node, resumed with `Command(resume=...)`.
  - Interrupt before executing any tool classified `sensitive`.
  - GA4 MCP tools are classified as `sensitive`; SQLite discovery/query tools
    are statically `safe`, with dynamic honeypot blocking added in Step 5.
  - The human should be triggered by graph state, not by natural-language chat
    parsing: when the latest AI message contains a sensitive tool call, a
    pre-tool approval node calls `interrupt()` with the tool name, args, and
    reason.
  - Chainlit is the approval surface. Show structured controls (approve, edit
    args, reject) using Chainlit actions/forms, then resume the same graph
    thread with `Command(resume=...)`. Do not treat a normal chat reply like
    "yes" as approval.
  - CLI can use a blocking terminal prompt as a fallback approval surface.
  - Human can approve / edit args / reject; decision is written to state as an
    auditable HITL event.
  - Requires a checkpointer. On resume the node re-executes from the top, so any
    charged call or side effect before `interrupt()` must be idempotent.
- **Step 5 - DB hardening + honeypot.** Implemented; archive when reviewed.
  - Keep DB access scoped/read-only.
  - Canary table `api_keys_backup` exists in SQLite with fake rows only; no
    legitimate query should touch it.
  - Pre-execution inspect every query/tool call; any reference to honeypot
    objects is blocked, logged, and recorded.
  - Introduce state-visible tool classification: `safe`, `sensitive`,
    `honeypot`.
- **Step 6 - Persistence + observability.** Implemented; archive when reviewed.
  - Consider swapping SQLite checkpointer for Postgres when resume-days-later or
    multi-user durability is needed.
  - Add LangSmith observability as the auditable "show I control" view for
    governance events.
  - Keep `AgentState` as the source of truth; LangSmith is the searchable trace
    and investigation surface.
  - Emit explicit events such as `honeypot_blocked`, `hitl_decision`, and
    `budget_halt` so seeing a guard node in LangSmith is not confused with a
    real incident.

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
- HITL approval should be implemented as a graph-level gate before `ToolNode`,
  not inside individual tools. The gate classifies pending tool calls and only
  interrupts for `sensitive` actions.
- Honeypot blocking should run before HITL approval. Honeypot calls are
  deny-only and should never be presented for human approval.
- `src/honeypot.py` owns the SQLite canary registry and exact/quoted identifier
  detection for `api_keys_backup`.
- LangSmith automatic traces may show every graph node. Treat explicit
  `honeypot_events` / `governance_event=honeypot_blocked` metadata as the
  signal of an actual canary access attempt.
- In Chainlit, human approval should be structured UI state (actions/forms)
  linked to the pending interrupt. Regular chat messages remain user intent for
  the agent, not governance approval.
- Human answer-quality feedback uses Chainlit's built-in data-layer feedback
  UI (👍/👎), not custom actions. Ratings are mirrored to LangSmith as
  `user_score` (1.0/0.0) with a deterministic `uuid5` feedback id keyed on the
  rated message id, so re-rating updates instead of duplicating and removal
  deletes. Forwarding is optional and non-blocking: local persistence never
  depends on LangSmith.

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
- Observability must be optional and non-blocking: LangSmith tracing should
  never become required for local development or policy enforcement.

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
