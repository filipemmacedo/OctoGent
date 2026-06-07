import asyncio
import json
import logging
from dotenv import load_dotenv
from langgraph.errors import GraphRecursionError

load_dotenv()
logging.basicConfig(level=logging.INFO)

from src.config import build_graph_config
from src.mcp_tools import build_mcp_config, describe_mcp_config, load_ga_tools
from src.tools import list_tables, describe_table, query_database
from src.graph import build_graph, create_checkpointer


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
            "messages": len(messages),
        }
    )


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
            graph = build_graph(all_tools, checkpointer)

            print("\nAgent ready. Type your question (Ctrl+C to quit).\n")
            thread_id = "cli-session"
            config = build_graph_config(thread_id)

            while True:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                try:
                    result = await graph.ainvoke(
                        {"messages": [{"role": "user", "content": user_input}]},
                        config=config,
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
