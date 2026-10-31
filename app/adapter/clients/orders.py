"""order-service client — implements domain.ports.OrderSource.

Reads a restaurant's sales through order-service's internal API (service
key): amounts, statuses and dishes, never the customers. Who may see which
figures is decided by the use cases; head office has no access to the orders
themselves.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from app.domain.errors import DomainError
from app.domain.metrics import Order, OrderItem

# order-service pages its lists; analytics walks every page (200 is its max).
PAGE_SIZE = 200
# Safety bound: 100 pages = 20 000 orders per restaurant per computation.
MAX_PAGES = 100


class OrderClient:
    def __init__(self, base_url: str, service_key: str, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_key = service_key
        self._timeout = timeout_seconds

    async def list_by_restaurant(self, restaurant_id: str) -> list[Order]:
        """Every sale of the restaurant, following order-service's pages
        (X-Next-Offset) until the last one."""
        url = f"{self._base_url}/internal/orders/sales"
        orders: list[Order] = []
        offset = 0
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for _ in range(MAX_PAGES):
                try:
                    response = await client.get(
                        url,
                        params={"restaurantId": restaurant_id, "limit": PAGE_SIZE, "offset": offset},
                        headers={"X-Service-Key": self._service_key},
                    )
                except httpx.HTTPError as exc:
                    raise DomainError.upstream(f"order-service unreachable: {exc}") from exc

                if response.status_code >= 400:
                    raise DomainError.upstream(f"order-service returned {response.status_code}")

                orders.extend(_to_order(payload) for payload in response.json())
                next_offset = response.headers.get("X-Next-Offset")
                if not next_offset:
                    break
                offset = int(next_offset)
        return orders


def _to_order(payload: dict) -> Order:
    return Order(
        id=payload["id"],
        restaurant_id=payload["restaurant_id"],
        status=payload["status"],
        total_amount_cents=payload["total_amount_cents"],
        placed_at=_parse_timestamp(payload["placed_at"]),
        items=tuple(
            OrderItem(
                menu_item_id=item["menu_item_id"],
                name=item["menu_item_name"],
                quantity=item["quantity"],
                unit_price_cents=item["unit_price_cents"],
            )
            for item in payload.get("items", [])
        ),
    )


def _parse_timestamp(raw: str) -> datetime:
    """Go marshals RFC 3339 with a trailing Z, which fromisoformat only accepts
    from Python 3.11 — normalised here to stay explicit."""
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))
