import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import RetryPolicy, interrupt

from src.config import get_agent_max_cost_eur
from src.state import AgentState
from src.tool_policy import ToolPolicy, default_unknown_tool_policy

# EUR pricing for gpt-4o-mini (USD to EUR at 0.92)
PRICE_INPUT_PER_TOKEN = 0.15 / 1_000_000 * 0.92
PRICE_OUTPUT_PER_TOKEN = 0.60 / 1_000_000 * 0.92
EUR_USD_RATE = 0.92

CHECKPOINTS_PATH = Path(__file__).parent.parent / ".checkpoints" / "chat_history.db"
ROUTE_CALL_MODEL = "call_model"
ROUTE_APPROVAL_GATE = "approval_gate"
ROUTE_APPROVAL_INTERRUPT = "approval_interrupt"
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


def _message_tool_calls(message: Any) -> list[dict[str, Any]]:
    return list(getattr(message, "tool_calls", None) or [])


def _get_tool_policy(
    tool_policies: dict[str, ToolPolicy],
    tool_name: str,
) -> ToolPolicy:
    return tool_policies.get(tool_name) or default_unknown_tool_policy(tool_name)


def _build_approval_payload(
    tool_calls: list[dict[str, Any]],
    tool_policies: dict[str, ToolPolicy],
) -> dict[str, Any] | None:
    if not tool_calls:
        return None

    classified_calls: list[dict[str, Any]] = []
    sensitive_ids: list[str] = []
    for tool_call in tool_calls:
        name = str(tool_call.get("name", ""))
        policy = _get_tool_policy(tool_policies, name)
        tool_call_id = str(tool_call.get("id", ""))
        if policy["classification"] == "sensitive":
            sensitive_ids.append(tool_call_id)
        classified_calls.append(
            {
                "id": tool_call_id,
                "name": name,
                "args": tool_call.get("args", {}),
                "source": policy["source"],
                "classification": policy["classification"],
                "reason": policy["reason"],
            }
        )

    if not sensitive_ids:
        return None

    return {
        "kind": "tool_approval",
        "tool_calls": classified_calls,
        "sensitive_tool_call_ids": sensitive_ids,
    }


def _decision_value(resume_value: Any) -> str:
    if isinstance(resume_value, dict):
        return str(resume_value.get("decision", "")).strip().lower()
    return str(resume_value).strip().lower()


def _decision_comment(resume_value: Any) -> str:
    if not isinstance(resume_value, dict):
        return ""
    return str(
        resume_value.get("reason")
        or resume_value.get("comment")
        or resume_value.get("message")
        or ""
    )


def _edited_args_by_call_id(
    payload: dict[str, Any],
    resume_value: Any,
) -> dict[str, dict[str, Any]]:
    if not isinstance(resume_value, dict):
        return {}

    edited_args = resume_value.get("edited_args")
    if edited_args is None:
        edited_args = resume_value.get("args")
    if not isinstance(edited_args, dict):
        return {}

    tool_calls = payload.get("tool_calls", [])
    call_ids = {str(call.get("id", "")) for call in tool_calls}
    if len(tool_calls) == 1:
        only_id = str(tool_calls[0].get("id", ""))
        if only_id not in edited_args:
            return {only_id: edited_args}

    return {
        call_id: args
        for call_id, args in edited_args.items()
        if call_id in call_ids and isinstance(args, dict)
    }


def _copy_ai_message_with_tool_args(
    message: Any,
    final_args_by_id: dict[str, dict[str, Any]],
) -> Any:
    updated_tool_calls: list[dict[str, Any]] = []
    for tool_call in _message_tool_calls(message):
        updated_call = dict(tool_call)
        call_id = str(updated_call.get("id", ""))
        if call_id in final_args_by_id:
            updated_call["args"] = final_args_by_id[call_id]
        updated_tool_calls.append(updated_call)

    if hasattr(message, "model_copy"):
        return message.model_copy(update={"tool_calls": updated_tool_calls})
    return message.copy(update={"tool_calls": updated_tool_calls})


def _approval_decision_records(
    payload: dict[str, Any],
    decision: str,
    comment: str,
    final_args_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    timestamp = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []
    for tool_call in payload.get("tool_calls", []):
        call_id = str(tool_call.get("id", ""))
        original_args = tool_call.get("args", {})
        records.append(
            {
                "tool_call_id": call_id,
                "tool_name": tool_call.get("name", ""),
                "classification": tool_call.get("classification", ""),
                "source": tool_call.get("source", ""),
                "original_args": original_args,
                "final_args": final_args_by_id.get(call_id, original_args),
                "decision": decision,
                "reason": tool_call.get("reason", ""),
                "comment": comment,
                "timestamp": timestamp,
            }
        )
    return records


def build_graph(
    tools: list[Any],
    checkpointer=None,
    tool_policies: dict[str, ToolPolicy] | None = None,
):
    """Build and compile the LangGraph ReAct agent. Returns the compiled graph."""
    tool_policies = tool_policies or {}
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
            route = tools_condition(state)
            if route == ROUTE_TOOLS:
                return ROUTE_APPROVAL_GATE
            return route

        return ROUTE_CALL_MODEL

    def approval_gate(state: AgentState) -> dict:
        messages = state.get("messages", [])
        if not messages:
            return {"pending_approval": None}

        tool_calls = _message_tool_calls(messages[-1])
        payload = _build_approval_payload(tool_calls, tool_policies)
        if payload is None:
            if tool_calls:
                print("[hitl] safe tool calls approved automatically")
            return {"pending_approval": None}

        names = ", ".join(call["name"] for call in payload["tool_calls"])
        print(f"[hitl] approval required before tool execution: {names}")
        return {"pending_approval": payload}

    def route_after_approval_gate(state: AgentState) -> str:
        if state.get("pending_approval"):
            return ROUTE_APPROVAL_INTERRUPT

        messages = state.get("messages", [])
        if not messages:
            return ROUTE_CALL_MODEL

        last_message = messages[-1]
        if hasattr(last_message, "tool_calls"):
            return tools_condition(state)
        return ROUTE_CALL_MODEL

    def approval_interrupt(state: AgentState) -> dict:
        payload = state.get("pending_approval")
        if not payload:
            return {"pending_approval": None}

        resume_value = interrupt(payload)
        decision = _decision_value(resume_value)
        comment = _decision_comment(resume_value)

        if decision not in {"approve", "edit", "reject"}:
            decision = "reject"
            comment = comment or "Invalid or missing approval decision"

        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None
        final_args_by_id: dict[str, dict[str, Any]] = {}

        if decision == "edit":
            final_args_by_id = _edited_args_by_call_id(payload, resume_value)
            if last_message is not None and final_args_by_id:
                updated_message = _copy_ai_message_with_tool_args(
                    last_message,
                    final_args_by_id,
                )
                records = _approval_decision_records(
                    payload,
                    decision,
                    comment,
                    final_args_by_id,
                )
                print("[hitl] sensitive tool call approved with edited args")
                return {
                    "messages": [updated_message],
                    "pending_approval": None,
                    "hitl_decisions": records,
                }
            decision = "reject"
            comment = comment or "Edited arguments were missing or invalid"

        if decision == "approve":
            records = _approval_decision_records(payload, decision, comment, {})
            print("[hitl] sensitive tool call approved")
            return {
                "pending_approval": None,
                "hitl_decisions": records,
            }

        rejection_messages = [
            ToolMessage(
                content=(
                    "Human rejected this sensitive tool call before execution."
                    + (f" Reason: {comment}" if comment else "")
                ),
                tool_call_id=str(tool_call.get("id", "")),
                name=str(tool_call.get("name", "")),
            )
            for tool_call in payload.get("tool_calls", [])
        ]
        records = _approval_decision_records(payload, "reject", comment, {})
        print("[hitl] sensitive tool call rejected")
        return {
            "messages": rejection_messages,
            "pending_approval": None,
            "hitl_decisions": records,
        }

    def route_after_approval_interrupt(state: AgentState) -> str:
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
    graph.add_node("approval_gate", approval_gate)
    graph.add_node("approval_interrupt", approval_interrupt)
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
            ROUTE_APPROVAL_GATE: "approval_gate",
            ROUTE_END: END,
        },
    )
    graph.add_conditional_edges(
        "approval_gate",
        route_after_approval_gate,
        {
            ROUTE_CALL_MODEL: "call_model",
            ROUTE_APPROVAL_INTERRUPT: "approval_interrupt",
            ROUTE_TOOLS: "tools",
            ROUTE_END: END,
        },
    )
    graph.add_conditional_edges(
        "approval_interrupt",
        route_after_approval_interrupt,
        {
            ROUTE_CALL_MODEL: "call_model",
            ROUTE_TOOLS: "tools",
            ROUTE_END: END,
        },
    )
    return graph.compile(checkpointer=checkpointer)
