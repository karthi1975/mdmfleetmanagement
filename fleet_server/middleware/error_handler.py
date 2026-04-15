"""Global error handling — catches unhandled exceptions (SRP).

Returns consistent JSON error responses instead of raw 500s.
Logs errors with request context for debugging.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError

from fleet_server.middleware.request_id import request_id_var

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the app (OCP — add new handlers here)."""

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        logger.warning(
            "Database integrity error [%s]: %s",
            request_id_var.get(), str(exc.orig),
        )
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Database constraint violation",
                "request_id": request_id_var.get(),
            },
        )

    @app.exception_handler(OperationalError)
    async def db_operational_error_handler(request: Request, exc: OperationalError):
        logger.error(
            "Database error [%s]: %s",
            request_id_var.get(), str(exc.orig),
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Database unavailable",
                "request_id": request_id_var.get(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception(
            "Unhandled error [%s] %s %s: %s",
            request_id_var.get(), request.method, request.url.path, exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": request_id_var.get(),
            },
        )
