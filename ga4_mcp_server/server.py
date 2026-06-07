from __future__ import annotations

from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from ga4_mcp_server.config import GA4MCPConfig
from ga4_mcp_server.ga4 import (
    list_accounts,
    list_properties,
    run_realtime_report as execute_realtime_report,
    run_report as execute_report,
)

load_dotenv()

mcp = FastMCP("Local GA4 OAuth MCP")


@mcp.tool()
def list_ga4_accounts() -> dict[str, Any]:
    """List Google Analytics accounts available to the authenticated user."""
    return list_accounts(GA4MCPConfig.from_env())


@mcp.tool()
def list_ga4_properties(account: str | None = None) -> dict[str, Any]:
    """List GA4 properties available to the authenticated user."""
    return list_properties(account=account, config=GA4MCPConfig.from_env())


@mcp.tool()
def run_ga4_report(
    start_date: str,
    end_date: str,
    dimensions: list[str],
    metrics: list[str],
    property_id: str | None = None,
    filters: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run a constrained GA4 Data API report."""
    return execute_report(
        property_id=property_id,
        start_date=start_date,
        end_date=end_date,
        dimensions=dimensions,
        metrics=metrics,
        filters=filters,
        config=GA4MCPConfig.from_env(),
    )


@mcp.tool()
def run_realtime_report(
    dimensions: list[str],
    metrics: list[str],
    property_id: str | None = None,
) -> dict[str, Any]:
    """Run a constrained GA4 realtime report."""
    return execute_realtime_report(
        property_id=property_id,
        dimensions=dimensions,
        metrics=metrics,
        config=GA4MCPConfig.from_env(),
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
