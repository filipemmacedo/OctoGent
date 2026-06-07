import logging
import json
from pathlib import Path
from typing import Any, Optional

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import ThreadDict
from dotenv import load_dotenv
from langgraph.errors import GraphRecursionError
from starlette.datastructures import Headers

load_dotenv()
logging.basicConfig(level=logging.INFO)

from src.config import build_graph_config
from src.mcp_tools import build_mcp_config, describe_mcp_config, load_ga_tools
from src.tools import list_tables, describe_table, query_database
from src.graph import build_graph, create_checkpointer

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


@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo=_DB_URI)


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
        cursor = await conn.execute(
            """
            UPDATE steps
            SET "parentId" = NULL
            WHERE "parentId" IS NOT NULL
              AND "parentId" NOT IN (SELECT "id" FROM steps)
            """
        )
        repaired = max(cursor.rowcount, 0)
        await conn.commit()
    if repaired:
        print(f"[startup] Repaired {repaired} orphan Chainlit step parent(s)")
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
    checkpointer_cm = create_checkpointer()
    checkpointer = await checkpointer_cm.__aenter__()
    graph = build_graph(all_tools, checkpointer)
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
    msg = cl.Message(content=content, **kwargs)
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
        config = {"configurable": {"thread_id": thread_id}}
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
    lines.append(f"cost_eur:  €{cost_eur:.6f}  (+€{d_cost:.6f} this turn)")
    lines.append("```")
    return "\n".join(lines)


@cl.on_message
async def on_message(message: cl.Message):
    try:
        await _handle_message(message)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        await _send_message(content=f"⚠️ Error: {exc}", parent_id=message.id)


async def _handle_message(message: cl.Message):
    graph = cl.user_session.get("graph")
    thread_id = cl.user_session.get("thread_id")

    if graph is None:
        await _send_message(
            content="⚠️ Session not initialised — please refresh the page.",
            parent_id=message.id,
        )
        return

    config = build_graph_config(thread_id)

    tokens_in_before = cl.user_session.get("tokens_in", 0)
    tokens_out_before = cl.user_session.get("tokens_out", 0)
    cost_eur_before = cl.user_session.get("cost_eur", 0.0)
    msgs_before = cl.user_session.get("msg_count", 0)

    final_state: dict = {}
    tool_steps: dict[str, cl.Step] = {}

    try:
        async for event in graph.astream_events(
            {"messages": [{"role": "user", "content": message.content}]},
            config=config,
            version="v2",
        ):
            kind = event["event"]

            if kind == "on_tool_start":
                tool_name = event["name"]
                step = cl.Step(name=tool_name, type="tool")
                await step.__aenter__()
                tool_steps[event["run_id"]] = step

            elif kind == "on_tool_end":
                run_id = event["run_id"]
                if run_id in tool_steps:
                    step = tool_steps.pop(run_id)
                    output = event["data"].get("output", "")
                    step.output = str(output)[:800]
                    await step.__aexit__(None, None, None)

            elif kind == "on_chain_end" and event.get("name") == "LangGraph":
                final_state = event["data"].get("output", {})
    except GraphRecursionError as exc:
        halt_reason = f"Loop limit exceeded: {exc}"
        print(f"[recursion] halted: {halt_reason}")
        for step in tool_steps.values():
            await step.__aexit__(None, None, None)
        tool_steps.clear()
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

    cl.user_session.set("tokens_in", tokens_in)
    cl.user_session.set("tokens_out", tokens_out)
    cl.user_session.set("cost_eur", cost_eur)
    cl.user_session.set("halted", halted)
    cl.user_session.set("budget_exceeded", budget_exceeded)
    cl.user_session.set("halt_reason", halt_reason)
    cl.user_session.set("msg_count", len(messages))

    final_content = ""
    if messages:
        last = messages[-1]
        final_content = last.content if hasattr(last, "content") else str(last)

    if final_content:
        await _send_message(content=final_content, parent_id=message.id)

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
                d_in=tokens_in - tokens_in_before,
                d_out=tokens_out - tokens_out_before,
                d_cost=cost_eur - cost_eur_before,
                msgs_before=msgs_before,
            )
            await _send_message(
                content=f"**State Inspector**\n\n{inspector_text}",
                parent_id=message.id,
            )
        except Exception as e:
            print(f"[inspector error] {e}")

    await _send_message(
        content=f"💰 `€{cost_eur:.6f}` this session",
        parent_id=message.id,
        author="system",
    )


@cl.on_stop
async def on_stop():
    checkpointer_cm = cl.user_session.get("checkpointer_cm")
    if checkpointer_cm:
        try:
            await checkpointer_cm.__aexit__(None, None, None)
        except Exception:
            pass
