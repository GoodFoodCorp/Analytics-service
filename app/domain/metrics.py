"""Pure aggregation domain — no HTTP, no database, no framework.

Everything here works on plain value objects so the whole KPI computation is
unit-testable in isolation, the same way the Go services keep their domain
layer free of adapters.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

#: An order in this status never counts towards revenue.
CANCELLED = "CANCELLED"

#: How many entries the "top" rankings keep.
TOP_LIMIT = 5


@dataclass(frozen=True)
class OrderItem:
    menu_item_id: str
    name: str
    quantity: int
    unit_price_cents: int

    @property
    def line_total_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass(frozen=True)
class Order:
    id: str
    restaurant_id: str
    status: str
    total_amount_cents: int
    placed_at: datetime
    items: tuple[OrderItem, ...] = ()

    @property
    def is_cancelled(self) -> bool:
        return self.status == CANCELLED


@dataclass(frozen=True)
class DayPoint:
    day: date
    revenue_cents: int
    orders_count: int


@dataclass(frozen=True)
class TopDish:
    menu_item_id: str
    name: str
    quantity: int
    revenue_cents: int


@dataclass(frozen=True)
class RestaurantBreakdown:
    restaurant_id: str
    name: str
    revenue_cents: int
    orders_count: int


@dataclass(frozen=True)
class Metrics:
    """The KPI set both dashboards read."""

    period_days: int
    revenue_cents: int
    orders_count: int
    cancelled_count: int
    average_basket_cents: int
    orders_by_status: dict[str, int]
    revenue_by_day: list[DayPoint]
    top_dishes: list[TopDish]
    top_restaurants: list[RestaurantBreakdown]
    computed_at: datetime
    restaurant_id: str | None = None
    restaurant_name: str | None = None


def _window_start(now: datetime, period_days: int) -> datetime:
    """Midnight UTC of the first day in the window (inclusive)."""
    midnight = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=period_days - 1)


def in_period(order: Order, now: datetime, period_days: int) -> bool:
    return order.placed_at.astimezone(UTC) >= _window_start(now, period_days)


def compute(
    orders: list[Order],
    period_days: int,
    now: datetime,
    restaurant_names: dict[str, str] | None = None,
    restaurant_id: str | None = None,
) -> Metrics:
    """Aggregate orders into the KPI set.

    Cancelled orders are counted (so the cancellation rate stays visible) but
    never contribute revenue.
    """
    names = restaurant_names or {}
    kept = [o for o in orders if in_period(o, now, period_days)]

    billable = [o for o in kept if not o.is_cancelled]
    revenue_cents = sum(o.total_amount_cents for o in billable)
    cancelled_count = sum(1 for o in kept if o.is_cancelled)
    average_basket_cents = revenue_cents // len(billable) if billable else 0

    orders_by_status: dict[str, int] = defaultdict(int)
    for order in kept:
        orders_by_status[order.status] += 1

    return Metrics(
        period_days=period_days,
        revenue_cents=revenue_cents,
        orders_count=len(kept),
        cancelled_count=cancelled_count,
        average_basket_cents=average_basket_cents,
        orders_by_status=dict(orders_by_status),
        revenue_by_day=_revenue_by_day(billable, kept, now, period_days),
        top_dishes=_top_dishes(billable),
        top_restaurants=_top_restaurants(billable, names),
        computed_at=now.astimezone(UTC),
        restaurant_id=restaurant_id,
        restaurant_name=names.get(restaurant_id) if restaurant_id else None,
    )


def _revenue_by_day(billable: list[Order], kept: list[Order], now: datetime, period_days: int) -> list[DayPoint]:
    """One point per day of the window — including days without a single order,
    so the chart line stays continuous instead of skipping gaps."""
    revenue: dict[date, int] = defaultdict(int)
    counts: dict[date, int] = defaultdict(int)

    for order in billable:
        revenue[order.placed_at.astimezone(UTC).date()] += order.total_amount_cents
    for order in kept:
        counts[order.placed_at.astimezone(UTC).date()] += 1

    first_day = _window_start(now, period_days).date()
    return [
        DayPoint(
            day=first_day + timedelta(days=offset),
            revenue_cents=revenue[first_day + timedelta(days=offset)],
            orders_count=counts[first_day + timedelta(days=offset)],
        )
        for offset in range(period_days)
    ]


def _top_dishes(billable: list[Order]) -> list[TopDish]:
    quantities: dict[str, int] = defaultdict(int)
    revenues: dict[str, int] = defaultdict(int)
    labels: dict[str, str] = {}

    for order in billable:
        for item in order.items:
            quantities[item.menu_item_id] += item.quantity
            revenues[item.menu_item_id] += item.line_total_cents
            labels[item.menu_item_id] = item.name

    ranked = sorted(quantities.items(), key=lambda pair: (-pair[1], labels[pair[0]]))
    return [
        TopDish(
            menu_item_id=item_id,
            name=labels[item_id],
            quantity=quantity,
            revenue_cents=revenues[item_id],
        )
        for item_id, quantity in ranked[:TOP_LIMIT]
    ]


def _top_restaurants(billable: list[Order], names: dict[str, str]) -> list[RestaurantBreakdown]:
    revenues: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)

    for order in billable:
        revenues[order.restaurant_id] += order.total_amount_cents
        counts[order.restaurant_id] += 1

    ranked = sorted(revenues.items(), key=lambda pair: (-pair[1], pair[0]))
    return [
        RestaurantBreakdown(
            restaurant_id=restaurant_id,
            name=names.get(restaurant_id, "Restaurant"),
            revenue_cents=revenue,
            orders_count=counts[restaurant_id],
        )
        for restaurant_id, revenue in ranked[:TOP_LIMIT]
    ]
