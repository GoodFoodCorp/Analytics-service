"""Use-case tests — authorization and fan-out, with fake adapters."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.actor import Actor
from app.application.usecases import UseCases
from app.domain.errors import DomainError, ErrorCode
from app.domain.metrics import Metrics, Order

RESTO_A = "resto-a"
RESTO_B = "resto-b"

admin = Actor(user_id="adm", role_slugs=("admin",), token="admin-token")
manager_a = Actor(user_id="mgr-a", tenant_id=RESTO_A, role_slugs=("manager",), token="mgr-token")
customer = Actor(user_id="cust", role_slugs=("user",), token="cust-token")


class FakeOrders:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def list_by_restaurant(self, restaurant_id: str, token: str) -> list[Order]:
        self.calls.append(restaurant_id)
        return [
            Order(
                id=f"o-{restaurant_id}",
                restaurant_id=restaurant_id,
                status="DELIVERED",
                total_amount_cents=1000,
                placed_at=datetime.now(UTC),
            )
        ]


class FakeRestaurants:
    async def list_restaurants(self, token: str) -> dict[str, str]:
        return {RESTO_A: "République", RESTO_B: "Montparnasse"}


class FakeSnapshots:
    def __init__(self) -> None:
        self.saved: dict[str, Metrics] = {}
        self.serve_cached = False

    async def get_fresh(self, scope_key: str, max_age_seconds: int) -> Metrics | None:
        return self.saved.get(scope_key) if self.serve_cached else None

    async def save(self, scope_key: str, metrics: Metrics) -> None:
        self.saved[scope_key] = metrics


def setup() -> tuple[UseCases, FakeOrders, FakeSnapshots]:
    orders, snapshots = FakeOrders(), FakeSnapshots()
    return UseCases(orders, FakeRestaurants(), snapshots), orders, snapshots


async def expect_error(coro, code: ErrorCode) -> None:
    with pytest.raises(DomainError) as excinfo:
        await coro
    assert excinfo.value.code == code


@pytest.mark.asyncio
async def test_network_overview_fans_out_to_every_restaurant():
    use_cases, orders, _ = setup()
    metrics = await use_cases.network_overview(admin, 30)

    assert sorted(orders.calls) == [RESTO_A, RESTO_B]
    assert metrics.revenue_cents == 2000
    assert len(metrics.top_restaurants) == 2


@pytest.mark.asyncio
async def test_only_head_office_reads_network_analytics():
    use_cases, _, _ = setup()
    await expect_error(use_cases.network_overview(manager_a, 30), ErrorCode.FORBIDDEN)
    await expect_error(use_cases.network_overview(customer, 30), ErrorCode.FORBIDDEN)


@pytest.mark.asyncio
async def test_manager_gets_their_own_restaurant_without_asking():
    use_cases, orders, _ = setup()
    metrics = await use_cases.restaurant_overview(manager_a, 30)

    assert orders.calls == [RESTO_A]
    assert metrics.restaurant_id == RESTO_A
    assert metrics.restaurant_name == "République"


@pytest.mark.asyncio
async def test_manager_cannot_read_another_restaurant():
    use_cases, _, _ = setup()
    await expect_error(use_cases.restaurant_overview(manager_a, 30, RESTO_B), ErrorCode.FORBIDDEN)


@pytest.mark.asyncio
async def test_customer_has_no_restaurant_analytics():
    use_cases, _, _ = setup()
    await expect_error(use_cases.restaurant_overview(customer, 30), ErrorCode.FORBIDDEN)


@pytest.mark.asyncio
async def test_head_office_must_name_the_restaurant():
    use_cases, _, _ = setup()
    await expect_error(use_cases.restaurant_overview(admin, 30), ErrorCode.VALIDATION)

    metrics = await use_cases.restaurant_overview(admin, 30, RESTO_B)
    assert metrics.restaurant_id == RESTO_B


@pytest.mark.asyncio
async def test_period_is_validated():
    use_cases, _, _ = setup()
    await expect_error(use_cases.network_overview(admin, 0), ErrorCode.VALIDATION)
    await expect_error(use_cases.network_overview(admin, 400), ErrorCode.VALIDATION)


@pytest.mark.asyncio
async def test_a_fresh_snapshot_short_circuits_the_upstream_calls():
    use_cases, orders, snapshots = setup()
    await use_cases.network_overview(admin, 30)
    assert len(orders.calls) == 2

    snapshots.serve_cached = True
    await use_cases.network_overview(admin, 30)
    assert len(orders.calls) == 2, "the cached snapshot should avoid a second fan-out"
