from __future__ import annotations

from typing import Any, Callable

try:
    from langsmith import traceable
    from langsmith.run_helpers import get_current_run_tree
except Exception:  # pragma: no cover - import fallback for minimal local envs
    traceable = None
    get_current_run_tree = None


APP_NAME = "langgraph-governed-agent"
GOVERNANCE_OBSERVABILITY_VERSION = "1"
BASE_GOVERNANCE_TAGS = ["governed-agent", "governance"]
HONEYPOT_INCIDENT_TAGS = [
    "security",
    "honeypot",
    "blocked",
    "severity:high",
    "governance-event:honeypot-blocked",
]


def governance_run_tags(interface: str) -> list[str]:
    return [*BASE_GOVERNANCE_TAGS, f"interface:{interface}"]


def governance_run_metadata(thread_id: str, interface: str) -> dict[str, Any]:
    return {
        "app": APP_NAME,
        "interface": interface,
        "thread_id": thread_id,
        "governance_observability_version": GOVERNANCE_OBSERVABILITY_VERSION,
    }


def _safe_text(value: Any, limit: int = 240) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _args_summary(args: Any) -> dict[str, Any]:
    if not isinstance(args, dict):
        return {"type": type(args).__name__}

    keys = sorted(str(key) for key in args.keys())
    return {
        "keys": keys,
        "types": {str(key): type(value).__name__ for key, value in args.items()},
    }


def sanitize_governance_event(event: dict[str, Any]) -> dict[str, Any]:
    """Return a LangSmith-safe event payload without raw sensitive args."""
    safe: dict[str, Any] = {}
    for key in (
        "governance_event",
        "tool_call_id",
        "tool_name",
        "source",
        "classification",
        "matched_object",
        "action",
        "decision",
        "reason",
        "comment",
        "timestamp",
        "cost_eur",
        "budget_eur",
        "halt_reason",
    ):
        if key in event and event[key] is not None:
            value = event[key]
            safe[key] = _safe_text(value) if isinstance(value, str) else value

    if "args" in event:
        safe["args_summary"] = _args_summary(event["args"])
    if "original_args" in event:
        safe["original_args_summary"] = _args_summary(event["original_args"])
    if "final_args" in event:
        safe["final_args_summary"] = _args_summary(event["final_args"])

    return safe


def _identity(value: Any, **_: Any) -> Any:
    return value


def _decorated_traceable(name: str, tags: list[str]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    if traceable is None:
        return _identity
    return traceable(
        name=name,
        run_type="chain",
        tags=tags,
        process_inputs=lambda inputs: inputs,
        process_outputs=lambda outputs: outputs,
    )(_identity)


_trace_honeypot_blocked = _decorated_traceable(
    "honeypot_blocked",
    [*BASE_GOVERNANCE_TAGS, "security", "honeypot", "blocked"],
)
_trace_hitl_decision = _decorated_traceable(
    "hitl_decision",
    [*BASE_GOVERNANCE_TAGS, "hitl"],
)
_trace_budget_halt = _decorated_traceable(
    "budget_halt",
    [*BASE_GOVERNANCE_TAGS, "budget", "halt"],
)


def _emit(
    trace_fn: Callable[..., dict[str, Any]],
    event: dict[str, Any],
    tags: list[str],
) -> dict[str, Any]:
    payload = sanitize_governance_event(event)
    metadata = {
        **payload,
        "governance_observability_version": GOVERNANCE_OBSERVABILITY_VERSION,
    }
    try:
        return trace_fn(
            payload,
            langsmith_extra={
                "metadata": metadata,
                "tags": tags,
            },
        )
    except Exception as exc:
        print(f"[observability] failed to emit {event.get('governance_event')}: {exc}")
        return payload


def _mark_active_trace_incident(
    tags: list[str],
    metadata: dict[str, Any],
) -> None:
    if get_current_run_tree is None:
        return

    try:
        run = get_current_run_tree()
        visited = set()
        while run is not None and id(run) not in visited:
            visited.add(id(run))
            run.add_tags(tags)
            run.add_metadata(metadata)
            run.patch()
            run = getattr(run, "parent_run", None)
    except Exception as exc:
        print(f"[observability] failed to mark active trace: {exc}")


def emit_honeypot_blocked(event: dict[str, Any]) -> dict[str, Any]:
    event = {"governance_event": "honeypot_blocked", **event}
    metadata = sanitize_governance_event(event)
    _mark_active_trace_incident(
        HONEYPOT_INCIDENT_TAGS,
        {
            **metadata,
            "governance_severity": "high",
            "governance_incident": True,
        },
    )
    return _emit(
        _trace_honeypot_blocked,
        event,
        [*BASE_GOVERNANCE_TAGS, *HONEYPOT_INCIDENT_TAGS],
    )


def emit_hitl_decision(event: dict[str, Any]) -> dict[str, Any]:
    event = {"governance_event": "hitl_decision", **event}
    decision = str(event.get("decision", "unknown"))
    return _emit(
        _trace_hitl_decision,
        event,
        [*BASE_GOVERNANCE_TAGS, "hitl", f"decision:{decision}"],
    )


def emit_budget_halt(event: dict[str, Any]) -> dict[str, Any]:
    event = {"governance_event": "budget_halt", **event}
    return _emit(
        _trace_budget_halt,
        event,
        [*BASE_GOVERNANCE_TAGS, "budget", "halt"],
    )
