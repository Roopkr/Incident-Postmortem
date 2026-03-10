import logging
from backend.preprocessing.parser import load_csv_records_from_upload, load_json_from_upload
from flask import Blueprint, jsonify, request
from backend.services.incident_service import IncidentService


api_bp = Blueprint("api", __name__)
logger = logging.getLogger(__name__)

@api_bp.get("/health")
def health() -> tuple:
    return jsonify({"status": "ok", "service": "ai-incident-postmortem"}), 200


@api_bp.route("/api/incidents/reconstruct", methods=["POST", "OPTIONS"])
def reconstruct_incident() -> tuple:
    if request.method == "OPTIONS":
        return "", 204

    content_type = request.content_type or ""
    payload = request.get_json(silent=True) or {}
    if "multipart/form-data" in content_type:
        try:
            logs = load_csv_records_from_upload(request.files.get("logs_file"))
            alerts = load_csv_records_from_upload(request.files.get("alerts_file"))
            deployments = load_csv_records_from_upload(request.files.get("deployments_file"))
            incident_ticket = load_json_from_upload(request.files.get("ticket_file"))

            payload = {}
            if logs:
                payload["logs"] = logs
            if alerts:
                payload["alerts"] = alerts
            if deployments:
                payload["deployments"] = deployments
            if incident_ticket:
                payload["incident_ticket"] = incident_ticket
        except Exception as exc:
            logger.warning("multipart upload parsing failed error=%s", exc)
            return jsonify({"error": f"Failed to parse uploaded files: {exc}"}), 400

    logger.info(
        "reconstruct_incident request received logs=%s alerts=%s deployments=%s has_ticket=%s",
        len(payload.get("logs", [])) if isinstance(payload.get("logs"), list) else "default",
        len(payload.get("alerts", [])) if isinstance(payload.get("alerts"), list) else "default",
        len(payload.get("deployments", []))
        if isinstance(payload.get("deployments"), list)
        else "default",
        isinstance(payload.get("incident_ticket"), dict),
    )

    try:
        incident_service = IncidentService()
        result = incident_service.reconstruct_incident(payload)
        logger.info(
            "reconstruct_incident success timeline_events=%s confidence=%s",
            len(result.get("timeline", [])),
            result.get("confidence"),
        )
        return jsonify(result), 200
    except ValueError as exc:
        logger.warning("reconstruct_incident bad_request error=%s", exc)
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("reconstruct_incident unexpected error=%s", exc)
        return jsonify(
            {
                "error": "Unexpected server error while reconstructing incident.",
                "details": str(exc),
            }
        ), 500
