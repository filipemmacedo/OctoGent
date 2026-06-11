# Reading Orchestration Metrics in LangSmith

This guide explains where each orchestration metric lives in LangSmith and how
to read it. All metrics are observability-only: `AgentState` remains the
source of truth for governance, and nothing here is required for the agent to
run (no LangSmith, no behavior change).

Prerequisites: LangSmith tracing enabled via `.env`
(`LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`,
optionally `LANGSMITH_ENDPOINT` / `LANGSMITH_WORKSPACE_ID`). The tracing
project referenced below is the one named in `LANGSMITH_PROJECT`
(default `langgraph-governed-agent`).

## Quick reference

| Metric | Where it lives | Key to look for |
|---|---|---|
| 1. Context window utilization | metadata + feedback on `call_model` runs | `context_window_pct` |
| 2. Cumulative EUR cost | metadata + feedback on `call_model` runs | `cumulative_cost_eur` |
| 3. Error rate by node | automatic LangGraph node runs | run name + error status |
| 4. End-to-end latency & tokens/cost | root runs (automatic) | latency, token counts, cost |
| 5. Context groundedness (LLM judge) | feedback on sampled runs | `context_groundedness` |
| 6. Data retrieval hit rate | feedback on `tools` runs | `data_hit` |

**Why metadata *and* feedback:** LangSmith dashboards can filter and group by
metadata but cannot put a metadata value on a chart's Y-axis — only feedback
scores and built-in metrics are chartable. So every metric is attached as run
metadata (full payload, for trace inspection and filtering), and the three
chartable keys — `context_window_pct`, `cumulative_cost_eur`,
`step_input_tokens` — are additionally mirrored as feedback scores by
`attach_model_step_metrics` (`src/observability.py`). Two consequences:

- The **Feedback** tab on `call_model` runs mixes system-emitted metric
  scores (those three keys) with LLM-judge quality scores
  (`context_groundedness`). Same namespace, different meaning — the key name
  tells you which is which.
- Each mirrored key is a synchronous feedback POST per model step (~3 small
  HTTP calls), a deliberate latency trade-off for chartability. Failures are
  swallowed with a printed warning and never affect the agent.

---

## 1. Context window utilization

**Origin:** computed in `call_model` (`src/graph.py`) from this call's input
tokens divided by `AGENT_MODEL_CONTEXT_WINDOW` (`src/config.py`, default
128000), attached by `attach_model_step_metrics` (`src/observability.py`).

**Where to read it:**
1. Open the tracing project, open any trace, select a `call_model` run.
2. In the run's **Metadata** section, read:
   - `step_input_tokens` — tokens in this call's prompt (after trimming)
   - `model_context_window` — configured window size
   - `context_window_pct` — utilization percentage (0–100, 2 decimals)

**Filter:** in the Runs view, filter `Name` = `call_model`, then add a
metadata filter such as `metadata.context_window_pct > 50`.

**Chart:** Dashboards → New chart → data source: your project, filter
`name = call_model`, metric: **feedback score** `context_window_pct`
(average, or p95), grouped over time. The metadata copy of the value is for
filtering only — metadata cannot be charted.

**Interpretation:** the prompt is trimmed to the current turn before
invocation, so this measures *what the model actually saw*, not the
cumulative session. Sustained values above ~85% mean the trimming strategy
is too loose or turns are too large; values that never leave single digits
mean there is headroom. If you change `OPENAI_MODEL`, update
`AGENT_MODEL_CONTEXT_WINDOW` or the percentage will be wrong (harmless, but
misleading).

## 2. Cumulative EUR cost

**Origin:** the token ledger in `AgentState` (`tokens_in`, `tokens_out`,
`cost_eur`), computed in `call_model` with the EUR pricing constants in
`src/graph.py`, attached as run metadata.

**Where to read it:** on any `call_model` run's **Metadata**:
- `cumulative_cost_eur` — session EUR spend up to and including this step
- `cumulative_tokens_in` / `cumulative_tokens_out` — ledger totals
- `step_input_tokens` / `step_output_tokens` — this call's delta

The latest `call_model` run in a trace carries the session's current total.

**Chart:** Dashboards → New chart → filter `name = call_model`, metric:
**feedback score** `cumulative_cost_eur` (max), grouped by
`metadata.thread_id` (thread id is set on every run by `build_graph_config`
in `src/config.py`).

**Interpretation — which cost number is authoritative:** LangSmith also
computes its own cost estimate (in **USD**) from its model pricing table.
The two will not match: the ledger applies a EUR conversion
(`EUR_USD_RATE` in `src/graph.py`) and is the number the budget circuit
breaker (`AGENT_MAX_COST_EUR`) enforces. **The `AgentState` EUR ledger is
authoritative for governance; LangSmith's USD figure is a cross-check.**
If they diverge wildly, the pricing constants in `src/graph.py` are stale.

## 3. Error rate by node

**Origin:** automatic. LangGraph traces every node — `call_model`,
`budget_check`, `honeypot_guard`, `approval_gate`, `approval_interrupt`,
`tools` — as a child run with name, status, and latency. No custom emission
code exists or is needed.

**Where to read it:**
1. Runs view → filter `Is Root` = false, `Name` = the node of interest.
2. Add filter `Status` = `error` to see only failures; the run's error field
   has the exception.

**Chart:** Dashboards → New chart → filter `name = <node>`, metric: error
rate (errored runs / total runs), one chart per node or grouped by run name.
Latency per node: same filter, metric p50/p99 latency.

**Interpretation — node errors vs governance events:** a `honeypot_guard` or
`budget_check` run appearing in a trace only means the guard *executed* —
that is normal on every loop iteration. A real incident is signaled by the
explicit governance events (`honeypot_blocked`, `budget_halt`,
`hitl_decision` runs and their `governance_event` metadata/tags, see Step 6).
Conversely, an *errored* node run is an implementation failure (exception),
not a governance action: a honeypot block produces a successful guard run
plus a `honeypot_blocked` event, not an error. The `tools` node is the one
to watch for flaky external calls (GA4 MCP).

## 4. End-to-end latency and token/cost totals

**Origin:** automatic root-run tracing.

**Where to read it:**
1. Runs view → filter `Is Root` = true. Each row is one graph invocation
   (one user turn) with total latency, total tokens, and LangSmith's USD
   cost estimate.
2. Per-thread: filter `metadata.thread_id = <id>` to see all turns of a
   session.

**Chart:** the project's built-in **Monitor** tab already charts trace
count, latency percentiles, token usage, error rate, and cost over time with
no setup. For custom views: Dashboards → chart on root runs, metrics p50/p99
latency and total tokens.

**Interpretation:** creeping root-run latency with rising
`step_input_tokens` (metric 1) means context growth; rising latency with
flat tokens points at tool calls (check the `tools` node, metric 3). For
EUR cost the ledger rule from metric 2 applies — use
`cumulative_cost_eur`, not the USD estimate, when reasoning about the
budget breaker.

## 5. Context groundedness (online LLM-as-judge)

**Origin:** a LangSmith **online evaluator** (workspace configuration, not
repo code) that runs an LLM judge over a sample of production `call_model`
runs and writes a feedback score. The judge checks whether the response used
only information actually present in the trimmed prompt the model was given
— the honest analogue of an "offload hit rate" for this project's
trim-to-current-turn context strategy.

**Where to read it:**
1. Runs view → filter `Name` = `call_model`, add filter
   `Feedback` → `context_groundedness`.
2. On a run, the **Feedback** tab shows the 0–1 score and the judge's
   comment naming any ungrounded claims.

**Chart:** Dashboards → New chart → metric: average feedback
`context_groundedness` over time. A downward trend after a prompt or
trimming change is the signal this metric exists to catch.

**Interpretation:** score 1.0 = fully grounded; below ~0.5 = the response
asserted facts not present in its prompt (fabrication, or context lost to
trimming). Because the judge sees the run's recorded input — which *is* the
trimmed prompt — a low score on a correct-sounding answer usually means the
agent "remembered" something trimming had removed: it got lucky, and that is
still a governance smell. Scores arrive minutes after the trace, only on
sampled runs.

**Cost note:** the judge is LLM spend billed on the LangSmith side. It is
**outside** the agent's EUR budget breaker — `AGENT_MAX_COST_EUR` does not
see or limit it. The sampling rate (below) is the only cost lever.

## 6. Data retrieval hit rate

**Origin:** the `tools` node in `src/graph.py` wraps `ToolNode`; after each
execution, `log_tool_data_hits` (`src/observability.py`) scores every tool
result 1.0 (returned usable data) or 0.0 (miss or error) and logs it as
feedback `data_hit` on the `tools` run, with the tool name in the comment.
The classifier (`classify_tool_result_hit`) matches the known no-data output
formats: `No results found.`, `Table '...' does not exist.`, `No tables
found.`, `Error: ...` / `Query error: ...`, empty content, and empty GA4
report rows (`"rows": []`). Update `DATA_MISS_MARKERS` if tool output
formats change.

**What this is — and is not:** this is the honest analogue of an "offload
hit rate" for this architecture. The agent does **not** offload context to a
memory store — dropped messages are not retrievable — so a literal offload
hit rate has nothing to measure. `data_hit` measures retrieval quality
against the agent's *data stores* (SQLite, GA4): when the agent reached for
data, did it get any? The other half of the offload concern — the agent
needing conversation context that trimming removed — is what
`context_groundedness` (metric 5) detects. If a real context-offload layer
is added later (e.g. a recall tool over summarized dropped turns), its
results flow through the same `tools` node and `data_hit` starts measuring
true offload hit rate with no new instrumentation.

**Where to read it:**
1. Runs view → filter `Name` = `tools` → a run's **Feedback** tab shows one
   `data_hit` score per tool call, with `tool: <name>` as the comment.
2. Honeypot-blocked calls never reach the `tools` node, so they are
   correctly excluded from the hit rate.

**Chart:** Dashboards → New chart → filter `name = tools`, metric:
**feedback score** `data_hit`, aggregation **Average** — that average *is*
the hit rate (1.0 = every retrieval found data). `latency_to_retrieve` is
the built-in latency metric on the same `tools` runs; add it as a second
chart with p50/p95.

**Interpretation:** a sustained hit rate below ~0.8 means the agent is
guessing at table names, columns, or GA4 dimensions instead of following
discovery-before-query — check the miss comments for which tool. Note the
score is a heuristic over output text, not a semantic judgment: a query that
returns the *wrong* rows still counts as a hit; that failure mode belongs to
`context_groundedness`.

### Online evaluator setup (reproducible walkthrough)

Workspace configuration cannot be checked into git; these are the exact
values to use.

1. In LangSmith, open the tracing project (`LANGSMITH_PROJECT` value) →
   **Rules** (Automations) → **Add rule**.
2. Configure:
   - **Rule name:** `context-groundedness-judge`
   - **Filter:** `name is call_model` and `status is success` (judge the
     model steps against their own trimmed inputs; skip errored runs)
   - **Sampling rate:** `0.10` (10%). Start low: every sampled run is one
     judge LLM call. Raise toward 0.25 only if score volume is too thin to
     chart; lower it if judge spend matters more than coverage.
   - **Action:** Evaluator (LLM-as-judge), using the prompt below.
   - **Feedback key:** `context_groundedness`, continuous score 0–1, with
     comment.
3. Save. Scores appear on newly sampled runs within minutes; backfill is not
   applied to past runs.

### Judge prompt (versioned here; paste into the evaluator)

```text
You are auditing an AI data assistant for context groundedness.

You are given the exact INPUT the assistant received (a system prompt plus
the trimmed recent messages — this is ALL the context it had) and the OUTPUT
it produced.

Score how grounded the OUTPUT is in the INPUT:
- 1.0: every factual claim, number, table/field name, and reference in the
  OUTPUT is supported by the INPUT (including tool results present in it),
  or the OUTPUT explicitly asks for / declines due to missing information.
- 0.5: mostly grounded, but at least one specific detail (a value, name,
  date, or attribution) does not appear in the INPUT.
- 0.0: the OUTPUT asserts material facts absent from the INPUT — fabricated
  data, invented schema, or confident references to earlier conversation
  content that is not present in the INPUT.

Rules:
- Judge ONLY against the INPUT text. Do not use outside knowledge to decide
  whether a claim is true; a true-but-unsupported claim is still ungrounded.
- Tool CALLS (requests to fetch data) are not claims; do not penalize them.
- General language ability and formatting are not claims.

Respond with the score and a one-to-three sentence comment naming the
specific ungrounded claims, or stating that all claims are grounded.

INPUT:
{inputs}

OUTPUT:
{outputs}
```

If the evaluator editor uses different placeholders than `{inputs}` /
`{outputs}`, map them to the run's input messages and output message; keep
the rest of the prompt verbatim so repo and workspace stay in sync. If the
UI steps above drift from the current LangSmith interface, update this file
in the same change that re-verifies the setup.
