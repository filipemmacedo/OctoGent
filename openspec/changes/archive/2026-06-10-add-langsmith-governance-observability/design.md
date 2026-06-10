## Context

The project already emits automatic LangGraph/LangChain traces when LangSmith environment variables are configured. Today those traces show graph nodes such as `honeypot_guard`, but a node appearing in the trace does not mean a governance incident occurred. The durable source of governance truth remains `AgentState`: token/cost fields, halt fields, HITL decisions, and `honeypot_events`.

Step 6 adds a thin observability layer that mirrors governance events into LangSmith so runs can be filtered and investigated centrally. This should improve auditability without making LangSmith part of the policy decision path.

## Goals / Non-Goals

**Goals:**

- Make real governance events searchable in LangSmith by tags and metadata.
- Distinguish guard execution from actual incidents such as `honeypot_blocked`.
- Attach stable run-level metadata to Chainlit and CLI invocations.
- Emit explicit event spans for honeypot blocks, HITL decisions, and budget halts.
- Keep all observability optional and safe when LangSmith is not configured.
- Keep `AgentState` as the authoritative audit ledger.

**Non-Goals:**

- Do not replace Chainlit state inspection, CLI debug output, or checkpoint state.
- Do not add Slack/email/SIEM alert delivery in this change.
- Do not introduce Langfuse in parallel; this step standardizes on LangSmith first.
- Do not move checkpointer persistence from SQLite to Postgres.
- Do not send secrets, OAuth tokens, raw credentials, or full sensitive data payloads to LangSmith.

## Decisions

### D1: Use LangSmith as the first observability backend

Use the existing LangSmith/LangChain integration rather than adding a second observability vendor.

Rationale: the app already uses LangGraph and LangChain, `langsmith` is already listed in `requirements.txt`, and automatic traces are already visible. LangSmith also supports runtime tags and metadata through LangChain config, which keeps integration small.

Alternative considered: add Langfuse. Langfuse is a good open-source observability option, but adding it now would create a second tracing vocabulary and increase implementation surface before the reference implementation has one complete observability path.

### D2: Keep observability out of governance decisions

Governance decisions remain in graph state and routing logic. Observability helpers only receive already-created events and emit trace records.

Rationale: audit tooling should not become a policy dependency. A LangSmith outage or missing API key must not affect budget halts, honeypot blocks, HITL interrupts, or tool execution.

Alternative considered: make LangSmith callbacks part of each control node's decision logic. This would tightly couple policy to tracing and make failure modes harder to reason about.

### D3: Emit event-level spans for actual events, not guard node execution

Add helpers such as `emit_honeypot_blocked(event)`, `emit_hitl_decision(event)`, and `emit_budget_halt(event)` that create explicit traceable spans only when something happened.

Rationale: LangSmith already shows graph nodes. The missing signal is whether the node observed an incident. Separate spans make filters like `tag:honeypot` or `metadata.governance_event=honeypot_blocked` meaningful.

Alternative considered: rename graph nodes or rely on stdout. Node names alone create false positives, and stdout is not searchable across sessions in LangSmith.

### D4: Pass run-level metadata from invocation config

Extend `build_graph_config()` or add an adjacent helper so Chainlit and CLI invocations include tags and metadata such as app name, interface, thread ID, recursion limit, and governance version. Per-run dynamic counts may be added after execution where appropriate.

Rationale: LangSmith metadata and tags are inherited by child runs, making traces easier to group by interface and session.

Alternative considered: attach metadata only to custom event spans. That would make incidents searchable but leave normal runs harder to correlate with Chainlit sessions and CLI sessions.

### D5: Redact event payloads before tracing

Create a small sanitizer that preserves policy fields but avoids sending raw secrets. For honeypot events, include tool name, action, classification, source, matched object, reason, timestamp, and safe argument summaries. Do not send actual canary row values or credentials.

Rationale: observability systems are useful because they centralize data. That also means they should receive the minimum data needed for investigation.

Alternative considered: send full event dictionaries unchanged. That is convenient but weakens the project's security story.

## Risks / Trade-offs

- [Duplicate trace noise] -> Use clear names and tags so event spans are easy to distinguish from ordinary graph node spans.
- [LangSmith not configured] -> Observability helpers must no-op or rely on existing tracing behavior without raising errors.
- [Sensitive metadata leakage] -> Sanitize event payloads and document that raw secrets must never be emitted.
- [Async/sync mismatch] -> Keep event emitters lightweight and synchronous unless implementation proves async is necessary.
- [Over-coupling to one backend] -> Keep helpers behind a local module so a future Langfuse/SIEM backend can reuse sanitized event dictionaries.

## Migration Plan

1. Add LangSmith env vars to `.env.example` without requiring them.
2. Add observability helpers and wire them into governance nodes.
3. Add run config metadata/tags for Chainlit and CLI.
4. Verify with LangSmith enabled and disabled.
5. Document LangSmith filters for governance investigation.

Rollback is straightforward: disable `LANGSMITH_TRACING` or remove calls to the local observability helpers. Core governance behavior remains in `AgentState`.

## Open Questions

- Should Step 6 include LangSmith automation rules/webhook alerts, or should alert delivery be a later Step 7?
- What exact project name should be recommended in `.env.example`: `langgraph-governed-agent` or a user-specific value?
