# CLAUDE.md — Governed Agent

Project context. Read this fully before acting.

## What this is

A LangGraph + OpenAI tool-calling agent built as a **reference implementation
for governed agentic systems**. It is not a feature demo — the whole point is to
demonstrate *control* over four pillars that matter for enterprise/corporate AI
adoption:

1. **Orchestration & state management** — LangGraph StateGraph, tool-calling loop
2. **Token & cost awareness** — per-node usage tracking + EUR cost, so agents
   can't get lost or burn money
3. **Database / misuse control** — a honeypot canary surface that detects and
   alerts on abuse (confused agent OR prompt injection)
4. **Human-in-the-loop** — approve / edit / reject sensitive actions, with
   feedback written back into state

Guiding principle: **the state object is where governance lives.** The token
ledger, budget flags, feedback, and tool classification all live in graph state
so the system can *show* what it's doing and why — auditability is the product.

## Domain & access points

A tool-calling assistant over **two tools of deliberately different trust**:

- **SQLite** (`src/tools.py`) — local, we own the schema. Low cost, deterministic.
  This is the honeypot's home. Exposed as native LangChain `@tool`s.
- **Google Analytics** (`src/mcp_tools.py`) — loaded from the user's running MCP
  server via `langchain-mcp-adapters`. External, real cost, sensitive data. This
  is where budget + HITL controls matter most.

The agent sees one toolset; the governance layer treats the two differently.

## Current status: Step 1 complete (skeleton)

Working tool-calling loop, no controls yet. Files:

```
src/state.py      # AgentState: messages + add_messages reducer (grows each step)
src/tools.py      # SQLite tools (list_tables, describe_table, query_database) + seed
src/mcp_tools.py  # load_ga_tools() via MultiServerMCPClient, env-configured
src/graph.py      # build_graph(): call_model -> tools_condition -> tools -> loop
src/main.py       # entry point: python -m src.main
requirements.txt  # langgraph, langchain, langchain-openai, langchain-mcp-adapters, python-dotenv
.env.example      # OPENAI_API_KEY, OPENAI_MODEL, GA_MCP_URL, GA_MCP_AUTH, GA_MCP_TRANSPORT
```

The orchestration loop in `graph.py` is the seam everything else plugs into:
`START -> call_model --(tool calls?)--> tools -> call_model --(else)--> END`,
using prebuilt `ToolNode` + `tools_condition`. Keep it clean; add controls
*around* it, don't rewrite it.

## Build roadmap (do strictly in order, each must run before the next)

- **Step 1 — Skeleton.** ✅ Done.
- **Step 2 — Token ledger.** Attach LangChain's `UsageMetadataCallbackHandler`
  / `get_usage_metadata_callback()` (node-level usage works with LangGraph).
  Accumulate input/output tokens + EUR cost into `AgentState`. Print spend per
  node. EUR cost source: pricepertoken.com pricing (USD→EUR), per the user's
  existing API Guard work.
- **Step 3 — Circuit breaker.** Conditional edge that halts the graph if the run
  exceeds a EUR budget OR a recursion/loop limit (`recursion_limit` in config +
  an explicit budget check reading the ledger from state).
- **Step 4 — Human-in-the-loop.** Use the modern `interrupt()` function inside a
  node, resumed with `Command(resume=...)`. Interrupt before executing any tool
  classified `sensitive`. Human can approve / edit args / reject; decision is
  written to state. Requires a checkpointer. CRITICAL: on resume the node
  re-executes from the top, so any charged call / side effect before the
  `interrupt()` must be idempotent.
- **Step 5 — DB hardening + honeypot.** Scoped read-only DB role. Plant a canary
  table in SQLite (e.g. `api_keys_backup`) that no legitimate query touches.
  Pre-execution inspection of every query/tool call: any reference to a honeypot
  object → block, log, alert. Optionally a canary GA property/tool. Introduce a
  tool classification in state: `safe` (auto) / `sensitive` (HITL) / `honeypot`
  (block+alert) — this drives routing.
- **Step 6 — Persistence + observability.** Swap in-memory checkpointer for
  Postgres (survives restarts, enables resume-days-later). Add tracing
  (LangSmith or Langfuse) as the auditable "show I control" view.

## Key technical facts (current as of mid-2026 — verify against docs if unsure)

- LangGraph loop: `from langgraph.prebuilt import ToolNode, tools_condition`;
  model via `from langchain.chat_models import init_chat_model` →
  `init_chat_model("openai:gpt-4o-mini")`; `model.bind_tools(tools)`.
- State uses reducers (`add_messages`); >60% of production agent incidents trace
  to state management, so design schema changes deliberately.
- HITL: `interrupt()` + `Command(resume=...)` (NOT the old
  `interrupt_before`/`interrupt_after`). Needs a checkpointer to persist across
  the pause. Node re-executes on resume → idempotency required.
- Token tracking: `UsageMetadataCallbackHandler` /
  `get_usage_metadata_callback()` (langchain-core ≥ 0.3.49). Pass via the run
  config `callbacks`; works per-node in LangGraph for cost attribution.
- MCP: `from langchain_mcp_adapters.client import MultiServerMCPClient`;
  `tools = await client.get_tools()`. Server config dict supports `url`,
  `transport` ("streamable_http" or "sse"/"stdio"), and `headers` for auth.
  MCP servers run as separate processes and can't see graph state; "interceptors"
  offer middleware-style control over MCP tool calls if needed, but prefer
  enforcing budget/honeypot/HITL at the graph level where full state is visible.

## Conventions

- Config via `.env` only — never hardcode secrets, URLs, or budgets.
- Async throughout (MCP tools are async): use `graph.ainvoke(...)`.
- Run with `python -m src.main` from the project root.
- The user has a real GA MCP server running; its URL/auth go in `.env`
  (`GA_MCP_URL`, `GA_MCP_AUTH`). With no URL set, the app runs SQLite-only.
- SQLite tools follow a discovery-before-query pattern (list → describe → query)
  so the model inspects schema instead of hallucinating it.

## Working style

Step by step. Build one layer, confirm it runs, then add the next. Prefer
surgical edits that insert nodes/edges around the existing loop over rewrites.
When adding a control, also make it *observable* (print/log the decision) —
demonstrating control is the goal, not just having it.

## Workflow: OpenSpec (spec-driven development)

This project uses OpenSpec for all non-trivial changes. The `openspec/`
directory is the **source of truth** — update the spec before changing code,
never the other way around.

- **One roadmap step = one OpenSpec change.** Don't bundle steps.
- Start each step with `/opsx:propose "<step description>"`, then move through
  the artifacts in order: proposal → design → specs → tasks → implement.
- The proposal defines *why/what*, not *how* — don't jump to code until the
  proposal and specs are agreed. Honor the artifact locks (tasks stay blocked
  until design + specs exist).
- When a step is implemented and verified (it must actually run), archive the
  change and update the **Status** + roadmap checkboxes in this file so context
  stays current.
- Keep changes observable: every governance feature (budget, honeypot block,
  HITL decision) should log/print what it did — demonstrating control is the goal.

Example for the next step:
`/opsx:propose "Step 2: accumulate per-node token usage and EUR cost into AgentState, print spend per node"`