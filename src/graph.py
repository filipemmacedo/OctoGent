import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import RetryPolicy

from src.config import get_agent_max_cost_eur
from src.state import AgentState

# EUR pricing for gpt-4o-mini (USD to EUR at 0.92)
PRICE_INPUT_PER_TOKEN = 0.15 / 1_000_000 * 0.92
PRICE_OUTPUT_PER_TOKEN = 0.60 / 1_000_000 * 0.92
EUR_USD_RATE = 0.92

CHECKPOINTS_PATH = Path(__file__).parent.parent / ".checkpoints" / "chat_history.db"
ROUTE_CALL_MODEL = "call_model"
ROUTE_TOOLS = "tools"
ROUTE_END = "__end__"


@asynccontextmanager
async def create_checkpointer():
    """Open a persistent async SQLite checkpointer for the active graph lifetime."""
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    CHECKPOINTS_PATH.parent.mkdir(exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(CHECKPOINTS_PATH)) as checkpointer:
        await checkpointer.setup()
        yield checkpointer


def _build_system_prompt() -> str:
    today = date.today().isoformat()
    ga4_property_id = os.getenv("GA4_PROPERTY_ID", "").strip()
    property_hint = (
        "\n   A default GA4 property is configured in the MCP server environment. "
        "For GA4 report tools, omit `property_id` unless the user explicitly specifies another property."
        if ga4_property_id
        else "\n   No default GA4 property_id is configured. If a GA4 report needs a property, list available properties or ask the user for a property ID. Never invent one."
    )

    return f"""You are a data assistant with access to two data sources:

1. **E-commerce SQLite database** - a local database whose schema you do not know in advance.
   Rules for SQLite - follow this order strictly:
   - ALWAYS call `list_tables` first before answering any data question.
   - ALWAYS call `describe_table` on each relevant table before writing a query.
   - ALWAYS use `query_database` with a SELECT statement to retrieve data.
   - Only SELECT queries are allowed - never attempt INSERT, UPDATE, DELETE, or DROP.

2. **Google Analytics 4 (GA4)** - session and event data via MCP tools (if available).
   Use GA4 tools to answer questions about traffic sources, sessions, events, and user behaviour.
{property_hint}
   GA4 date rules:
   - Tool date arguments must be ISO dates (`YYYY-MM-DD`), `today`, `yesterday`, or relative values like `7daysAgo`.
   - Today's date is {today}. If the user gives a clear colloquial date like "6th May", convert it to an ISO date before calling a tool.
   - If the date is ambiguous or malformed, ask a short clarification question instead of sending an invalid date to a tool.

Routing rules:
- For e-commerce/business data questions about orders, products, customers, revenue, purchases, inventory, or database contents, use SQLite tools.
- For website/app analytics questions about traffic, users, sessions, events, conversions, pages, sources, campaigns, realtime activity, or GA4 metrics, use GA4 tools.
- For generic questions that do not require local data or GA4 data, answer directly with the main model and do not call tools.
- For mixed questions, use both sources only when the question clearly needs both.

**Cross-source queries**: One table in the SQLite database has a `ga_client_id` column that
links to GA4's `client_id`. Use this bridge when questions require data from both sources.

Be concise and factual. Always derive your answers from tool results, not assumptions.
If GA4 tools are not available, say so clearly.
"""


def _current_turn_messages(messages: list) -> list:
    """Keep the active user turn and its complete tool-call transcript."""
    for index in range(len(messages) - 1, -1, -1):
        if getattr(messages[index], "type", None) == "human":
            return messages[index:]
    return messages


def build_graph(tools: list[Any], checkpointer=None):
    """Build and compile the LangGraph ReAct agent. Returns the compiled graph."""
    model = init_chat_model(
        os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        model_provider="openai",
    ).bind_tools(tools)

    def call_model(state: AgentState) -> dict:
        current_turn = _current_turn_messages(state["messages"])
        messages = [SystemMessage(content=_build_system_prompt())] + current_turn
        with get_usage_metadata_callback() as cb:
            response = model.invoke(messages)

        # usage_metadata is keyed by model name; sum across all models.
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
        print(f"[tokens] +{new_in}in/{new_out}out | session total: EUR {cost_eur:.6f}")
        return {
            "messages": [response],
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_eur": cost_eur,
            "halted": False,
            "budget_exceeded": False,
            "halt_reason": "",
        }

    def budget_check(state: AgentState) -> dict:
        budget_eur = get_agent_max_cost_eur()
        cost_eur = state.get("cost_eur", 0.0)
        if cost_eur < budget_eur:
            return {
                "halted": False,
                "budget_exceeded": False,
                "halt_reason": "",
            }

        reason = (
            f"Budget exceeded: EUR {cost_eur:.6f} >= "
            f"limit EUR {budget_eur:.6f}"
        )
        print(f"[budget] halted: {reason}")
        return {
            "halted": True,
            "budget_exceeded": True,
            "halt_reason": reason,
        }

    def route_after_budget_check(state: AgentState) -> str:
        if state.get("budget_exceeded", False):
            return ROUTE_END

        messages = state.get("messages", [])
        if not messages:
            return ROUTE_CALL_MODEL

        last_message = messages[-1]
        if hasattr(last_message, "tool_calls"):
            return tools_condition(state)

        return ROUTE_CALL_MODEL

    graph = StateGraph(AgentState)
    graph.add_node("call_model", call_model)
    graph.add_node("budget_check", budget_check)
    graph.add_node(
        "tools",
        ToolNode(tools, handle_tool_errors=True),
        retry=RetryPolicy(max_attempts=3),
    )
    graph.add_edge(START, "call_model")
    graph.add_edge("call_model", "budget_check")
    graph.add_edge("tools", "call_model")
    graph.add_conditional_edges(
        "budget_check",
        route_after_budget_check,
        {
            ROUTE_CALL_MODEL: "call_model",
            ROUTE_TOOLS: "tools",
            ROUTE_END: END,
        },
    )
    return graph.compile(checkpointer=checkpointer)
