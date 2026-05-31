import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langchain_core.callbacks import get_usage_metadata_callback
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from src.state import AgentState

# EUR pricing for gpt-4o-mini (USD→EUR at 0.92)
PRICE_INPUT_PER_TOKEN = 0.15 / 1_000_000 * 0.92
PRICE_OUTPUT_PER_TOKEN = 0.60 / 1_000_000 * 0.92
EUR_USD_RATE = 0.92

CHECKPOINTS_PATH = Path(__file__).parent.parent / ".checkpoints" / "chat_history.db"


@asynccontextmanager
async def create_checkpointer():
    """Open a persistent async SQLite checkpointer for the active graph lifetime."""
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    CHECKPOINTS_PATH.parent.mkdir(exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(CHECKPOINTS_PATH)) as checkpointer:
        await checkpointer.setup()
        yield checkpointer

SYSTEM_PROMPT = """You are a data assistant with access to two data sources:

1. **E-commerce SQLite database** — a local database whose schema you do not know in advance.
   Rules for SQLite — follow this order strictly:
   - ALWAYS call `list_tables` first before answering any data question.
   - ALWAYS call `describe_table` on each relevant table before writing a query.
   - ALWAYS use `query_database` with a SELECT statement to retrieve data.
   - Only SELECT queries are allowed — never attempt INSERT, UPDATE, DELETE, or DROP.

2. **Google Analytics 4 (GA4)** — session and event data via MCP tools (if available).
   Use GA4 tools to answer questions about traffic sources, sessions, events, and user behaviour.

**Cross-source queries**: One table in the SQLite database has a `ga_client_id` column that
links to GA4's `client_id`. Use this bridge when questions require data from both sources.

Be concise and factual. Always derive your answers from tool results, not assumptions.
If GA4 tools are not available, say so clearly.
"""


def build_graph(tools: list[Any], checkpointer=None):
    """Build and compile the LangGraph ReAct agent. Returns the compiled graph."""
    model = init_chat_model(
        os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        model_provider="openai",
    ).bind_tools(tools)

    def call_model(state: AgentState) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        with get_usage_metadata_callback() as cb:
            response = model.invoke(messages)

        # usage_metadata is keyed by model name; sum across all models
        usage = cb.usage_metadata
        new_in = sum(v.get("input_tokens", 0) for v in usage.values())
        new_out = sum(v.get("output_tokens", 0) for v in usage.values())
        tokens_in = state.get("tokens_in", 0) + new_in
        tokens_out = state.get("tokens_out", 0) + new_out
        cost_eur = (
            state.get("cost_eur", 0.0)
            + new_in * PRICE_INPUT_PER_TOKEN
            + new_out * PRICE_OUTPUT_PER_TOKEN
        )
        print(
            f"[tokens] +{new_in}in/{new_out}out | session total: €{cost_eur:.6f}"
        )
        return {
            "messages": [response],
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_eur": cost_eur,
        }

    graph = StateGraph(AgentState)
    graph.add_node("call_model", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", tools_condition)
    graph.add_edge("tools", "call_model")
    return graph.compile(checkpointer=checkpointer)
