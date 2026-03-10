from typing import Any
import logging

import pandas as pd
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SearchLogsInput(BaseModel):
    query: str = Field(..., description="Text to search in log messages")
    start_time: str | None = Field(default=None)
    end_time: str | None = Field(default=None)
    top_n: int = Field(default=25, ge=1, le=200)


class ErrorSpikesInput(BaseModel):
    window_minutes: int = Field(default=1, ge=1, le=60)
    threshold: int = Field(default=3, ge=1, le=500)


class AlertsWindowInput(BaseModel):
    start_time: str
    end_time: str


class SearchLogsTool:
    def __init__(self, log_records: list[dict[str, Any]]) -> None:
        self.df = pd.DataFrame(log_records)
        if "timestamp" in self.df.columns:
            self.df["timestamp"] = pd.to_datetime(self.df["timestamp"], errors="coerce")
        logger.debug("SearchLogsTool initialized rows=%s", len(self.df))

    def execute(
        self,
        query: str,
        start_time: str | None = None,
        end_time: str | None = None,
        top_n: int = 25,
    ) -> list[dict[str, Any]]:
        if self.df.empty:
            logger.debug("SearchLogsTool execute called with empty dataframe")
            return []
        if "message" not in self.df.columns or "timestamp" not in self.df.columns:
            logger.warning("SearchLogsTool missing required columns columns=%s", list(self.df.columns))
            return []

        results = self.df.copy()
        if start_time:
            start_dt = pd.to_datetime(start_time, errors="coerce")
            results = results[results["timestamp"] >= start_dt]
        if end_time:
            end_dt = pd.to_datetime(end_time, errors="coerce")
            results = results[results["timestamp"] <= end_dt]

        results = results[results["message"].astype(str).str.contains(query, case=False, na=False)]
        results = results.sort_values("timestamp").head(top_n)

        output = results.fillna("").to_dict(orient="records")
        for row in output:
            value = row.get("timestamp")
            if isinstance(value, pd.Timestamp):
                row["timestamp"] = value.strftime("%Y-%m-%dT%H:%M:%S")
        logger.debug("SearchLogsTool query=%s returned=%s", query, len(output))
        return output

    def as_tool(self) -> StructuredTool:
        return StructuredTool.from_function(
            func=self.execute,
            name="search_logs",
            description="Search logs for specific message patterns.",
            args_schema=SearchLogsInput,
        )


class GetErrorSpikesTool:
    def __init__(self, log_records: list[dict[str, Any]]) -> None:
        self.df = pd.DataFrame(log_records)
        if "timestamp" in self.df.columns:
            self.df["timestamp"] = pd.to_datetime(self.df["timestamp"], errors="coerce")
        logger.debug("GetErrorSpikesTool initialized rows=%s", len(self.df))

    def execute(self, window_minutes: int = 1, threshold: int = 3) -> list[dict[str, Any]]:
        if self.df.empty:
            logger.debug("GetErrorSpikesTool execute called with empty dataframe")
            return []
        if "level" not in self.df.columns or "timestamp" not in self.df.columns:
            logger.warning("GetErrorSpikesTool missing required columns columns=%s", list(self.df.columns))
            return []

        errors = self.df[self.df["level"].astype(str).str.upper() == "ERROR"].dropna(subset=["timestamp"])
        if errors.empty:
            logger.debug("GetErrorSpikesTool found no error-level rows")
            return []

        window_label = f"{window_minutes}min"
        errors = errors.copy()
        errors["bucket"] = errors["timestamp"].dt.floor(window_label)
        grouped = errors.groupby("bucket").size().reset_index(name="error_count")
        spikes = grouped[grouped["error_count"] >= threshold]

        output = [
            {
                "timestamp": row["bucket"].strftime("%Y-%m-%dT%H:%M:%S"),
                "error_count": int(row["error_count"]),
            }
            for _, row in spikes.iterrows()
        ]
        logger.debug(
            "GetErrorSpikesTool window_minutes=%s threshold=%s spikes=%s",
            window_minutes,
            threshold,
            len(output),
        )
        return output

    def as_tool(self) -> StructuredTool:
        return StructuredTool.from_function(
            func=self.execute,
            name="get_error_spikes",
            description="Detect error spikes from logs grouped by time window.",
            args_schema=ErrorSpikesInput,
        )


class GetAlertsInWindowTool:
    def __init__(self, alert_records: list[dict[str, Any]]) -> None:
        self.df = pd.DataFrame(alert_records)
        if "timestamp" in self.df.columns:
            self.df["timestamp"] = pd.to_datetime(self.df["timestamp"], errors="coerce")
        logger.debug("GetAlertsInWindowTool initialized rows=%s", len(self.df))

    def execute(self, start_time: str, end_time: str) -> list[dict[str, Any]]:
        if self.df.empty:
            logger.debug("GetAlertsInWindowTool execute called with empty dataframe")
            return []
        if "timestamp" not in self.df.columns:
            logger.warning("GetAlertsInWindowTool missing timestamp column columns=%s", list(self.df.columns))
            return []

        start_dt = pd.to_datetime(start_time, errors="coerce")
        end_dt = pd.to_datetime(end_time, errors="coerce")

        filtered = self.df[(self.df["timestamp"] >= start_dt) & (self.df["timestamp"] <= end_dt)]
        output = filtered.fillna("").to_dict(orient="records")

        for row in output:
            value = row.get("timestamp")
            if isinstance(value, pd.Timestamp):
                row["timestamp"] = value.strftime("%Y-%m-%dT%H:%M:%S")
        logger.debug(
            "GetAlertsInWindowTool start=%s end=%s returned=%s",
            start_time,
            end_time,
            len(output),
        )
        return output

    def as_tool(self) -> StructuredTool:
        return StructuredTool.from_function(
            func=self.execute,
            name="get_alerts_in_window",
            description="Get alerts between two timestamps.",
            args_schema=AlertsWindowInput,
        )
