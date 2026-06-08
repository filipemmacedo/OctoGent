import asyncio
import json
import logging
from dotenv import load_dotenv
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

load_dotenv()
logging.basicConfig(level=logging.INFO)

from src.config import build_graph_config
from src.mcp_tools import build_mcp_config, describe_mcp_config, load_ga_tools
from src.tools import list_tables, describe_table, query_database
from src.graph import build_graph, create_checkpointer
from src.tool_policy import build_tool_policies


def _print_state_debug(state: dict) -> None:
    messages = state.get("messages", [])
    print("\n[debug state]")
    print(
        {
            "tokens_in": state.get("tokens_in", 0),
            "tokens_out": state.get("tokens_out", 0),
            "cost_eur": state.get("cost_eur", 0.0),
            "halted": state.get("halted", False),
            "budget_exceeded": state.get("budget_exceeded", False),
            "halt_reason": state.get("halt_reason", ""),
            "pending_approval": bool(state.get("pending_approval")),
            "hitl_decisions": len(state.get("hitl_decisions", [])),
            "messages": len(messages),
        }
    )


def _print_approval_request(payload: dict) -> None:
    print("\n[hitl approval required]")
    for index, tool_call in enumerate(payload.get("tool_calls", []), start=1):
        print(f"{index}. {tool_call.get('name')} ({tool_call.get('classification')})")
        print(f"   reason: {tool_call.get('reason')}")
        print(f"   args: {json.dumps(tool_call.get('args', {}), indent=2)}")


def _read_cli_approval(payload: dict) -> dict:
    _print_approval_request(payload)
    while True:
        choice = input("Approve, edit args, or reject? [a/e/r]: ").strip().lower()
        if choice in {"a", "approve"}:
            return {"decision": "approve", "comment": "Approved in CLI"}
        if choice in {"r", "reject"}:
            reason = input("Rejection reason (optional): ").strip()
            return {
                "decision": "reject",
                "comment": reason or "Rejected in CLI",
            }
        if choice in {"e", "edit"}:
            print("Enter edited args as JSON.")
            print("For one tool call, enter the args object directly.")
            print("For multiple calls, enter {\"tool_call_id\": {args...}}.")
            raw = input("Edited args JSON: ").strip()
            try:
                edited_args = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"Invalid JSON: {exc}")
                continue
            if not isinstance(edited_args, dict):
                print("Edited args must be a JSON object.")
                continue
            return {
                "decision": "edit",
                "edited_args": edited_args,
                "comment": "Edited in CLI",
            }
        print("Please enter a, e, or r.")


async def _invoke_with_cli_approval(graph, graph_input, config: dict) -> dict:
    current_input = graph_input
    while True:
        result = await graph.ainvoke(current_input, config=config)
        interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
        if not interrupts:
            return result

        interrupt_obj = interrupts[0]
        payload = getattr(interrupt_obj, "value", interrupt_obj)
        if not isinstance(payload, dict) or payload.get("kind") != "tool_approval":
            raise RuntimeError(f"Unsupported graph interrupt: {payload!r}")

        decision = _read_cli_approval(payload)
        current_input = Command(resume=decision)


async def main() -> None:
    sqlite_tools = [list_tables, describe_table, query_database]

    mcp_config = build_mcp_config()
    print("[mcp] config:")
    print(json.dumps(describe_mcp_config(mcp_config), indent=2))
    if mcp_config:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        try:
            client = MultiServerMCPClient({"ga4": mcp_config})
            ga_tools = await load_ga_tools(client)
            print(f"[mcp] loaded GA tools: {[tool.name for tool in ga_tools]}")
        except Exception as exc:
            import traceback
            print(f"[mcp] failed to load GA tools: {exc!r}")
            traceback.print_exc()
            print("[mcp] continuing with SQLite-only tools")
            ga_tools = []
    else:
        ga_tools = []
        print("[mcp] GA MCP not configured; using SQLite-only tools")

    try:
        async with create_checkpointer() as checkpointer:
            all_tools = sqlite_tools + ga_tools
            tool_policies = build_tool_policies(sqlite_tools, ga_tools)
            graph = build_graph(all_tools, checkpointer, tool_policies)

            print("\nAgent ready. Type your question (Ctrl+C to quit).\n")
            thread_id = "cli-session"
            config = build_graph_config(thread_id)

            while True:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                try:
                    result = await _invoke_with_cli_approval(
                        graph,
                        {"messages": [{"role": "user", "content": user_input}]},
                        config,
                    )
                except GraphRecursionError as exc:
                    print(f"\n[recursion] halted: loop limit exceeded ({exc})")
                    continue

                halt_reason = result.get("halt_reason", "")
                if result.get("halted") and halt_reason:
                    print(f"\nAgent stopped: {halt_reason}\n")
                    _print_state_debug(result)
                    continue

                answer = result["messages"][-1].content
                print(f"\nAgent: {answer}\n")
                _print_state_debug(result)
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye.")
