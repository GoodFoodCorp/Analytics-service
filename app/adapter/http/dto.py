"""Response models. Snake_case on the wire, like the Go services."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.domain.metrics import Metrics


class DayPointResponse(BaseModel):
    day: date
    revenue_cents: int
    orders_count: int


class TopDishResponse(BaseModel):
    menu_item_id: str
    name: str
    quantity: int
    revenue_cents: int


class RestaurantBreakdownResponse(BaseModel):
    restaurant_id: str
    name: str
    revenue_cents: int
    orders_count: int


class MetricsResponse(BaseModel):
    period_days: int
    revenue_cents: int
    orders_count: int
    cancelled_count: int
    average_basket_cents: int
    orders_by_status: dict[str, int]
    revenue_by_day: list[DayPointResponse]
    top_dishes: list[TopDishResponse]
    top_restaurants: list[RestaurantBreakdownResponse]
    computed_at: datetime
    restaurant_id: str | None = None
    restaurant_name: str | None = None


class ErrorResponse(BaseModel):
    error: str
    request_id: str | None = None


def to_response(metrics: Metrics) -> MetricsResponse:
    return MetricsResponse(
        period_days=metrics.period_days,
        revenue_cents=metrics.revenue_cents,
        orders_count=metrics.orders_count,
        cancelled_count=metrics.cancelled_count,
        average_basket_cents=metrics.average_basket_cents,
        orders_by_status=metrics.orders_by_status,
        revenue_by_day=[
            DayPointResponse(day=p.day, revenue_cents=p.revenue_cents, orders_count=p.orders_count)
            for p in metrics.revenue_by_day
        ],
        top_dishes=[
            TopDishResponse(
                menu_item_id=d.menu_item_id, name=d.name, quantity=d.quantity, revenue_cents=d.revenue_cents
            )
            for d in metrics.top_dishes
        ],
        top_restaurants=[
            RestaurantBreakdownResponse(
                restaurant_id=r.restaurant_id,
                name=r.name,
                revenue_cents=r.revenue_cents,
                orders_count=r.orders_count,
            )
            for r in metrics.top_restaurants
        ],
        computed_at=metrics.computed_at,
        restaurant_id=metrics.restaurant_id,
        restaurant_name=metrics.restaurant_name,
    )
