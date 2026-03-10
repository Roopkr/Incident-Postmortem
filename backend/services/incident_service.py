from abc import ABC, abstractmethod
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from backend.graph.incident_graph import IncidentGraph
from backend.llm.llm_factory import LLMFactory
from backend.preprocessing.parser import (
    load_csv_records,
    load_json_file,
    sort_records_by_timestamp,
)
from backend.services.rag_service import RagService
from backend.utils.sanitization import sanitize_log_records

logger = logging.getLogger(__name__)


class RootCauseStrategy(ABC):
    @abstractmethod
    def choose(self, evaluations: list[dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError


class HighestConfidenceRootCauseStrategy(RootCauseStrategy):
    def choose(self, evaluations: list[dict[str, Any]]) -> dict[str, Any]:
        if not evaluations:
            return {
                "cause": "Insufficient evidence",
                "confidence": 0.0,
                "supporting_timestamps": [],
                "reasoning": "No candidate hypotheses were available.",
            }

        return max(evaluations, key=lambda item: float(item.get("confidence", 0.0)))


class IncidentService:
    def __init__(
        self,
        data_dir: Path | None = None,
        rag_dir: Path | None = None,
        root_cause_strategy: RootCauseStrategy | None = None,
    ) -> None:
        self.data_dir = data_dir or (Path(__file__).resolve().parents[2] / "sample_data")
        self.rag_dir = rag_dir or (Path(__file__).resolve().parents[2] / "rag_data")
        self.rag_service = RagService(self.rag_dir)
        self.root_cause_strategy = root_cause_strategy or HighestConfidenceRootCauseStrategy()
        logger.info(
            "IncidentService initialized data_dir=%s rag_dir=%s",
            self.data_dir,
            self.rag_dir,
        )

    @staticmethod
    def _validate_record_list(records: Any, field_name: str) -> list[dict[str, Any]]:
        if records is None:
            return []
        if not isinstance(records, list):
            raise ValueError(f"'{field_name}' must be a list of JSON objects.")
        validated: list[dict[str, Any]] = []
        for index, item in enumerate(records):
            if not isinstance(item, dict):
                raise ValueError(f"'{field_name}[{index}]' must be a JSON object.")
            validated.append(item)
        return validated

    def _load_default_payload(self) -> dict[str, Any]:
        logger.info("Loading default incident payload from sample_data")
        logs = load_csv_records(self.data_dir / "logs.csv")
        alerts = load_csv_records(self.data_dir / "alerts.csv")
        deployments = load_csv_records(self.data_dir / "deployments.csv")
        incident_ticket = load_json_file(self.data_dir / "incident_ticket.json")

        return {
            "logs": sort_records_by_timestamp(logs),
            "alerts": sort_records_by_timestamp(alerts),
            "deployments": sort_records_by_timestamp(deployments),
            "incident_ticket": incident_ticket,
        }

    def _merge_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        defaults = self._load_default_payload()

        input_logs = (
            self._validate_record_list(payload.get("logs"), "logs")
            if "logs" in payload
            else defaults["logs"]
        )
        input_alerts = (
            self._validate_record_list(payload.get("alerts"), "alerts")
            if "alerts" in payload
            else defaults["alerts"]
        )
        input_deployments = (
            self._validate_record_list(payload.get("deployments"), "deployments")
            if "deployments" in payload
            else defaults["deployments"]
        )
        input_incident_ticket = payload.get("incident_ticket", defaults["incident_ticket"])
        if not isinstance(input_incident_ticket, dict):
            raise ValueError("'incident_ticket' must be a JSON object.")

        merged = {
            "logs": input_logs or defaults["logs"],
            "alerts": input_alerts or defaults["alerts"],
            "deployments": input_deployments or defaults["deployments"],
            "incident_ticket": input_incident_ticket or defaults["incident_ticket"],
        }
        merged["logs"] = sanitize_log_records(merged["logs"])
        logger.info(
            "Merged incident payload logs=%s alerts=%s deployments=%s",
            len(merged["logs"]),
            len(merged["alerts"]),
            len(merged["deployments"]),
        )
        return merged

    def validate_logs(self, logs: Any) -> dict[str, Any]:
        records = self._validate_record_list(logs, "logs")
        if not records:
            return {
                "valid": False,
                "total_rows": 0,
                "valid_timestamps": 0,
                "invalid_timestamps": 0,
                "error_rows": 0,
                "rows_with_missing_required_fields": 0,
                "missing_columns": ["timestamp", "service", "level", "message"],
                "warnings": ["No logs were provided."],
            }

        required_columns = ["timestamp", "service", "level", "message"]
        dataframe = pd.DataFrame(records)
        missing_columns = [col for col in required_columns if col not in dataframe.columns]

        timestamp_series = pd.to_datetime(
            dataframe["timestamp"], errors="coerce"
        ) if "timestamp" in dataframe.columns else pd.Series([], dtype="datetime64[ns]")
        valid_timestamps = int(timestamp_series.notna().sum())
        invalid_timestamps = int(len(records) - valid_timestamps)

        rows_with_missing_required_fields = 0
        for row in records:
            if any(not str(row.get(col, "")).strip() for col in required_columns):
                rows_with_missing_required_fields += 1

        error_rows = 0
        if "level" in dataframe.columns:
            error_rows = int((dataframe["level"].astype(str).str.upper() == "ERROR").sum())

        warnings: list[str] = []
        if missing_columns:
            warnings.append(f"Missing required columns: {', '.join(missing_columns)}")
        if invalid_timestamps > 0:
            warnings.append(f"{invalid_timestamps} rows have invalid timestamp format.")
        if rows_with_missing_required_fields > 0:
            warnings.append(
                f"{rows_with_missing_required_fields} rows have empty required fields."
            )

        valid = not missing_columns and invalid_timestamps == 0 and rows_with_missing_required_fields == 0
        logger.info(
            "Log validation result valid=%s total_rows=%s invalid_timestamps=%s missing_columns=%s",
            valid,
            len(records),
            invalid_timestamps,
            missing_columns,
        )
        return {
            "valid": valid,
            "total_rows": len(records),
            "valid_timestamps": valid_timestamps,
            "invalid_timestamps": invalid_timestamps,
            "error_rows": error_rows,
            "rows_with_missing_required_fields": rows_with_missing_required_fields,
            "missing_columns": missing_columns,
            "warnings": warnings,
        }

    def reconstruct_incident(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            merged_payload = self._merge_payload(payload)
            incident_ticket = merged_payload["incident_ticket"]
            query_parts = [
                str(incident_ticket.get("title", "")),
                str(incident_ticket.get("summary", "")),
                str(incident_ticket.get("initial_description", "")),
                " ".join(str(service) for service in incident_ticket.get("impacted_services", [])),
            ]
            rag_query = " ".join(part for part in query_parts if part).strip()
            rag_context = self.rag_service.retrieve(rag_query, top_k=3)
            logger.info("RAG query generated chars=%s", len(rag_query))

            llm = LLMFactory().get_llm()
            graph = IncidentGraph(llm=llm, root_cause_strategy=self.root_cause_strategy)

            initial_state = {
                "logs": merged_payload["logs"],
                "alerts": merged_payload["alerts"],
                "deployments": merged_payload["deployments"],
                "incident_ticket": incident_ticket,
                "rag_context": rag_context,
                "timeline": [],
                "hypotheses": [],
                "selected_root_cause": "",
                "confidence": 0.0,
                "report": {},
                "uncertainty": "",
            }

            final_state = graph.run(initial_state)
            logger.info(
                "Incident reconstruction completed timeline=%s hypotheses=%s confidence=%s",
                len(final_state.get("timeline", [])),
                len(final_state.get("hypotheses", [])),
                final_state.get("confidence", 0.0),
            )

            return {
                "incident_understanding": final_state.get("incident_understanding", {}),
                "timeline": final_state.get("timeline", []),
                "hypotheses": final_state.get("hypotheses", []),
                "selected_root_cause": final_state.get("selected_root_cause", ""),
                "confidence": final_state.get("confidence", 0.0),
                "report": final_state.get("report", {}),
                "uncertainty": final_state.get("uncertainty", ""),
            }
        except Exception as exc:
            logger.exception("Incident reconstruction failed error=%s", exc)
            raise
