from typing import Any
import logging

from langgraph.graph import END, START, StateGraph

from backend.graph.nodes import IncidentGraphNodes
from backend.graph.state import GraphState

logger = logging.getLogger(__name__)


class IncidentGraph:
    def __init__(self, llm: Any, root_cause_strategy: Any) -> None:
        self.nodes = IncidentGraphNodes(llm, root_cause_strategy)
        self.graph = self._build_graph()
        logger.info("IncidentGraph initialized")

    def _build_graph(self):
        logger.debug("Building incident state graph")
        workflow = StateGraph(GraphState)
        workflow.add_node("incident_understanding", self.nodes.incident_understanding_node)
        workflow.add_node("timeline_reconstruction", self.nodes.timeline_reconstruction_node)
        workflow.add_node("hypothesis_generation", self.nodes.hypothesis_generation_node)
        workflow.add_node("evidence_evaluation", self.nodes.evidence_evaluation_node)
        workflow.add_node("report_generation", self.nodes.report_generation_node)

        workflow.add_edge(START, "incident_understanding")
        workflow.add_edge("incident_understanding", "timeline_reconstruction")
        workflow.add_edge("timeline_reconstruction", "hypothesis_generation")
        workflow.add_edge("hypothesis_generation", "evidence_evaluation")
        workflow.add_edge("evidence_evaluation", "report_generation")
        workflow.add_edge("report_generation", END)

        return workflow.compile()

    def run(self, initial_state: GraphState) -> GraphState:
        logger.info(
            "Running incident graph logs=%s alerts=%s deployments=%s",
            len(initial_state.get("logs", [])),
            len(initial_state.get("alerts", [])),
            len(initial_state.get("deployments", [])),
        )
        try:
            result = self.graph.invoke(initial_state)
            logger.info("Incident graph run completed")
            return result
        except Exception as exc:
            logger.exception("Incident graph run failed error=%s", exc)
            raise
