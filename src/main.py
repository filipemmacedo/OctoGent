import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

from src.mcp_tools import build_mcp_config, load_ga_tools
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
            "messages": len(messages),
        }
    )


async def main() -> None:
    sqlite_tools = [list_tables, describe_table, query_database]

    mcp_config = build_mcp_config()
    if mcp_config:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        client = MultiServerMCPClient({"ga4": mcp_config})
        await client.__aenter__()
        ga_tools = await load_ga_tools(client)
    else:
        client = None
        ga_tools = []

    try:
        async with create_checkpointer() as checkpointer:
            all_tools = sqlite_tools + ga_tools
            graph = build_graph(all_tools, checkpointer)

            print("\nAgent ready. Type your question (Ctrl+C to quit).\n")
            thread_id = "cli-session"
            config = {"configurable": {"thread_id": thread_id}}

            while True:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                result = await graph.ainvoke(
                    {"messages": [{"role": "user", "content": user_input}]},
                    config=config,
                )
                answer = result["messages"][-1].content
                print(f"\nAgent: {answer}\n")
                _print_state_debug(result)
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye.")
    finally:
        if client:
            await client.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(main())
