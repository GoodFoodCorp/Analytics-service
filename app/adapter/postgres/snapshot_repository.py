"""Snapshot cache — implements domain.ports.SnapshotRepository."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import asyncpg

from app.domain.metrics import DayPoint, Metrics, RestaurantBreakdown, TopDish


class SnapshotRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_fresh(self, scope_key: str, max_age_seconds: int) -> Metrics | None:
        row = await self._pool.fetchrow(
            """
            SELECT payload, computed_at FROM metric_snapshots
            WHERE scope_key = $1 AND computed_at > now() - make_interval(secs => $2)
            """,
            scope_key,
            max_age_seconds,
        )
        if row is None:
            return None
        return _from_payload(json.loads(row["payload"]))

    async def save(self, scope_key: str, metrics: Metrics) -> None:
        await self._pool.execute(
            """
            INSERT INTO metric_snapshots (scope_key, payload, computed_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (scope_key) DO UPDATE
              SET payload = EXCLUDED.payload, computed_at = EXCLUDED.computed_at
            """,
            scope_key,
            json.dumps(_to_payload(metrics)),
            metrics.computed_at,
        )


def _to_payload(metrics: Metrics) -> dict:
    return {
        "period_days": metrics.period_days,
        "revenue_cents": metrics.revenue_cents,
        "orders_count": metrics.orders_count,
        "cancelled_count": metrics.cancelled_count,
        "average_basket_cents": metrics.average_basket_cents,
        "orders_by_status": metrics.orders_by_status,
        "revenue_by_day": [
            {"day": point.day.isoformat(), "revenue_cents": point.revenue_cents, "orders_count": point.orders_count}
            for point in metrics.revenue_by_day
        ],
        "top_dishes": [
            {
                "menu_item_id": dish.menu_item_id,
                "name": dish.name,
                "quantity": dish.quantity,
                "revenue_cents": dish.revenue_cents,
            }
            for dish in metrics.top_dishes
        ],
        "top_restaurants": [
            {
                "restaurant_id": entry.restaurant_id,
                "name": entry.name,
                "revenue_cents": entry.revenue_cents,
                "orders_count": entry.orders_count,
            }
            for entry in metrics.top_restaurants
        ],
        "computed_at": metrics.computed_at.isoformat(),
        "restaurant_id": metrics.restaurant_id,
        "restaurant_name": metrics.restaurant_name,
    }


def _from_payload(payload: dict) -> Metrics:
    return Metrics(
        period_days=payload["period_days"],
        revenue_cents=payload["revenue_cents"],
        orders_count=payload["orders_count"],
        cancelled_count=payload["cancelled_count"],
        average_basket_cents=payload["average_basket_cents"],
        orders_by_status=payload["orders_by_status"],
        revenue_by_day=[
            DayPoint(
                day=date.fromisoformat(point["day"]),
                revenue_cents=point["revenue_cents"],
                orders_count=point["orders_count"],
            )
            for point in payload["revenue_by_day"]
        ],
        top_dishes=[
            TopDish(
                menu_item_id=dish["menu_item_id"],
                name=dish["name"],
                quantity=dish["quantity"],
                revenue_cents=dish["revenue_cents"],
            )
            for dish in payload["top_dishes"]
        ],
        top_restaurants=[
            RestaurantBreakdown(
                restaurant_id=entry["restaurant_id"],
                name=entry["name"],
                revenue_cents=entry["revenue_cents"],
                orders_count=entry["orders_count"],
            )
            for entry in payload["top_restaurants"]
        ],
        computed_at=_parse_datetime(payload["computed_at"]),
        restaurant_id=payload.get("restaurant_id"),
        restaurant_name=payload.get("restaurant_name"),
    )


def _parse_datetime(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
