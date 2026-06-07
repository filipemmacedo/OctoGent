import os


DEFAULT_AGENT_MAX_COST_EUR = 0.05
DEFAULT_AGENT_RECURSION_LIMIT = 12


def _warn_invalid_env(name: str, value: str, default: object, reason: str) -> None:
    print(
        f"[config] Invalid {name}={value!r} ({reason}); "
        f"using default {default!r}"
    )


def get_agent_max_cost_eur() -> float:
    value = os.getenv("AGENT_MAX_COST_EUR", "").strip()
    if not value:
        return DEFAULT_AGENT_MAX_COST_EUR

    try:
        budget = float(value)
    except ValueError:
        _warn_invalid_env(
            "AGENT_MAX_COST_EUR",
            value,
            DEFAULT_AGENT_MAX_COST_EUR,
            "expected a decimal EUR amount",
        )
        return DEFAULT_AGENT_MAX_COST_EUR

    if budget <= 0:
        _warn_invalid_env(
            "AGENT_MAX_COST_EUR",
            value,
            DEFAULT_AGENT_MAX_COST_EUR,
            "must be greater than 0",
        )
        return DEFAULT_AGENT_MAX_COST_EUR

    return budget


def get_agent_recursion_limit() -> int:
    value = os.getenv("AGENT_RECURSION_LIMIT", "").strip()
    if not value:
        return DEFAULT_AGENT_RECURSION_LIMIT

    try:
        limit = int(value)
    except ValueError:
        _warn_invalid_env(
            "AGENT_RECURSION_LIMIT",
            value,
            DEFAULT_AGENT_RECURSION_LIMIT,
            "expected an integer",
        )
        return DEFAULT_AGENT_RECURSION_LIMIT

    if limit < 2:
        _warn_invalid_env(
            "AGENT_RECURSION_LIMIT",
            value,
            DEFAULT_AGENT_RECURSION_LIMIT,
            "must be at least 2",
        )
        return DEFAULT_AGENT_RECURSION_LIMIT

    return limit


def build_graph_config(thread_id: str) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": get_agent_recursion_limit(),
    }
