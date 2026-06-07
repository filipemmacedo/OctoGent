import logging
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _split_args(value: str) -> list[str]:
    """Parse a shell-like argument string from .env."""
    if not value.strip():
        return []
    return shlex.split(value, posix=os.name != "nt")


def _credential_summary(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {"configured": False}

    path = Path(path_value)
    summary: dict[str, Any] = {
        "configured": True,
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        return summary

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        summary["error"] = f"Could not read credential JSON: {exc}"
        return summary

    summary["type"] = data.get("type")
    if data.get("client_email"):
        summary["client_email"] = data["client_email"]
    if data.get("client_id"):
        summary["client_id_present"] = True
    return summary


def describe_mcp_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return a log-safe MCP config summary."""
    if not config:
        return {"configured": False}

    summary: dict[str, Any] = {
        "configured": True,
        "transport": config.get("transport"),
    }
    if config.get("transport") == "stdio":
        env = config.get("env") or {}
        summary.update(
            {
                "command": config.get("command"),
                "args": config.get("args", []),
                "google_project_id": env.get("GOOGLE_PROJECT_ID"),
                "google_cloud_project": env.get("GOOGLE_CLOUD_PROJECT"),
                "google_client_id_configured": bool(env.get("GOOGLE_CLIENT_ID")),
                "google_client_secret_configured": bool(env.get("GOOGLE_CLIENT_SECRET")),
                "ga4_property_id_configured": bool(env.get("GA4_PROPERTY_ID")),
                "ga4_token_path_configured": bool(env.get("GA4_TOKEN_PATH")),
                "credentials": _credential_summary(
                    env.get("GOOGLE_APPLICATION_CREDENTIALS")
                ),
            }
        )
    else:
        summary["url"] = config.get("url")
        summary["has_auth_header"] = bool((config.get("headers") or {}).get("Authorization"))
    return summary


def build_mcp_config() -> dict[str, Any] | None:
    """Return MCP server config dict, or None if GA MCP is not configured."""
    transport = os.getenv("GA_MCP_TRANSPORT", "streamable_http").strip()

    if transport == "stdio":
        command = os.getenv("GA_MCP_COMMAND", "").strip()
        if not command:
            logger.warning("GA_MCP_COMMAND not set for stdio MCP - running SQLite-only")
            return None
        if command.lower() in {"python", "python.exe"}:
            command = sys.executable

        env = dict(os.environ)
        config: dict[str, Any] = {
            "transport": "stdio",
            "command": command,
            "args": _split_args(os.getenv("GA_MCP_ARGS", "")),
            "cwd": str(Path(__file__).parent.parent),
            "env": env,
        }
        return config

    url = os.getenv("GA_MCP_URL", "").strip()
    if not url:
        logger.warning("GA_MCP_URL not set - running SQLite-only")
        return None

    auth = os.getenv("GA_MCP_AUTH", "")
    config: dict[str, Any] = {"url": url, "transport": transport}
    if auth:
        config["headers"] = {"Authorization": auth}
    return config


async def load_ga_tools(client: Any) -> list[Any]:
    """Get GA4 tools from a MultiServerMCPClient.

    With langchain-mcp-adapters 0.1.x, get_tools() creates a new MCP session
    for each tool call, so the client itself is not used as a context manager.
    """
    try:
        tools = await client.get_tools()
    except Exception:
        logger.exception("Failed to load GA4 tools from MCP")
        raise

    logger.info("Loaded %d GA4 tools from MCP: %s", len(tools), [t.name for t in tools])
    return tools
