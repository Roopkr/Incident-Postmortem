import logging

from backend.app import app
import serverless_wsgi

logger = logging.getLogger(__name__)
logger.info("Initialaizing handler")


def handler(event, context):
    return serverless_wsgi.handle_request(app, event, context)
