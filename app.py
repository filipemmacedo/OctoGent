import logging
import json
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import ThreadDict
from dotenv import load_dotenv
from langgraph.errors import GraphRecursionError
from langgraph.types import Command
from starlette.datastructures import Headers

load_dotenv()
logging.basicConfig(level=logging.INFO)

from src.config import build_graph_config
from src.mcp_tools import build_mcp_config, describe_mcp_config, load_ga_tools
from src.observability import (
    create_answer_example,
    delete_user_feedback,
    log_user_feedback,
    safe_text,
)
from src.tools import list_tables, describe_table, query_database
from src.graph import build_graph, create_checkpointer
from src.tool_policy import build_tool_policies

SQLITE_TOOLS = [list_tables, describe_table, query_database]
GA_TOOLS_CACHE: list[Any] = []
MCP_STATUS_CACHE: dict[str, Any] | None = None

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


_DB_URI = f"sqlite+aiosqlite:///{DATA_DIR}/chainlit.db"

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    "id" TEXT PRIMARY KEY,
    "identifier" TEXT NOT NULL UNIQUE,
    "createdAt" TEXT,
    "metadata" TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS threads (
    "id" TEXT PRIMARY KEY,
    "createdAt" TEXT,
    "name" TEXT,
    "userId" TEXT,
    "userIdentifier" TEXT,
    "tags" TEXT,
    "metadata" TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS steps (
    "id" TEXT PRIMARY KEY,
    "name" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "threadId" TEXT NOT NULL,
    "parentId" TEXT,
    "streaming" INTEGER,
    "waitForAnswer" INTEGER,
    "isError" INTEGER,
    "metadata" TEXT,
    "tags" TEXT,
    "input" TEXT,
    "output" TEXT,
    "createdAt" TEXT,
    "start" TEXT,
    "end" TEXT,
    "generation" TEXT,
    "showInput" TEXT,
    "language" TEXT,
    "indent" INTEGER
);

CREATE TABLE IF NOT EXISTS feedbacks (
    "id" TEXT PRIMARY KEY,
    "forId" TEXT NOT NULL,
    "threadId" TEXT,
    "value" INTEGER NOT NULL,
    "comment" TEXT
);

CREATE TABLE IF NOT EXISTS elements (
    "id" TEXT PRIMARY KEY,
    "threadId" TEXT,
    "type" TEXT,
    "chainlitKey" TEXT,
    "url" TEXT,
    "objectKey" TEXT,
    "name" TEXT NOT NULL,
    "props" TEXT,
    "display" TEXT,
    "size" TEXT,
    "language" TEXT,
    "page" INTEGER,
    "autoPlay" INTEGER,
    "playerConfig" TEXT,
    "forId" TEXT,
    "mime" TEXT
);
"""


def _is_hitl_status_output(output: Any) -> bool:
    return str(output or "").startswith("**Selected:**")


def _exception_tree_lines(exc: BaseException, indent: int = 0) -> list[str]:
    prefix = "  " * indent
    lines = [f"{prefix}{type(exc).__name__}: {exc}"]
    if isinstance(exc, BaseExceptionGroup):
        for index, sub_exc in enumerate(exc.exceptions, start=1):
            lines.append(f"{prefix}sub-exception {index}:")
            lines.extend(_exception_tree_lines(sub_exc, indent + 1))
    cause = getattr(exc, "__cause__", None)
    if cause:
        lines.append(f"{prefix}caused by:")
        lines.extend(_exception_tree_lines(cause, indent + 1))
    context = getattr(exc, "__context__", None)
    if context and context is not cause:
        lines.append(f"{prefix}context:")
        lines.extend(_exception_tree_lines(context, indent + 1))
    return lines


# Fast-path map from answer message id to the LangSmith root run that produced
# it; the durable copy lives in the message's steps-table metadata.
ANSWER_RUN_IDS: dict[str, str] = {}
ANSWER_EXAMPLE_IDS: dict[str, str] = {}


class LangSmithFeedbackDataLayer(SQLAlchemyDataLayer):
    """Data layer that mirrors human 👍/👎 ratings to LangSmith as user_score.

    Local persistence always runs first and never depends on LangSmith;
    forwarding failures are printed and swallowed.
    """

    async def _resolve_run_id(self, message_id: str) -> Optional[str]:
        run_id = ANSWER_RUN_IDS.get(message_id)
        if run_id:
            return run_id

        try:
            rows = await self.execute_sql(
                query=(
                    'SELECT "metadata", "output", "threadId", "createdAt" '
                    'FROM steps WHERE "id" = :id'
                ),
                parameters={"id": message_id},
            )
        except Exception as exc:
            print(f"[feedback] failed to read step metadata: {exc}")
            return None

        if not isinstance(rows, list) or not rows:
            # Chainlit wraps every on_message call in an auto-created
            # Step(name="on_message", type="run", parent_id=<user message>),
            # which is never persisted to `steps`. The feedback UI attaches
            # to that run step, so `forId` is its id - the *parent* of our
            # persisted answer message - rather than the answer's own id.
            return await self._resolve_run_id_from_child_answer(message_id)

        raw = rows[0].get("metadata")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                return None
        if not isinstance(raw, dict):
            return None
        run_id = raw.get("langsmith_run_id")
        if run_id:
            return str(run_id)

        return await self._resolve_run_id_from_related_answer(message_id, rows[0])

    async def _resolve_run_id_from_child_answer(self, parent_id: str) -> Optional[str]:
        """Resolve feedback on Chainlit's auto on_message run step.

        That step id (the rated bubble's `forId`) is the parent of the final
        answer message, which carries the `langsmith_run_id` metadata.
        """
        try:
            rows = await self.execute_sql(
                query="""
                    SELECT "metadata"
                    FROM steps
                    WHERE "parentId" = :parent_id
                      AND "type" = 'assistant_message'
                    ORDER BY "createdAt" DESC
                    LIMIT 1
                """,
                parameters={"parent_id": parent_id},
            )
        except Exception as exc:
            print(f"[feedback] failed to resolve child answer metadata: {exc}")
            return None

        if not isinstance(rows, list) or not rows:
            return None

        raw = rows[0].get("metadata")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                return None
        if not isinstance(raw, dict):
            return None

        run_id = raw.get("langsmith_run_id")
        return str(run_id) if run_id else None

    async def _resolve_run_id_from_related_answer(
        self,
        message_id: str,
        rated_step: dict,
    ) -> Optional[str]:
        """Resolve feedback on Chainlit approval/status messages to the answer.

        Chainlit renders feedback controls on assistant/status messages too.
        The HITL action message is persisted as ``**Selected:** Approve`` and
        has no LangSmith run metadata of its own, so map it to the next final
        answer in the same thread when possible.
        """
        if not _is_hitl_status_output(rated_step.get("output")):
            return None

        thread_id = rated_step.get("threadId")
        created_at = rated_step.get("createdAt")
        if not thread_id or not created_at:
            return None

        try:
            rows = await self.execute_sql(
                query="""
                    SELECT "id", "metadata"
                    FROM steps
                    WHERE "threadId" = :thread_id
                      AND "id" != :id
                      AND "type" = 'assistant_message'
                      AND "createdAt" >= :created_at
                    ORDER BY "createdAt" ASC
                    LIMIT 20
                """,
                parameters={
                    "thread_id": thread_id,
                    "id": message_id,
                    "created_at": created_at,
                },
            )
        except Exception as exc:
            print(f"[feedback] failed to resolve related answer metadata: {exc}")
            return None

        if not isinstance(rows, list):
            return None

        for row in rows:
            raw = row.get("metadata")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except ValueError:
                    continue
            if not isinstance(raw, dict):
                continue
            run_id = raw.get("langsmith_run_id")
            if run_id:
                print(
                    f"[feedback] mapped status message {message_id} "
                    f"to answer {row.get('id')}"
                )
                return str(run_id)

        return None

    async def upsert_feedback(self, feedback) -> str:
        feedback_id = await super().upsert_feedback(feedback)

        run_id = await self._resolve_run_id(feedback.forId)
        if run_id is None:
            print(
                f"[feedback] no langsmith_run_id for message {feedback.forId}; "
                "rating kept local-only"
            )
            return feedback_id

        example_id = ANSWER_EXAMPLE_IDS.get(feedback.forId)
        score = 1.0 if feedback.value else 0.0
        if log_user_feedback(
            run_id=run_id,
            score=score,
            comment=feedback.comment,
            message_id=feedback.forId,
            example_id=example_id,
        ):
            print(f"[feedback] user_score={score} recorded on run {run_id}")
        return feedback_id

    async def delete_feedback(self, feedback_id: str) -> bool:
        for_id: Optional[str] = None
        try:
            rows = await self.execute_sql(
                query='SELECT "forId" FROM feedbacks WHERE "id" = :id',
                parameters={"id": feedback_id},
            )
            if isinstance(rows, list) and rows:
                for_id = rows[0].get("forId")
        except Exception as exc:
            print(f"[feedback] failed to read feedback row: {exc}")

        deleted = await super().delete_feedback(feedback_id)
        if for_id and delete_user_feedback(for_id):
            print(f"[feedback] user_score removed for message {for_id}")
        return deleted


@cl.data_layer
def get_data_layer():
    return LangSmithFeedbackDataLayer(conninfo=_DB_URI)


@cl.on_app_startup
async def on_app_startup():
    """Create Chainlit data layer tables if they don't exist yet."""
    global GA_TOOLS_CACHE, MCP_STATUS_CACHE

    import aiosqlite
    db_path = str(DATA_DIR / "chainlit.db")
    repaired = 0
    async with aiosqlite.connect(db_path) as conn:
        for statement in _CREATE_TABLES_SQL.strip().split(";\n\n"):
            stmt = statement.strip()
            if stmt:
                await conn.execute(stmt)
        feedback_columns = await conn.execute('PRAGMA table_info("feedbacks")')
        added_thread_id_column = False
        if "threadId" not in {row[1] for row in await feedback_columns.fetchall()}:
            await conn.execute('ALTER TABLE feedbacks ADD COLUMN "threadId" TEXT')
            added_thread_id_column = True
        cursor = await conn.execute(
            """
            UPDATE steps
            SET "parentId" = NULL
            WHERE "parentId" IS NOT NULL
              AND "parentId" NOT IN (SELECT "id" FROM steps)
            """
        )
        repaired = max(cursor.rowcount, 0)
        cursor = await conn.execute(
            """
            DELETE FROM steps
            WHERE "output" LIKE '**Selected:%'
            """
        )
        removed_hitl_status = max(cursor.rowcount, 0)
        cursor = await conn.execute(
            """
            DELETE FROM steps
            WHERE "type" = 'tool'
            """
        )
        removed_tool_steps = max(cursor.rowcount, 0)
        cursor = await conn.execute(
            """
            UPDATE steps
            SET "type" = 'system_message'
            WHERE "type" = 'assistant_message'
              AND (
                "name" = 'system'
                OR "output" LIKE '**State Inspector**%'
                OR "output" LIKE '**MCP Status**%'
                OR "output" LIKE '💰%'
                OR "output" LIKE 'Execution stopped:%'
              )
            """
        )
        reclassified_system_messages = max(cursor.rowcount, 0)
        await conn.commit()
    if added_thread_id_column:
        print('[startup] Added missing "threadId" column to feedbacks table')
    if repaired:
        print(f"[startup] Repaired {repaired} orphan Chainlit step parent(s)")
    if removed_hitl_status:
        print(
            "[startup] Removed "
            f"{removed_hitl_status} persisted HITL status message(s)"
        )
    if removed_tool_steps:
        print(f"[startup] Removed {removed_tool_steps} persisted tool step(s)")
    if reclassified_system_messages:
        print(
            "[startup] Reclassified "
            f"{reclassified_system_messages} non-answer message(s) as system messages"
        )
    print("[startup] Chainlit DB tables ready")

    MCP_STATUS_CACHE = await _load_mcp_tools_once()


async def _load_mcp_tools_once() -> dict[str, Any]:
    """Load GA MCP tools once per Chainlit process and cache the result."""
    global GA_TOOLS_CACHE

    mcp_config = build_mcp_config()
    mcp_summary = describe_mcp_config(mcp_config)
    status: dict[str, Any] = {
        "summary": mcp_summary,
        "tool_names": [],
        "error": None,
        "error_lines": [],
    }
    print("[mcp] config:")
    print(json.dumps(mcp_summary, indent=2))

    if not mcp_config:
        GA_TOOLS_CACHE = []
        print("[mcp] GA MCP not configured; using SQLite-only tools")
        return status

    from langchain_mcp_adapters.client import MultiServerMCPClient

    try:
        mcp_client = MultiServerMCPClient({"ga4": mcp_config})
        GA_TOOLS_CACHE = await load_ga_tools(mcp_client)
        tool_names = [tool.name for tool in GA_TOOLS_CACHE]
        status["tool_names"] = tool_names
        print(f"[mcp] loaded GA tools: {tool_names}")
    except Exception as exc:
        import traceback

        GA_TOOLS_CACHE = []
        status["error"] = f"{type(exc).__name__}: {exc}"
        status["error_lines"] = _exception_tree_lines(exc)
        print(f"[mcp] failed to load GA tools: {exc!r}")
        print("[mcp] exception tree:")
        print("\n".join(status["error_lines"]))
        traceback.print_exc()
        print("[mcp] continuing with SQLite-only tools")

    return status


@cl.header_auth_callback
async def header_auth_callback(headers: Headers) -> Optional[cl.User]:
    return cl.User(identifier="local", metadata={"role": "user"})


async def _setup_session(thread_id: str) -> None:
    """Build MCP tools, checkpointer, and graph; store in user session."""
    global MCP_STATUS_CACHE

    if MCP_STATUS_CACHE is None:
        MCP_STATUS_CACHE = await _load_mcp_tools_once()

    all_tools = SQLITE_TOOLS + GA_TOOLS_CACHE
    tool_policies = build_tool_policies(SQLITE_TOOLS, GA_TOOLS_CACHE)
    checkpointer_cm = create_checkpointer()
    checkpointer = await checkpointer_cm.__aenter__()
    graph = build_graph(all_tools, checkpointer, tool_policies)
    cl.user_session.set("graph", graph)
    cl.user_session.set("checkpointer", checkpointer)
    cl.user_session.set("checkpointer_cm", checkpointer_cm)
    cl.user_session.set("thread_id", thread_id)
    cl.user_session.set("mcp_status", MCP_STATUS_CACHE)
    return MCP_STATUS_CACHE


def _format_mcp_status(status: dict) -> str:
    summary = status.get("summary", {})
    tool_names = status.get("tool_names", [])
    error = status.get("error")
    error_lines = status.get("error_lines", [])

    lines = ["**MCP Status**"]
    if not summary.get("configured"):
        lines.append("GA MCP is not configured. Running SQLite-only.")
        return "\n\n".join(lines)

    lines.append(f"Transport: `{summary.get('transport')}`")
    if summary.get("transport") == "stdio":
        lines.append(f"Command: `{summary.get('command')}`")
        lines.append(f"Args: `{' '.join(summary.get('args', []))}`")
        lines.append(
            f"OAuth client configured: `{summary.get('google_client_id_configured')}`"
        )
        lines.append(
            f"GA4 default property configured: `{summary.get('ga4_property_id_configured')}`"
        )
        lines.append(
            f"OAuth token path configured: `{summary.get('ga4_token_path_configured')}`"
        )
        credentials = summary.get("credentials", {})
        lines.append(f"Legacy ADC credential exists: `{credentials.get('exists')}`")
        lines.append(f"Legacy ADC credential type: `{credentials.get('type')}`")
        if credentials.get("client_email"):
            lines.append(f"Legacy service account: `{credentials['client_email']}`")

    if error:
        lines.append("")
        lines.append("GA MCP failed to load. The session is running SQLite-only.")
        lines.append(f"Error: `{error}`")
        if error_lines:
            lines.append("")
            lines.append("Nested error:")
            lines.append("```")
            lines.extend(error_lines[:40])
            lines.append("```")
        if "McpError: Connection closed" in "\n".join(error_lines):
            lines.append("")
            lines.append(
                "The local stdio MCP process closed before tool discovery completed. "
                "Restart Chainlit from the project root and verify the same GA4 MCP "
                "config works with `python -m src.main`."
            )
    else:
        lines.append("")
        lines.append(f"GA MCP loaded `{len(tool_names)}` tools.")
        if tool_names:
            lines.append(f"Tools: `{', '.join(tool_names)}`")

    return "\n".join(lines)


async def _send_message(
    content: str,
    parent_id: Optional[str] = None,
    **kwargs,
) -> cl.Message:
    """Send a Chainlit message with an explicit persisted parent."""
    if kwargs.get("author") == "system" and "type" not in kwargs:
        kwargs["type"] = "system_message"
    msg = cl.Message(content=content, **kwargs)
    if parent_id is not None:
        msg.parent_id = parent_id
    await msg.send()
    return msg


@cl.on_chat_start
async def on_chat_start():
    # Chainlit assigns a UUID to the session; we reuse it as the LangGraph thread_id
    # so both systems stay in sync without any extra metadata storage.
    thread_id = cl.context.session.thread_id
    status = await _setup_session(thread_id)
    await _send_message(content=_format_mcp_status(status), author="system")


@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    # thread["id"] is the Chainlit thread ID == our LangGraph thread_id.
    # Rebuilding the graph with the same checkpointer restores full agent state.
    thread_id = thread["id"]
    status = await _setup_session(thread_id)
    await _send_message(content=_format_mcp_status(status), author="system")
    # Restore token/message baseline from the last persisted state so the
    # cost badge and state inspector deltas are computed correctly.
    ckpt = cl.user_session.get("checkpointer")
    if ckpt:
        graph = cl.user_session.get("graph")
        config = build_graph_config(thread_id, interface="chainlit")
        try:
            state = await graph.aget_state(config)
            if state and state.values:
                v = state.values
                cl.user_session.set("tokens_in", v.get("tokens_in", 0))
                cl.user_session.set("tokens_out", v.get("tokens_out", 0))
                cl.user_session.set("cost_eur", v.get("cost_eur", 0.0))
                cl.user_session.set("halted", v.get("halted", False))
                cl.user_session.set("budget_exceeded", v.get("budget_exceeded", False))
                cl.user_session.set("halt_reason", v.get("halt_reason", ""))
                cl.user_session.set("pending_approval", v.get("pending_approval"))
                cl.user_session.set("hitl_decisions", v.get("hitl_decisions", []))
                cl.user_session.set("honeypot_events", v.get("honeypot_events", []))
                msgs = v.get("messages", [])
                cl.user_session.set("msg_count", len(msgs))
        except Exception:
            pass


def _format_state_inspector(
    messages: list,
    tokens_in: int,
    tokens_out: int,
    cost_eur: float,
    halted: bool,
    budget_exceeded: bool,
    halt_reason: str,
    pending_approval: Optional[dict],
    hitl_decisions: list[dict],
    honeypot_events: list[dict],
    d_in: int,
    d_out: int,
    d_cost: float,
    msgs_before: int,
) -> str:
    lines = ["```", "AgentState", "══════════════════════════════════════════"]

    n_new = len(messages) - msgs_before
    lines.append(f"\nmessages  ({len(messages)} total, +{n_new} this turn):")
    for i, msg in enumerate(messages):
        msg_type = type(msg).__name__
        content_preview = ""
        suffix = ""

        if hasattr(msg, "tool_calls") and msg.tool_calls:
            calls = [f"{tc['name']}()" for tc in msg.tool_calls]
            suffix = f"  → calls: {', '.join(calls)}"
        elif hasattr(msg, "content") and msg.content:
            preview = str(msg.content).replace("\n", " ")[:60]
            content_preview = f'  "{preview}{"…" if len(str(msg.content)) > 60 else ""}"'

        marker = "▶" if i >= msgs_before else " "
        lines.append(f"  {marker} [{i}] {msg_type:<18}{suffix}{content_preview}")

    lines.append(f"\ntokens_in:   {tokens_in:>6,}  (+{d_in} this turn)")
    lines.append(f"tokens_out:  {tokens_out:>6,}  (+{d_out} this turn)")
    lines.append(f"halted:     {halted}")
    lines.append(f"budget_exceeded: {budget_exceeded}")
    if halt_reason:
        lines.append(f"halt_reason: {halt_reason}")
    lines.append(f"pending_approval: {bool(pending_approval)}")
    lines.append(f"hitl_decisions: {len(hitl_decisions)}")
    for decision in hitl_decisions[-3:]:
        lines.append(
            "  - "
            f"{decision.get('decision')} "
            f"{decision.get('tool_name')} "
            f"({decision.get('classification')})"
        )
    lines.append(f"honeypot_events: {len(honeypot_events)}")
    for event in honeypot_events[-3:]:
        lines.append(
            "  - "
            f"{event.get('action')} "
            f"{event.get('tool_name')} "
            f"matched {event.get('matched_object')}"
        )
    lines.append(f"cost_eur:  €{cost_eur:.6f}  (+€{d_cost:.6f} this turn)")
    lines.append("```")
    return "\n".join(lines)


def _interrupt_payload_from_event(event: dict) -> Optional[dict]:
    data = event.get("data") or {}
    chunk = data.get("chunk") or {}
    interrupts = chunk.get("__interrupt__") if isinstance(chunk, dict) else None
    if not interrupts:
        return None

    interrupt_obj = interrupts[0]
    payload = getattr(interrupt_obj, "value", interrupt_obj)
    if isinstance(payload, dict) and payload.get("kind") == "tool_approval":
        return payload
    return None


def _format_tool_approval_request(payload: dict) -> str:
    lines = ["Human approval required before sensitive tool execution.", ""]
    for index, tool_call in enumerate(payload.get("tool_calls", []), start=1):
        lines.append(
            f"{index}. `{tool_call.get('name')}` "
            f"({tool_call.get('classification')})"
        )
        lines.append(f"Reason: {tool_call.get('reason')}")
        lines.append("Args:")
        lines.append("```json")
        lines.append(json.dumps(tool_call.get("args", {}), indent=2))
        lines.append("```")
    return "\n".join(lines)


def _action_name(response: Any) -> str:
    if isinstance(response, dict):
        return str(response.get("name") or "")
    return str(getattr(response, "name", "") or "")


def _message_content(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, dict):
        return str(
            response.get("output")
            or response.get("content")
            or response.get("message")
            or ""
        )
    return str(getattr(response, "content", "") or "")


async def _ask_for_json_args(payload: dict) -> Optional[dict]:
    tool_calls = payload.get("tool_calls", [])
    if len(tool_calls) == 1:
        current = tool_calls[0].get("args", {})
        prompt = (
            "Edit the tool arguments as JSON. Submit a single JSON object.\n\n"
            "Current arguments:\n"
            "```json\n"
            f"{json.dumps(current, indent=2)}\n"
            "```"
        )
    else:
        current = {
            tool_call.get("id"): tool_call.get("args", {})
            for tool_call in tool_calls
        }
        prompt = (
            "Edit tool arguments as JSON keyed by tool call ID.\n\n"
            "Current arguments:\n"
            "```json\n"
            f"{json.dumps(current, indent=2)}\n"
            "```"
        )

    for _ in range(3):
        response = await cl.AskUserMessage(
            content=prompt,
            timeout=300,
            raise_on_timeout=False,
        ).send()
        raw = _message_content(response).strip()
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            await _send_message(
                content=f"Invalid JSON: {exc}. Please try again.",
                author="system",
            )
            continue
        if isinstance(value, dict):
            return value
        await _send_message(
            content="Edited arguments must be a JSON object. Please try again.",
            author="system",
        )
    return None


async def _ask_chainlit_approval(payload: dict) -> dict:
    approval_message = cl.AskActionMessage(
        content=_format_tool_approval_request(payload),
        actions=[
            cl.Action(
                name="hitl_approve",
                label="Approve",
                payload={"decision": "approve"},
            ),
            cl.Action(
                name="hitl_edit",
                label="Edit args",
                payload={"decision": "edit"},
            ),
            cl.Action(
                name="hitl_reject",
                label="Reject",
                payload={"decision": "reject"},
            ),
        ],
        timeout=300,
        raise_on_timeout=False,
    )
    # Chainlit otherwise persists the post-action ``**Selected:** ...`` row as
    # an assistant message, which makes the built-in thumbs feedback target the
    # approval status instead of the final answer.
    approval_message.type = "system_message"
    response = await approval_message.send()
    await approval_message.remove()

    action = _action_name(response)
    if action == "hitl_approve":
        return {"decision": "approve", "comment": "Approved in Chainlit"}

    if action == "hitl_edit":
        edited_args = await _ask_for_json_args(payload)
        if edited_args is None:
            return {
                "decision": "reject",
                "comment": "Edit cancelled or timed out in Chainlit",
            }
        return {
            "decision": "edit",
            "edited_args": edited_args,
            "comment": "Edited in Chainlit",
        }

    if action == "hitl_reject":
        reason = await cl.AskUserMessage(
            content=(
                "Rejection note (optional)\n\n"
                "Add a short reason to send back to the agent, for example "
                "`GA4 access not approved for this request`. Leave it blank "
                "to use the default rejection message."
            ),
            timeout=120,
            raise_on_timeout=False,
        ).send()
        comment = (
            _message_content(reason).strip()
            or "Sensitive tool call rejected by the human reviewer"
        )
        return {"decision": "reject", "comment": comment}

    return {
        "decision": "reject",
        "comment": "Approval timed out or no action was selected in Chainlit",
    }


@cl.on_message
async def on_message(message: cl.Message):
    try:
        await _handle_message(message)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        await _send_message(content=f"⚠️ Error: {exc}", parent_id=message.id)


def _new_invocation_config(thread_id: str, user_message: Optional[str] = None):
    """Return (run_id, config) for one graph invocation with a fresh root run."""
    run_id = uuid4()
    extra_metadata = None
    if user_message:
        extra_metadata = {"user_message": safe_text(user_message)}
    config = build_graph_config(
        thread_id,
        interface="chainlit",
        extra_metadata=extra_metadata,
        run_id=run_id,
    )
    return run_id, config


async def _handle_message(message: cl.Message):
    graph = cl.user_session.get("graph")
    thread_id = cl.user_session.get("thread_id")

    if graph is None:
        await _send_message(
            content="⚠️ Session not initialised — please refresh the page.",
            parent_id=message.id,
        )
        return

    tokens_in_before = cl.user_session.get("tokens_in", 0)
    tokens_out_before = cl.user_session.get("tokens_out", 0)
    cost_eur_before = cl.user_session.get("cost_eur", 0.0)
    msgs_before = cl.user_session.get("msg_count", 0)

    final_state: dict = {}
    # Each astream_events call is its own LangSmith root run, including HITL
    # resumes; the last one produced the final answer, so feedback targets it.
    last_run_id, config = _new_invocation_config(thread_id, message.content)

    try:
        graph_input: Any = {
            "messages": [{"role": "user", "content": message.content}]
        }
        while True:
            interrupt_payload: Optional[dict] = None
            async for event in graph.astream_events(
                graph_input,
                config=config,
                version="v2",
            ):
                kind = event["event"]

                if kind == "on_chain_stream":
                    interrupt_payload = (
                        _interrupt_payload_from_event(event) or interrupt_payload
                    )

                elif kind == "on_chain_end" and event.get("name") == "LangGraph":
                    final_state = event["data"].get("output", {})

            if not interrupt_payload:
                break

            decision = await _ask_chainlit_approval(interrupt_payload)
            graph_input = Command(resume=decision)
            last_run_id, config = _new_invocation_config(thread_id, message.content)
    except GraphRecursionError as exc:
        halt_reason = f"Loop limit exceeded: {exc}"
        print(f"[recursion] halted: {halt_reason}")
        try:
            state = await graph.aget_state(config)
            if state and state.values:
                final_state = state.values
        except Exception as state_exc:
            print(f"[recursion] could not load checkpoint state: {state_exc}")
        await _send_message(
            content=f"Execution stopped: {halt_reason}",
            parent_id=message.id,
            author="system",
        )

    messages = final_state.get("messages", [])
    tokens_in = final_state.get("tokens_in", 0)
    tokens_out = final_state.get("tokens_out", 0)
    cost_eur = final_state.get("cost_eur", 0.0)
    halted = final_state.get("halted", False)
    budget_exceeded = final_state.get("budget_exceeded", False)
    halt_reason = final_state.get("halt_reason", "")
    pending_approval = final_state.get("pending_approval")
    hitl_decisions = final_state.get("hitl_decisions", [])
    honeypot_events = final_state.get("honeypot_events", [])

    cl.user_session.set("tokens_in", tokens_in)
    cl.user_session.set("tokens_out", tokens_out)
    cl.user_session.set("cost_eur", cost_eur)
    cl.user_session.set("halted", halted)
    cl.user_session.set("budget_exceeded", budget_exceeded)
    cl.user_session.set("halt_reason", halt_reason)
    cl.user_session.set("pending_approval", pending_approval)
    cl.user_session.set("hitl_decisions", hitl_decisions)
    cl.user_session.set("honeypot_events", honeypot_events)
    cl.user_session.set("msg_count", len(messages))

    final_content = ""
    if messages:
        last = messages[-1]
        final_content = last.content if hasattr(last, "content") else str(last)

    if halted and halt_reason:
        await _send_message(
            content=f"Execution stopped: {halt_reason}",
            parent_id=message.id,
            author="system",
        )

    if messages:
        try:
            inspector_text = _format_state_inspector(
                messages,
                tokens_in, tokens_out, cost_eur,
                halted, budget_exceeded, halt_reason,
                pending_approval, hitl_decisions, honeypot_events,
                d_in=tokens_in - tokens_in_before,
                d_out=tokens_out - tokens_out_before,
                d_cost=cost_eur - cost_eur_before,
                msgs_before=msgs_before,
            )
            await _send_message(
                content=f"**State Inspector**\n\n{inspector_text}",
                parent_id=message.id,
                author="system",
            )
        except Exception as e:
            print(f"[inspector error] {e}")

    await _send_message(
        content=f"💰 `€{cost_eur:.6f}` this session",
        parent_id=message.id,
        author="system",
    )

    if final_content:
        answer_msg = await _send_message(
            content=final_content,
            metadata={"langsmith_run_id": str(last_run_id)},
        )
        ANSWER_RUN_IDS[answer_msg.id] = str(last_run_id)
        example_id = create_answer_example(
            user_message=message.content,
            assistant_answer=final_content,
            thread_id=thread_id,
            message_id=answer_msg.id,
            run_id=str(last_run_id),
        )
        if example_id:
            ANSWER_EXAMPLE_IDS[answer_msg.id] = example_id
        if answer_msg.parent_id:
            # Chainlit's feedback UI attaches to the auto on_message run step
            # (this message's parent), so cache that id too.
            ANSWER_RUN_IDS[answer_msg.parent_id] = str(last_run_id)
            if example_id:
                ANSWER_EXAMPLE_IDS[answer_msg.parent_id] = example_id


@cl.on_stop
async def on_stop():
    checkpointer_cm = cl.user_session.get("checkpointer_cm")
    if checkpointer_cm:
        try:
            await checkpointer_cm.__aexit__(None, None, None)
        except Exception:
            pass
