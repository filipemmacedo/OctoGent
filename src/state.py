import operator
from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    tokens_in: int
    tokens_out: int
    cost_eur: float
    halted: bool
    budget_exceeded: bool
    halt_reason: str
    pending_approval: dict[str, Any] | None
    hitl_decisions: Annotated[list[dict[str, Any]], operator.add]
    honeypot_events: Annotated[list[dict[str, Any]], operator.add]
