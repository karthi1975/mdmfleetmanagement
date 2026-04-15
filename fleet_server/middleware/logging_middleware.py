"""Structured request/response logging (SRP).

Logs every request with timing, status, and request_id for Loki/Grafana.
JSON format for easy parsing by log aggregation tools.
"""

import json
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from fleet_server.middleware.request_id import request_id_var

logger = logging.getLogger("fleet_server.access")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        # Skip health checks from access log noise
        if request.url.path == "/health":
            return response

        log_data = {
            "request_id": request_id_var.get(),
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "client": request.client.host if request.client else None,
        }

        if response.status_code >= 500:
            logger.error(json.dumps(log_data))
        elif response.status_code >= 400:
            logger.warning(json.dumps(log_data))
        else:
            logger.info(json.dumps(log_data))

        return response
