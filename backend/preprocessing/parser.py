import json
import io
import logging
from pathlib import Path
from typing import Any, Type

import pandas as pd
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def extract_first_json_object(text: str) -> str | None:
    if not text:
        return None

    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start_index = text.find("{")
    if start_index == -1:
        return None

    depth = 0
    for idx in range(start_index, len(text)):
        char = text[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start_index : idx + 1]
    return None


def parse_with_fallback(
    raw_text: str,
    parser: PydanticOutputParser,
    model_class: Type[BaseModel],
) -> BaseModel | None:
    try:
        return parser.parse(raw_text)
    except Exception as exc:
        logger.warning("Primary parser failed; attempting JSON fallback error=%s", exc)

    json_block = extract_first_json_object(raw_text)
    if not json_block:
        logger.warning("No JSON object found in model output for fallback parsing")
        return None

    try:
        payload = json.loads(json_block)
        return model_class.model_validate(payload)
    except Exception as exc:
        logger.warning("Fallback JSON validation failed model=%s error=%s", model_class.__name__, exc)
        return None


def load_csv_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        logger.error("CSV file not found path=%s", path)
        raise ValueError(f"CSV file not found: {path}")

    logger.info("Loading CSV records path=%s", path)
    dataframe = pd.read_csv(path)
    if "timestamp" in dataframe.columns:
        parsed = pd.to_datetime(dataframe["timestamp"], errors="coerce")
        dataframe["timestamp"] = parsed.dt.strftime("%Y-%m-%dT%H:%M:%S")

    dataframe = dataframe.fillna("")
    logger.info("Loaded CSV records path=%s rows=%s", path, len(dataframe))
    return dataframe.to_dict(orient="records")


def load_csv_records_from_upload(file_storage) -> list[dict[str, Any]]:
    if file_storage is None:
        logger.debug("No CSV upload provided")
        return []

    raw_bytes = file_storage.read()
    file_storage.stream.seek(0)
    if not raw_bytes:
        logger.warning("Uploaded CSV file is empty filename=%s", getattr(file_storage, "filename", ""))
        return []

    text = raw_bytes.decode("utf-8-sig")
    dataframe = pd.read_csv(io.StringIO(text))
    if "timestamp" in dataframe.columns:
        parsed = pd.to_datetime(dataframe["timestamp"], errors="coerce")
        dataframe["timestamp"] = parsed.dt.strftime("%Y-%m-%dT%H:%M:%S")

    dataframe = dataframe.fillna("")
    logger.info(
        "Loaded uploaded CSV filename=%s rows=%s",
        getattr(file_storage, "filename", ""),
        len(dataframe),
    )
    return dataframe.to_dict(orient="records")


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        logger.error("JSON file not found path=%s", path)
        raise ValueError(f"JSON file not found: {path}")

    logger.info("Loading JSON file path=%s", path)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_json_from_upload(file_storage) -> dict[str, Any]:
    if file_storage is None:
        logger.debug("No JSON upload provided")
        return {}

    raw_bytes = file_storage.read()
    file_storage.stream.seek(0)
    if not raw_bytes:
        logger.warning("Uploaded JSON file is empty filename=%s", getattr(file_storage, "filename", ""))
        return {}

    text = raw_bytes.decode("utf-8-sig")
    data = json.loads(text)
    if not isinstance(data, dict):
        logger.error("Uploaded JSON payload is not an object filename=%s", getattr(file_storage, "filename", ""))
        raise ValueError("Uploaded incident ticket JSON must be an object.")
    logger.info("Loaded uploaded JSON filename=%s", getattr(file_storage, "filename", ""))
    return data


def sort_records_by_timestamp(
    records: list[dict[str, Any]],
    timestamp_key: str = "timestamp",
) -> list[dict[str, Any]]:
    def _key(record: dict[str, Any]) -> str:
        return str(record.get(timestamp_key, ""))

    return sorted(records, key=_key)
