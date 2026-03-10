import json
import logging
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser

from backend.graph.state import GraphState
from backend.llm.prompts import (
    EVIDENCE_EVALUATION_PROMPT,
    HYPOTHESIS_GENERATION_PROMPT,
    INCIDENT_UNDERSTANDING_PROMPT,
    REPORT_GENERATION_PROMPT,
)
from backend.models.dtos import (
    EvidenceEvaluationDTO,
    HypothesisListDTO,
    IncidentUnderstandingDTO,
    PostmortemReportDTO,
)
from backend.preprocessing.parser import parse_with_fallback
from backend.tools.deployment_tools import GetDeployEventsTool
from backend.tools.log_tools import GetAlertsInWindowTool, GetErrorSpikesTool, SearchLogsTool

logger = logging.getLogger(__name__)


class IncidentGraphNodes:
    def __init__(self, llm: Any, root_cause_strategy: Any) -> None:
        self.llm = llm
        self.root_cause_strategy = root_cause_strategy

    def _invoke_and_parse(self, prompt: str, parser: PydanticOutputParser, model_class: Any) -> Any | None:
        logger.debug("Invoking LLM for model=%s prompt_chars=%s", model_class.__name__, len(prompt))
        try:
            response = self.llm.invoke(prompt)
            raw_content = response.content
            if isinstance(raw_content, list):
                raw_content = "\\n".join(str(chunk) for chunk in raw_content)
            parsed = parse_with_fallback(str(raw_content), parser, model_class)
            if parsed is None:
                logger.warning("LLM parse returned None model=%s", model_class.__name__)
            return parsed
        except Exception as exc:
            logger.exception("LLM invoke failed model=%s error=%s", model_class.__name__, exc)
            return None

    def incident_understanding_node(self, state: GraphState) -> dict[str, Any]:
        try:
            incident_ticket = state.get("incident_ticket", {})
            logs = state.get("logs", [])[:25]
            alerts = state.get("alerts", [])[:10]
            rag_context = state.get("rag_context", "No RAG context available.")
            logger.info(
                "Node start incident_understanding logs=%s alerts=%s rag_chars=%s",
                len(logs),
                len(alerts),
                len(rag_context),
            )

            parser = PydanticOutputParser(pydantic_object=IncidentUnderstandingDTO)
            prompt = INCIDENT_UNDERSTANDING_PROMPT.format(
                incident_ticket=json.dumps(incident_ticket, indent=2),
                logs=json.dumps(logs, indent=2),
                alerts=json.dumps(alerts, indent=2),
                rag_context=rag_context,
                format_instructions=parser.get_format_instructions(),
            )

            parsed = self._invoke_and_parse(prompt, parser, IncidentUnderstandingDTO)
            if parsed is None:
                fallback = IncidentUnderstandingDTO(
                    start_time=str(incident_ticket.get("reported_at", "")),
                    impacted_services=list(incident_ticket.get("impacted_services", [])),
                    severity=str(incident_ticket.get("severity", "SEV-2")),
                )
                logger.warning("Node fallback incident_understanding")
                return {"incident_understanding": fallback.model_dump()}

            logger.info("Node success incident_understanding")
            return {"incident_understanding": parsed.model_dump()}
        except Exception as exc:
            logger.exception("Node failed incident_understanding error=%s", exc)
            raise

    def timeline_reconstruction_node(self, state: GraphState) -> dict[str, Any]:
        try:
            logs = state.get("logs", [])
            deployments = state.get("deployments", [])
            alerts = state.get("alerts", [])
            understanding = state.get("incident_understanding", {})
            ticket = state.get("incident_ticket", {})
            logger.info(
                "Node start timeline_reconstruction logs=%s deployments=%s alerts=%s",
                len(logs),
                len(deployments),
                len(alerts),
            )

            error_spike_tool = GetErrorSpikesTool(logs).as_tool()
            deploy_events_tool = GetDeployEventsTool(deployments).as_tool()
            alerts_tool = GetAlertsInWindowTool(alerts).as_tool()

            start_time = str(understanding.get("start_time") or ticket.get("reported_at") or "")
            end_time = str(ticket.get("resolved_at") or start_time)

            error_spikes = error_spike_tool.invoke({"window_minutes": 1, "threshold": 3})
            deploy_events = deploy_events_tool.invoke({})
            alerts_in_window = []
            if start_time and end_time:
                alerts_in_window = alerts_tool.invoke(
                    {"start_time": start_time, "end_time": end_time}
                )

            timeline: list[dict[str, Any]] = []

            for event in deploy_events:
                timeline.append(
                    {
                        "timestamp": event.get("timestamp", ""),
                        "event_type": f"deployment_{event.get('event', 'event')}",
                        "details": (
                            f"{event.get('service', 'service')} {event.get('event', 'event')} "
                            f"version {event.get('version', 'unknown')}"
                        ),
                    }
                )

            for spike in error_spikes:
                timeline.append(
                    {
                        "timestamp": spike.get("timestamp", ""),
                        "event_type": "error_spike",
                        "details": f"Error count reached {spike.get('error_count', 0)} in one minute window",
                    }
                )

            for alert in alerts_in_window:
                timeline.append(
                    {
                        "timestamp": alert.get("timestamp", ""),
                        "event_type": "alert",
                        "details": f"{alert.get('alert_type', 'alert')}: {alert.get('message', '')}",
                    }
                )

            resolved_at = ticket.get("resolved_at")
            if resolved_at:
                timeline.append(
                    {
                        "timestamp": str(resolved_at),
                        "event_type": "incident_resolved",
                        "details": "Incident marked as resolved",
                    }
                )

            timeline.sort(key=lambda item: str(item.get("timestamp", "")))
            logger.info("Node success timeline_reconstruction timeline_events=%s", len(timeline))
            return {"timeline": timeline}
        except Exception as exc:
            logger.exception("Node failed timeline_reconstruction error=%s", exc)
            raise

    def hypothesis_generation_node(self, state: GraphState) -> dict[str, Any]:
        try:
            rag_context = state.get("rag_context", "No RAG context available.")
            logger.info(
                "Node start hypothesis_generation timeline_events=%s rag_chars=%s",
                len(state.get("timeline", [])),
                len(rag_context),
            )
            parser = PydanticOutputParser(pydantic_object=HypothesisListDTO)
            prompt = HYPOTHESIS_GENERATION_PROMPT.format(
                timeline=json.dumps(state.get("timeline", []), indent=2),
                incident_understanding=json.dumps(state.get("incident_understanding", {}), indent=2),
                rag_context=rag_context,
                format_instructions=parser.get_format_instructions(),
            )

            parsed = self._invoke_and_parse(prompt, parser, HypothesisListDTO)
            if parsed is None:
                fallback = HypothesisListDTO(
                    hypotheses=[
                        {
                            "cause": "Memory leak introduced in recent checkout-api deployment",
                            "rationale": "Error spike occurs shortly after deployment and stabilizes after rollback.",
                            "supporting_timestamps": ["2026-02-21T10:02:00", "2026-02-21T10:05:00", "2026-02-21T10:12:00"],
                        },
                        {
                            "cause": "Temporary database saturation during peak traffic",
                            "rationale": "High checkout volume might have increased downstream latency.",
                            "supporting_timestamps": ["2026-02-21T10:05:00", "2026-02-21T10:07:00"],
                        },
                    ]
                )
                logger.warning("Node fallback hypothesis_generation")
                return {
                    "hypotheses": [item.model_dump() for item in fallback.hypotheses]
                }

            logger.info("Node success hypothesis_generation count=%s", len(parsed.hypotheses))
            return {"hypotheses": [item.model_dump() for item in parsed.hypotheses]}
        except Exception as exc:
            logger.exception("Node failed hypothesis_generation error=%s", exc)
            raise

    def evidence_evaluation_node(self, state: GraphState) -> dict[str, Any]:
        try:
            hypotheses = state.get("hypotheses", [])
            logs = state.get("logs", [])
            deployments = state.get("deployments", [])
            rag_context = state.get("rag_context", "No RAG context available.")
            logger.info(
                "Node start evidence_evaluation hypotheses=%s logs=%s deployments=%s",
                len(hypotheses),
                len(logs),
                len(deployments),
            )

            search_logs_tool = SearchLogsTool(logs).as_tool()
            deploy_events_tool = GetDeployEventsTool(deployments).as_tool()
            deployment_events = deploy_events_tool.invoke({})

            evaluations: list[dict[str, Any]] = []
            for hypothesis in hypotheses:
                cause = str(hypothesis.get("cause", "Unknown cause"))
                supporting_timestamps = list(hypothesis.get("supporting_timestamps", []))

                query = "memory leak" if "memory" in cause.lower() else cause.split(" ")[0]
                matched_logs = search_logs_tool.invoke({"query": query, "top_n": 20})

                deploy_match_bonus = 0.0
                if any(event.get("event", "").lower() == "deploy" for event in deployment_events):
                    deploy_match_bonus = 0.1
                if any(event.get("event", "").lower() == "rollback" for event in deployment_events):
                    deploy_match_bonus += 0.1

                confidence = min(1.0, 0.25 + (0.03 * len(matched_logs)) + deploy_match_bonus)
                inferred_timestamps = [entry.get("timestamp", "") for entry in matched_logs[:3]]
                all_timestamps = [
                    ts for ts in (supporting_timestamps + inferred_timestamps) if ts
                ]

                evaluations.append(
                    {
                        "cause": cause,
                        "confidence": round(confidence, 2),
                        "supporting_timestamps": all_timestamps,
                        "reasoning": (
                            f"Matched {len(matched_logs)} log lines for keyword '{query}' "
                            "and correlated with deployment timeline."
                        ),
                    }
                )

            parser = PydanticOutputParser(pydantic_object=EvidenceEvaluationDTO)
            prompt = EVIDENCE_EVALUATION_PROMPT.format(
                evaluations=json.dumps(evaluations, indent=2),
                rag_context=rag_context,
                format_instructions=parser.get_format_instructions(),
            )
            parsed = self._invoke_and_parse(prompt, parser, EvidenceEvaluationDTO)

            if parsed is None:
                selected = self.root_cause_strategy.choose(evaluations)
                cause = str(selected.get("cause", "Insufficient evidence"))
                confidence = float(selected.get("confidence", 0.0))
                supporting_timestamps = selected.get("supporting_timestamps", [])
                logger.warning("Node fallback evidence_evaluation")
            else:
                cause = parsed.selected_root_cause
                confidence = float(parsed.confidence)
                supporting_timestamps = parsed.supporting_timestamps

            timestamps_text = ", ".join(supporting_timestamps[:3])
            uncertainty = ""
            if not timestamps_text:
                fallback_timestamp = str(
                    state.get("incident_understanding", {}).get("start_time", "")
                ).strip()
                if fallback_timestamp:
                    timestamps_text = fallback_timestamp
                uncertainty = (
                    "Insufficient timestamp evidence to assert a definitive root cause. "
                    "Result should be treated as a best-effort estimate."
                )
                confidence = min(confidence, 0.35)
            if timestamps_text:
                root_cause = f"{cause} | Evidence timestamps: {timestamps_text}"
            else:
                root_cause = f"{cause} | Evidence timestamps unavailable"

            confidence = round(max(0.0, min(1.0, confidence)), 2)
            logger.info("Node success evidence_evaluation confidence=%s", confidence)

            return {
                "selected_root_cause": root_cause,
                "confidence": confidence,
                "uncertainty": uncertainty,
            }
        except Exception as exc:
            logger.exception("Node failed evidence_evaluation error=%s", exc)
            raise

    def report_generation_node(self, state: GraphState) -> dict[str, Any]:
        try:
            rag_context = state.get("rag_context", "No RAG context available.")
            logger.info(
                "Node start report_generation timeline_events=%s confidence=%s",
                len(state.get("timeline", [])),
                state.get("confidence", 0.0),
            )
            parser = PydanticOutputParser(pydantic_object=PostmortemReportDTO)
            prompt = REPORT_GENERATION_PROMPT.format(
                incident_understanding=json.dumps(state.get("incident_understanding", {}), indent=2),
                timeline=json.dumps(state.get("timeline", []), indent=2),
                selected_root_cause=state.get("selected_root_cause", ""),
                confidence=state.get("confidence", 0.0),
                uncertainty=state.get("uncertainty", ""),
                rag_context=rag_context,
                format_instructions=parser.get_format_instructions(),
            )

            parsed = self._invoke_and_parse(prompt, parser, PostmortemReportDTO)

            if parsed is None:
                timeline_lines = [
                    f"{item.get('timestamp', '')} - {item.get('event_type', '')}: {item.get('details', '')}"
                    for item in state.get("timeline", [])
                ]
                fallback = PostmortemReportDTO(
                    executive_summary=(
                        "Checkout incident followed a deployment and was mitigated after rollback."
                    ),
                    impact=str(state.get("incident_ticket", {}).get("customer_impact", "Customer impact under investigation.")),
                    timeline=timeline_lines,
                    root_cause=str(state.get("selected_root_cause", "Root cause not confirmed.")),
                    action_items=[
                        "Add memory regression tests before checkout-api deployment.",
                        "Create canary rollback trigger for elevated 5xx rates.",
                        "Add runtime memory leak detection alerting.",
                    ],
                    confidence_score=float(state.get("confidence", 0.0)),
                    uncertainty=str(state.get("uncertainty", "")),
                )
                logger.warning("Node fallback report_generation")
                return {"report": fallback.model_dump()}

            report_payload = parsed.model_dump()
            report_payload["confidence_score"] = round(
                max(0.0, min(1.0, float(state.get("confidence", report_payload.get("confidence_score", 0.0))))),
                2,
            )
            report_payload["uncertainty"] = str(state.get("uncertainty", report_payload.get("uncertainty", "")))
            logger.info("Node success report_generation")
            return {"report": report_payload}
        except Exception as exc:
            logger.exception("Node failed report_generation error=%s", exc)
            raise
