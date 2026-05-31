import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def build_mcp_config() -> dict[str, Any] | None:
    """Return MCP server config dict, or None if GA_MCP_URL is not set."""
    url = os.getenv("GA_MCP_URL", "").strip()
    if not url:
        logger.warning("GA_MCP_URL not set — running SQLite-only")
        return None

    transport = os.getenv("GA_MCP_TRANSPORT", "streamable_http")
    auth = os.getenv("GA_MCP_AUTH", "")
    config: dict[str, Any] = {"url": url, "transport": transport}
    if auth:
        config["headers"] = {"Authorization": auth}
    return config


async def load_ga_tools(client: Any) -> list[Any]:
    """Get GA4 tools from an already-entered MultiServerMCPClient.

    The caller is responsible for keeping the client open for the lifetime
    of any tool calls — exiting the client's context manager invalidates
    the returned tools.
    """
    tools = await client.get_tools()
    logger.info("Loaded %d GA4 tools from MCP", len(tools))
    return tools
