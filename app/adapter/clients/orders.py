"""order-service client — implements domain.ports.OrderSource.

The caller's own JWT is forwarded rather than a service account, so
order-service applies its usual authorization (a manager only ever gets their
own restaurant back).
"""

from __future__ import annotations

from datetime import datetime

import httpx

from app.domain.errors import DomainError
from app.domain.metrics import Order, OrderItem


class OrderClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def list_by_restaurant(self, restaurant_id: str, token: str) -> list[Order]:
        url = f"{self._base_url}/api/orders"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    url,
                    params={"restaurantId": restaurant_id},
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as exc:
            raise DomainError.upstream(f"order-service unreachable: {exc}") from exc

        # A restaurant the caller may not read is not an analytics failure —
        # it simply contributes nothing to the aggregate.
        if response.status_code == 403:
            return []
        if response.status_code >= 400:
            raise DomainError.upstream(f"order-service returned {response.status_code}")

        return [_to_order(payload) for payload in response.json()]


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
