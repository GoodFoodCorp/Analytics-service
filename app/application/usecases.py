"""Use cases — one per dashboard. All business rules live here.

Authorization is enforced twice on purpose: once here (a manager may only ask
for their own restaurant) and once upstream, since every call to order-service
forwards the caller's own JWT rather than a service account.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.application.actor import Actor
from app.domain import metrics as domain
from app.domain.errors import DomainError
from app.domain.metrics import Metrics
from app.domain.ports import OrderSource, RestaurantSource, SnapshotRepository

MAX_PERIOD_DAYS = 365


class UseCases:
    def __init__(
        self,
        orders: OrderSource,
        restaurants: RestaurantSource,
        snapshots: SnapshotRepository,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self._orders = orders
        self._restaurants = restaurants
        self._snapshots = snapshots
        self._cache_ttl_seconds = cache_ttl_seconds

    async def network_overview(self, actor: Actor, period_days: int) -> Metrics:
        """Head-office view: every restaurant of the network."""
        if not actor.is_admin:
            raise DomainError.forbidden("only head office can read network analytics")
        period_days = _validate_period(period_days)

        cached = await self._snapshots.get_fresh("network", self._cache_ttl_seconds)
        if cached is not None:
            return cached

        names = await self._restaurants.list_restaurants(actor.token)
        orders = await self._collect_orders(list(names), actor.token)

        computed = domain.compute(orders, period_days, _now(), restaurant_names=names)
        await self._snapshots.save("network", computed)
        return computed

    async def restaurant_overview(self, actor: Actor, period_days: int, restaurant_id: str | None = None) -> Metrics:
        """Franchisee view: a single restaurant. A manager is confined to their
        own tenant; head office may inspect any restaurant."""
        period_days = _validate_period(period_days)
        target = self._resolve_restaurant(actor, restaurant_id)

        scope_key = f"restaurant:{target}"
        cached = await self._snapshots.get_fresh(scope_key, self._cache_ttl_seconds)
        if cached is not None:
            return cached

        names = await self._restaurants.list_restaurants(actor.token)
        orders = await self._orders.list_by_restaurant(target, actor.token)

        computed = domain.compute(
            orders,
            period_days,
            _now(),
            restaurant_names=names,
            restaurant_id=target,
        )
        await self._snapshots.save(scope_key, computed)
        return computed

    def _resolve_restaurant(self, actor: Actor, restaurant_id: str | None) -> str:
        if actor.is_admin:
            if not restaurant_id:
                raise DomainError.validation("restaurantId is required for head office")
            return restaurant_id
        if not actor.is_manager:
            raise DomainError.forbidden("only a restaurant manager can read these analytics")
        if not actor.tenant_id:
            raise DomainError.forbidden("your account is not linked to a restaurant")
        if restaurant_id and restaurant_id != actor.tenant_id:
            raise DomainError.forbidden("you can only read your own restaurant's analytics")
        return actor.tenant_id

    async def _collect_orders(self, restaurant_ids: list[str], token: str) -> list[domain.Order]:
        """Fan out across restaurants — order-service owns the data and has no
        network-wide endpoint, so the aggregate is built here."""
        if not restaurant_ids:
            return []
        batches = await asyncio.gather(
            *(self._orders.list_by_restaurant(restaurant_id, token) for restaurant_id in restaurant_ids)
        )
        return [order for batch in batches for order in batch]


def _validate_period(period_days: int) -> int:
    if period_days < 1 or period_days > MAX_PERIOD_DAYS:
        raise DomainError.validation(f"days must be between 1 and {MAX_PERIOD_DAYS}")
    return period_days


def _now() -> datetime:
    return datetime.now(UTC)
