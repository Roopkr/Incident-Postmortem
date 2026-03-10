from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    logs: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    deployments: list[dict[str, Any]]
    incident_ticket: dict[str, Any]
    rag_context: str
    incident_understanding: dict[str, Any]
    timeline: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    selected_root_cause: str
    confidence: float
    report: dict[str, Any]
    uncertainty: str
