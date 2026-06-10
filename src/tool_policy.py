from typing import Any, Literal, TypedDict


ToolClassification = Literal["safe", "sensitive", "honeypot"]
ToolSource = Literal["sqlite", "ga4", "unknown"]


class ToolPolicy(TypedDict):
    name: str
    source: ToolSource
    classification: ToolClassification
    reason: str


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", ""))


def build_tool_policies(
    sqlite_tools: list[Any],
    ga_tools: list[Any],
) -> dict[str, ToolPolicy]:
    """Build deterministic governance policy from known tool source lists."""
    policies: dict[str, ToolPolicy] = {}

    for tool in sqlite_tools:
        name = _tool_name(tool)
        if not name:
            continue
        policies[name] = {
            "name": name,
            "source": "sqlite",
            "classification": "safe",
            "reason": "Local read-only SQLite tool",
        }

    for tool in ga_tools:
        name = _tool_name(tool)
        if not name:
            continue
        policies[name] = {
            "name": name,
            "source": "ga4",
            "classification": "sensitive",
            "reason": "Authenticated external GA4 analytics data access",
        }

    return policies


def default_unknown_tool_policy(tool_name: str) -> ToolPolicy:
    """Conservatively classify unknown tools as sensitive."""
    return {
        "name": tool_name,
        "source": "unknown",
        "classification": "sensitive",
        "reason": "Tool source is unknown; approval required by default",
    }
