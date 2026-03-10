import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

INJECTION_PATTERNS = [
    r"ignore\s+previous\s+instructions",
    r"disregard\s+all\s+rules",
    r"you\s+are\s+chatgpt",
    r"system\s*:",
    r"assistant\s*:",
    r"<script.*?>.*?</script>",
]


def sanitize_text(text: str) -> str:
    cleaned = text
    for pattern in INJECTION_PATTERNS:
        cleaned = re.sub(pattern, "[redacted]", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def sanitize_log_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized_records: list[dict[str, Any]] = []
    redaction_count = 0
    for record in records:
        row = dict(record)
        original = str(row.get("message", ""))
        sanitized = sanitize_text(original)
        if sanitized != original.strip():
            redaction_count += 1
        row["message"] = sanitized
        sanitized_records.append(row)
    if redaction_count:
        logger.info("Sanitized log records redactions=%s total=%s", redaction_count, len(records))
    return sanitized_records
