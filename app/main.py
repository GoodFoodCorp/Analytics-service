"""Startup: migrations, dependency wiring, HTTP server.

Equivalent of cmd/main.go in the Go services.
"""

from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.adapter.clients.orders import OrderClient
from app.adapter.clients.restaurants import RestaurantClient
from app.adapter.http.middleware import RequestContextMiddleware
from app.adapter.http.router import build_health_router, build_router
from app.adapter.postgres import db
from app.adapter.postgres.snapshot_repository import SnapshotRepository
from app.application.usecases import UseCases
from app.config import get_settings
from app.domain.errors import DomainError, ErrorCode

STATUS_BY_CODE = {
    ErrorCode.VALIDATION: 400,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.UPSTREAM: 502,
}


class JsonLogFormatter(logging.Formatter):
    """One structured JSON line per event, like zerolog in the Go services."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname.lower(),
            "service": "analytics-service",
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger("analytics")

    state: dict[str, object] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        pool = await db.connect(settings.database_url)
        await db.migrate(pool)
        logger.info("migrations applied")

        state["pool"] = pool
        state["use_cases"] = UseCases(
            orders=OrderClient(settings.order_service_url),
            restaurants=RestaurantClient(settings.franchise_service_url),
            snapshots=SnapshotRepository(pool),
            cache_ttl_seconds=settings.cache_ttl_seconds,
        )
        logger.info("analytics-service started on port %s", settings.port)
        yield
        await pool.close()

    app = FastAPI(
        title="Analytics Service API",
        version="0.1.0",
        description=(
            "Aggregates the KPIs of the Good Food network. Owns no business data: "
            "it reads what order-service and franchise-service expose, forwarding "
            "the caller's own JWT."
        ),
        docs_url="/docs",
        openapi_url="/docs/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=STATUS_BY_CODE.get(exc.code, 500),
            content={"error": exc.message, "request_id": getattr(request.state, "request_id", None)},
        )

    async def ping_database() -> None:
        await db.ping(state["pool"])  # type: ignore[arg-type]

    app.include_router(build_health_router(ping_database))
    app.include_router(build_router(lambda: state["use_cases"]))
    return app


app = create_app()
