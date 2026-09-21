"""Outbound ports — implemented by the adapter layer (HTTP clients, Postgres)."""

from __future__ import annotations

from typing import Protocol

from app.domain.metrics import Metrics, Order


class OrderSource(Protocol):
    """Reads orders from order-service, which owns them."""

    async def list_by_restaurant(self, restaurant_id: str, token: str) -> list[Order]: ...


class RestaurantSource(Protocol):
    """Reads the restaurant directory from franchise-service."""

    async def list_restaurants(self, token: str) -> dict[str, str]:
        """Returns {restaurant_id: name}."""
        ...


class SnapshotRepository(Protocol):
    """Caches a computed KPI set so repeated dashboard loads don't re-fan-out
    to every upstream service."""

    async def get_fresh(self, scope_key: str, max_age_seconds: int) -> Metrics | None: ...

    async def save(self, scope_key: str, metrics: Metrics) -> None: ...
