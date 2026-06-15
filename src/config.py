import os

from src.observability import governance_run_metadata, governance_run_tags


DEFAULT_AGENT_MAX_COST_EUR = 0.05
DEFAULT_AGENT_RECURSION_LIMIT = 12
# gpt-4o-mini context window; update AGENT_MODEL_CONTEXT_WINDOW when changing models.
DEFAULT_MODEL_CONTEXT_WINDOW = 128_000


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


def get_model_context_window() -> int:
    value = os.getenv("AGENT_MODEL_CONTEXT_WINDOW", "").strip()
    if not value:
        return DEFAULT_MODEL_CONTEXT_WINDOW

    try:
        window = int(value)
    except ValueError:
        _warn_invalid_env(
            "AGENT_MODEL_CONTEXT_WINDOW",
            value,
            DEFAULT_MODEL_CONTEXT_WINDOW,
            "expected an integer",
        )
        return DEFAULT_MODEL_CONTEXT_WINDOW

    if window <= 0:
        _warn_invalid_env(
            "AGENT_MODEL_CONTEXT_WINDOW",
            value,
            DEFAULT_MODEL_CONTEXT_WINDOW,
            "must be greater than 0",
        )
        return DEFAULT_MODEL_CONTEXT_WINDOW

    return window


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


def build_graph_config(
    thread_id: str,
    interface: str = "unknown",
    extra_metadata: dict | None = None,
    extra_tags: list[str] | None = None,
    run_id=None,
) -> dict:
    recursion_limit = get_agent_recursion_limit()
    metadata = {
        **governance_run_metadata(thread_id, interface),
        "recursion_limit": recursion_limit,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    tags = governance_run_tags(interface)
    if extra_tags:
        tags.extend(extra_tags)

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": recursion_limit,
        "metadata": metadata,
        "tags": tags,
    }
    if run_id is not None:
        # Caller-chosen root run id, so feedback can target the trace without
        # a LangSmith round trip.
        config["run_id"] = run_id
    return config
