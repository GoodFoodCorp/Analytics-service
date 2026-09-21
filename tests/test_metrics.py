"""Domain tests — pure aggregation, no HTTP and no database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.metrics import Order, OrderItem, compute

NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)
RESTO_A = "resto-a"
RESTO_B = "resto-b"
NAMES = {RESTO_A: "Good Food République", RESTO_B: "Good Food Montparnasse"}


def order(
    *,
    restaurant_id: str = RESTO_A,
    status: str = "DELIVERED",
    total: int = 2000,
    days_ago: int = 0,
    items: tuple[OrderItem, ...] = (),
    order_id: str = "o1",
) -> Order:
    return Order(
        id=order_id,
        restaurant_id=restaurant_id,
        status=status,
        total_amount_cents=total,
        placed_at=NOW - timedelta(days=days_ago),
        items=items,
    )


def test_revenue_excludes_cancelled_orders_but_still_counts_them():
    metrics = compute(
        [order(total=1000), order(total=3000), order(total=5000, status="CANCELLED")],
        period_days=30,
        now=NOW,
        restaurant_names=NAMES,
    )

    assert metrics.revenue_cents == 4000
    assert metrics.orders_count == 3
    assert metrics.cancelled_count == 1
    assert metrics.average_basket_cents == 2000  # 4000 / 2 billable orders


def test_average_basket_is_zero_without_billable_orders():
    metrics = compute([order(status="CANCELLED")], period_days=7, now=NOW)
    assert metrics.average_basket_cents == 0
    assert metrics.revenue_cents == 0


def test_orders_outside_the_window_are_ignored():
    metrics = compute(
        [order(total=1000, days_ago=2), order(total=9999, days_ago=40)],
        period_days=7,
        now=NOW,
    )
    assert metrics.revenue_cents == 1000
    assert metrics.orders_count == 1


def test_revenue_by_day_covers_every_day_including_empty_ones():
    metrics = compute([order(total=1500, days_ago=1)], period_days=5, now=NOW)

    assert len(metrics.revenue_by_day) == 5
    assert [p.day for p in metrics.revenue_by_day] == sorted(p.day for p in metrics.revenue_by_day)
    assert metrics.revenue_by_day[-1].day == NOW.date()
    assert sum(p.revenue_cents for p in metrics.revenue_by_day) == 1500
    assert any(p.revenue_cents == 0 for p in metrics.revenue_by_day)


def test_top_dishes_ranked_by_quantity():
    burger = OrderItem(menu_item_id="d1", name="Burger", quantity=2, unit_price_cents=1200)
    pizza = OrderItem(menu_item_id="d2", name="Pizza", quantity=5, unit_price_cents=1400)

    metrics = compute(
        [order(order_id="o1", items=(burger,)), order(order_id="o2", items=(pizza, burger))],
        period_days=30,
        now=NOW,
    )

    assert [d.name for d in metrics.top_dishes] == ["Pizza", "Burger"]
    assert metrics.top_dishes[0].quantity == 5
    assert metrics.top_dishes[0].revenue_cents == 7000
    assert metrics.top_dishes[1].quantity == 4


def test_cancelled_orders_never_feed_the_rankings():
    dish = OrderItem(menu_item_id="d1", name="Burger", quantity=3, unit_price_cents=1000)
    metrics = compute([order(status="CANCELLED", items=(dish,))], period_days=30, now=NOW)

    assert metrics.top_dishes == []
    assert metrics.top_restaurants == []


def test_top_restaurants_use_the_franchise_directory_names():
    metrics = compute(
        [
            order(restaurant_id=RESTO_A, total=1000, order_id="o1"),
            order(restaurant_id=RESTO_B, total=4000, order_id="o2"),
            order(restaurant_id=RESTO_B, total=1000, order_id="o3"),
        ],
        period_days=30,
        now=NOW,
        restaurant_names=NAMES,
    )

    assert [r.name for r in metrics.top_restaurants] == ["Good Food Montparnasse", "Good Food République"]
    assert metrics.top_restaurants[0].revenue_cents == 5000
    assert metrics.top_restaurants[0].orders_count == 2


def test_unknown_restaurant_id_falls_back_to_a_neutral_label():
    metrics = compute([order(restaurant_id="ghost", total=1000)], period_days=30, now=NOW, restaurant_names={})
    assert metrics.top_restaurants[0].name == "Restaurant"


def test_restaurant_scope_is_reported_back():
    metrics = compute([], period_days=30, now=NOW, restaurant_names=NAMES, restaurant_id=RESTO_A)
    assert metrics.restaurant_id == RESTO_A
    assert metrics.restaurant_name == "Good Food République"


def test_orders_by_status_breakdown():
    metrics = compute(
        [
            order(status="DELIVERED", order_id="o1"),
            order(status="DELIVERED", order_id="o2"),
            order(status="IN_DELIVERY", order_id="o3"),
        ],
        period_days=30,
        now=NOW,
    )
    assert metrics.orders_by_status == {"DELIVERED": 2, "IN_DELIVERY": 1}
