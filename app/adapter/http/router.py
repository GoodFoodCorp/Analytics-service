"""Routes — decode, delegate to the use cases, encode. No business logic."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.adapter.http.dto import MetricsResponse, to_response
from app.adapter.http.middleware import current_actor
from app.application.actor import Actor
from app.application.usecases import UseCases

DEFAULT_PERIOD_DAYS = 30


def build_router(use_cases_provider) -> APIRouter:
    """`use_cases_provider` is a callable returning the wired UseCases — the
    app builds it once at startup (see main.py)."""
    router = APIRouter(prefix="/api/analytics", tags=["analytics"])

    @router.get("/network", response_model=MetricsResponse, summary="Network-wide KPIs (head office)")
    async def network(
        days: int = Query(DEFAULT_PERIOD_DAYS, ge=1, le=365),
        actor: Actor = Depends(current_actor),
    ) -> MetricsResponse:
        use_cases: UseCases = use_cases_provider()
        return to_response(await use_cases.network_overview(actor, days))

    @router.get("/restaurant", response_model=MetricsResponse, summary="One restaurant's KPIs (franchisee)")
    async def restaurant(
        days: int = Query(DEFAULT_PERIOD_DAYS, ge=1, le=365),
        restaurantId: str | None = Query(None, description="Head office only; a manager always gets their own"),
        actor: Actor = Depends(current_actor),
    ) -> MetricsResponse:
        use_cases: UseCases = use_cases_provider()
        return to_response(await use_cases.restaurant_overview(actor, days, restaurantId))

    return router


def build_health_router(ping_database) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/healthz", summary="Liveness")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/readyz", summary="Readiness (database reachable)")
    async def readyz() -> JSONResponse:
        try:
            await ping_database()
        except Exception:  # noqa: BLE001 — any failure means "not ready"
            return JSONResponse(status_code=503, content={"status": "db unavailable"})
        return JSONResponse(status_code=200, content={"status": "ready"})

    return router
