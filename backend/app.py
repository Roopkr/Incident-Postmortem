import logging
import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g, request

from backend.routes import api_bp

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    if not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        load_dotenv()

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    app = Flask(__name__)
    logger.info("App initialized")
    app.logger.setLevel(getattr(logging, log_level, logging.INFO))
    app.register_blueprint(api_bp)

    @app.before_request
    def before_request() -> tuple | None:
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        if request.method == "OPTIONS":
            return "", 204
        return None

    @app.after_request
    def after_request(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "*"
        return response

    @app.errorhandler(Exception)
    def error_handler(exc: Exception):
        app.logger.exception(
            "Unhandled exception request_id=%s method=%s path=%s error=%s",
            getattr(g, "request_id", "-"),
            request.method,
            request.path,
            exc,
        )
        return (
            {"error": "Internal server error", "request_id": getattr(g, "request_id", "")},
            500,
        )

    return app


app = create_app()


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=debug)
