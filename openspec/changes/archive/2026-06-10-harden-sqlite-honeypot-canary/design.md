## Context

Step 4 added a graph-level approval gate before `ToolNode` execution. SQLite tools are still statically classified as safe, so a model-requested SQLite call can execute without a second look at the actual arguments. That is fine for normal business queries, but it leaves no explicit control surface for prompt injection or model confusion that targets sensitive-looking database objects.

The project goal is not only to reject unsafe SQL. It is to make the rejection visible in graph state, logs, CLI, and Chainlit so the system can explain what happened. The honeypot guard therefore belongs in the LangGraph governance path, not only inside `query_database`.

## Goals / Non-Goals

**Goals:**

- Plant a fake sensitive SQLite canary table named `api_keys_backup`.
- Keep normal SQLite discovery focused on legitimate business tables.
- Detect canary references in pending SQLite tool calls before tool execution.
- Block honeypot calls without asking for human approval.
- Record honeypot blocks in `AgentState` as auditable events.
- Return rejection `ToolMessage` entries so the model can recover and explain that access was blocked.
- Preserve existing budget and HITL behavior.

**Non-Goals:**

- Do not implement a full SQL firewall or permission engine.
- Do not add a SQL parser dependency unless a later change needs one.
- Do not move the business database to a different storage engine.
- Do not implement alert delivery to external systems; logging and state/UI visibility are enough for Step 5.
- Do not make GA4 tools part of honeypot detection.

## Decisions

### D1: Add a dedicated graph-level honeypot guard before HITL approval

Add a pre-tool guard after `budget_check` and before the existing human approval path. The guard inspects the latest AI message tool calls and dynamically classifies specific calls as `honeypot` when their arguments reference protected SQLite objects.

Rationale: honeypot blocking is a hard deny, not a human approval workflow. Keeping it before HITL avoids asking a human to approve a call that must never execute.

Alternative considered: add all logic inside `query_database` and `describe_table`. This is still useful as a defensive fallback, but by itself it would not demonstrate graph-level governance or record rich state before `ToolNode`.

### D2: Hide canary objects from `list_tables`

`list_tables` should return only user-facing business tables and should exclude `api_keys_backup`.

Rationale: the normal schema-discovery workflow should remain clean and deterministic. The honeypot is meant to catch explicit misuse, prompt injection, or suspicious direct references, not create accidental temptation during ordinary discovery.

Alternative considered: expose the canary table from `list_tables` to test whether the model avoids it. That is a sharper adversarial demo, but it makes ordinary "what tables exist?" output look intentionally dangerous and can distract from the governed-agent story.

### D3: Use a small identifier detector instead of a SQL parser

Detection should cover direct canary references in `describe_table(table_name=...)` and SQL text passed to `query_database`, including common SQLite quoting forms such as `api_keys_backup`, `"api_keys_backup"`, `[api_keys_backup]`, and `` `api_keys_backup` ``.

Rationale: Step 5 needs predictable canary detection, not full SQL semantics. A conservative identifier/token scan is sufficient for a named canary object and avoids adding dependency and parser behavior questions.

Alternative considered: add `sqlparse` or `sqlglot`. That could help later if the project grows into a broader SQL policy engine, but it is unnecessary for this reference implementation.

### D4: Record honeypot events with an additive state reducer

Add `honeypot_events: Annotated[list[dict[str, Any]], operator.add]` to `AgentState`. Each event should include the tool call ID, tool name, classification, source, matched object, original args, reason, timestamp, and action.

Rationale: prior governance fields already use state as the audit surface. An additive reducer preserves all events across turns and checkpoints.

Alternative considered: use only logs. Logs are helpful, but they are not visible in Chainlit state inspection and are not naturally persisted with the graph checkpoint.

### D5: Continue the graph after a block by appending `ToolMessage` rejections

When a honeypot call is blocked, the guard should append matching `ToolMessage` entries and route back to `call_model`. If a model message contains both blocked and allowed tool calls, Step 5 should conservatively block the whole batch and return rejection messages for the pending calls.

Rationale: `ToolNode` executes tool calls from the latest AI message as a batch. Partial execution would require carefully rewriting the AI message and preserving tool-call ordering. A whole-batch deny is simpler, safer, and clearer for a first governance implementation.

Alternative considered: execute non-honeypot calls while rejecting only the honeypot call. This can be revisited once the guard has stronger batch rewriting tests.

## Risks / Trade-offs

- [False positives from simple text detection] -> Keep the protected object list small and exact; test quoted and unquoted forms.
- [Existing seeded databases may not get the canary table] -> Make `seed_database()` ensure the canary exists even when business tables already exist.
- [Canary table appears in normal discovery] -> Filter `list_tables` and avoid broad `sqlite_master` output in normal tools.
- [Bypass through direct tool invocation outside the graph] -> Add defensive checks in SQLite tools in addition to graph-level blocking.
- [State inspector becomes noisy] -> Show only counts and the most recent few honeypot events, matching the HITL decision summary pattern.
