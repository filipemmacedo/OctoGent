from __future__ import annotations

import os
import uuid
from typing import Any, Callable

try:
    from langsmith import Client, traceable
    from langsmith.run_helpers import get_current_run_tree
except Exception:  # pragma: no cover - import fallback for minimal local envs
    Client = None
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


def safe_text(value: Any, limit: int = 240) -> str:
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
            safe[key] = safe_text(value) if isinstance(value, str) else value

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


def build_model_step_metrics(
    step_input_tokens: int,
    step_output_tokens: int,
    cumulative_tokens_in: int,
    cumulative_tokens_out: int,
    cumulative_cost_eur: float,
    model_context_window: int,
) -> dict[str, Any]:
    """Build the numeric-only metrics payload for one call_model step.

    context_window_pct measures this call's trimmed prompt against the model
    window, not the cumulative ledger.
    """
    context_window_pct = 0.0
    if model_context_window > 0:
        context_window_pct = round(
            step_input_tokens / model_context_window * 100, 2
        )

    return {
        "step_input_tokens": step_input_tokens,
        "step_output_tokens": step_output_tokens,
        "cumulative_tokens_in": cumulative_tokens_in,
        "cumulative_tokens_out": cumulative_tokens_out,
        "cumulative_cost_eur": cumulative_cost_eur,
        "model_context_window": model_context_window,
        "context_window_pct": context_window_pct,
    }


# LangSmith dashboards cannot chart metadata on the Y-axis, only feedback
# scores; these keys are mirrored as feedback so they are chartable.
CHARTABLE_METRIC_KEYS = (
    "context_window_pct",
    "cumulative_cost_eur",
    "step_input_tokens",
)

_feedback_client: Any = None


def _get_feedback_client() -> Any:
    global _feedback_client
    if Client is None:
        return None
    if _feedback_client is None:
        try:
            _feedback_client = Client()
        except Exception as exc:
            print(f"[observability] failed to create LangSmith client: {exc}")
            _feedback_client = False
    return _feedback_client or None


def _log_step_metric_feedback(run: Any, metrics: dict[str, Any]) -> None:
    client = _get_feedback_client()
    if client is None:
        return

    for key in CHARTABLE_METRIC_KEYS:
        if key not in metrics:
            continue
        try:
            # Synchronous POST per key; adds a little latency per model step.
            client.create_feedback(
                run_id=run.id,
                key=key,
                score=metrics[key],
                trace_id=run.trace_id,
            )
        except Exception as exc:
            print(f"[observability] failed to log feedback {key}: {exc}")


# Lowercased substrings that mark a tool result as "no usable data".
# Sourced from src/tools.py return strings, ToolNode error wrapping, and
# empty GA4 report payloads.
DATA_MISS_MARKERS = (
    "no tables found",
    "no user-facing tables found",
    "does not exist",
    "no results found",
    '"rows": []',
)


def classify_tool_result_hit(content: Any) -> float:
    """Score a tool result 1.0 (returned usable data) or 0.0 (miss/error)."""
    if isinstance(content, (list, tuple)):
        content = " ".join(str(part) for part in content)
    text = str(content).strip()
    if not text:
        return 0.0

    lowered = text.lower()
    if lowered.startswith("error") or lowered.startswith("query error"):
        return 0.0
    for marker in DATA_MISS_MARKERS:
        if marker in lowered:
            return 0.0
    return 1.0


def log_tool_data_hits(messages: list[Any]) -> None:
    """Log a data_hit feedback score per tool result on the current run.

    The hit-rate analogue of an offload hit rate: did each data-store access
    (SQLite or GA4) return usable data? Never raises.
    """
    if get_current_run_tree is None or not messages:
        return

    try:
        run = get_current_run_tree()
    except Exception as exc:
        print(f"[observability] failed to get run for data hits: {exc}")
        return
    if run is None:
        return

    client = _get_feedback_client()
    if client is None:
        return

    for message in messages:
        score = classify_tool_result_hit(getattr(message, "content", ""))
        tool_name = str(getattr(message, "name", "") or "unknown")
        try:
            client.create_feedback(
                run_id=run.id,
                key="data_hit",
                score=score,
                trace_id=run.trace_id,
                comment=f"tool: {tool_name}",
            )
        except Exception as exc:
            print(f"[observability] failed to log data_hit for {tool_name}: {exc}")


# Human 👍/👎 ratings from the Chainlit UI, recorded on the root run that
# produced the rated answer. The feedback id is derived deterministically from
# the rated message id so re-rating upserts instead of appending.
USER_FEEDBACK_KEY = "user_score"
_USER_FEEDBACK_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, f"{APP_NAME}/user_score")


def user_feedback_id(message_id: str) -> str:
    return str(uuid.uuid5(_USER_FEEDBACK_NAMESPACE, str(message_id)))


def create_answer_example(
    user_message: str,
    assistant_answer: str,
    thread_id: str,
    message_id: str,
    run_id: str,
) -> str | None:
    """Create an example in a configured LangSmith dataset; never raise."""
    dataset_id = os.getenv("LANGSMITH_FEEDBACK_DATASET_ID")
    dataset_name = os.getenv("LANGSMITH_FEEDBACK_DATASET_NAME")
    if not dataset_id and not dataset_name:
        return None

    client = _get_feedback_client()
    if client is None:
        return None

    kwargs = {"dataset_id": dataset_id} if dataset_id else {"dataset_name": dataset_name}
    try:
        example = client.create_example(
            **kwargs,
            inputs={"user_message": user_message},
            outputs={"assistant_answer": assistant_answer},
            metadata={
                "app": APP_NAME,
                "interface": "chainlit",
                "thread_id": thread_id,
                "message_id": message_id,
                "source_run_id": run_id,
            },
        )
        return str(example.id)
    except Exception as exc:
        print(f"[observability] failed to create dataset example: {exc}")
        return None


def log_user_feedback(
    run_id: str,
    score: float,
    comment: str | None,
    message_id: str,
    example_id: str | None = None,
) -> bool:
    """Record a human rating as user_score feedback on a run; never raise."""
    client = _get_feedback_client()
    if client is None:
        return False

    feedback_id = user_feedback_id(message_id)

    try:
        client.create_feedback(
            run_id=run_id,
            trace_id=run_id,
            key=USER_FEEDBACK_KEY,
            score=float(score),
            comment=comment or None,
            feedback_id=feedback_id,
        )
        if example_id:
            update_dataset_example_feedback(
                example_id=example_id,
                score=score,
                comment=comment,
                message_id=message_id,
                run_id=run_id,
            )
        return True
    except Exception as create_exc:
        # The feedback id may already exist (re-rating); fall back to update.
        try:
            client.update_feedback(
                feedback_id,
                score=float(score),
                comment=comment or None,
            )
            if example_id:
                update_dataset_example_feedback(
                    example_id=example_id,
                    score=score,
                    comment=comment,
                    message_id=message_id,
                    run_id=run_id,
                )
            return True
        except Exception as update_exc:
            print(
                "[observability] failed to log user feedback: "
                f"create: {create_exc}; update: {update_exc}"
            )
            return False


def update_dataset_example_feedback(
    example_id: str,
    score: float,
    comment: str | None,
    message_id: str,
    run_id: str,
) -> bool:
    client = _get_feedback_client()
    if client is None:
        return False

    try:
        existing = client.read_example(example_id)
        metadata = getattr(existing, "metadata", None)
        if not isinstance(metadata, dict):
            metadata = {}
        client.update_example(
            example_id=example_id,
            metadata={
                **metadata,
                "user_score": float(score),
                "user_feedback": comment or None,
                "message_id": message_id,
                "source_run_id": run_id,
            },
        )
        return True
    except Exception as exc:
        print(f"[observability] failed to update dataset example: {exc}")
        return False


def delete_user_feedback(message_id: str) -> bool:
    """Delete the user_score feedback derived from a message id; never raise."""
    client = _get_feedback_client()
    if client is None:
        return False

    try:
        client.delete_feedback(user_feedback_id(message_id))
        return True
    except Exception as exc:
        print(f"[observability] failed to delete user feedback: {exc}")
        return False


def attach_model_step_metrics(metrics: dict[str, Any]) -> None:
    """Attach step metrics to the current LangSmith run only; never raise.

    Metrics are recorded as run metadata (for trace inspection and filtering)
    and the chartable subset is mirrored as feedback scores (for dashboards).
    """
    if get_current_run_tree is None:
        return

    try:
        run = get_current_run_tree()
        if run is None:
            return
        run.add_metadata(metrics)
        run.patch()
    except Exception as exc:
        print(f"[observability] failed to attach step metrics: {exc}")
        return

    _log_step_metric_feedback(run, metrics)


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
