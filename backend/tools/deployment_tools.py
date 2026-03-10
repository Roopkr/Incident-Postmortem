from typing import Any
import logging

import pandas as pd
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DeployEventsInput(BaseModel):
    start_time: str | None = Field(default=None)
    end_time: str | None = Field(default=None)
    event_types: list[str] | None = Field(default=None)


class GetDeployEventsTool:
    def __init__(self, deployment_records: list[dict[str, Any]]) -> None:
        self.df = pd.DataFrame(deployment_records)
        if "timestamp" in self.df.columns:
            self.df["timestamp"] = pd.to_datetime(self.df["timestamp"], errors="coerce")
        logger.debug("GetDeployEventsTool initialized rows=%s", len(self.df))

    def execute(
        self,
        start_time: str | None = None,
        end_time: str | None = None,
        event_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if self.df.empty:
            logger.debug("GetDeployEventsTool execute called with empty dataframe")
            return []
        if "timestamp" not in self.df.columns:
            logger.warning("GetDeployEventsTool missing timestamp column columns=%s", list(self.df.columns))
            return []

        results = self.df.copy()
        if start_time:
            start_dt = pd.to_datetime(start_time, errors="coerce")
            results = results[results["timestamp"] >= start_dt]
        if end_time:
            end_dt = pd.to_datetime(end_time, errors="coerce")
            results = results[results["timestamp"] <= end_dt]
        if event_types:
            if "event" not in results.columns:
                logger.warning("GetDeployEventsTool missing event column for event filter")
                return []
            lowered = {entry.lower() for entry in event_types}
            results = results[results["event"].astype(str).str.lower().isin(lowered)]

        output = results.sort_values("timestamp").fillna("").to_dict(orient="records")
        for row in output:
            value = row.get("timestamp")
            if isinstance(value, pd.Timestamp):
                row["timestamp"] = value.strftime("%Y-%m-%dT%H:%M:%S")
        logger.debug(
            "GetDeployEventsTool start=%s end=%s event_types=%s returned=%s",
            start_time,
            end_time,
            event_types or [],
            len(output),
        )
        return output

    def as_tool(self) -> StructuredTool:
        return StructuredTool.from_function(
            func=self.execute,
            name="get_deploy_events",
            description="Get deployment and rollback events from deployment history.",
            args_schema=DeployEventsInput,
        )
