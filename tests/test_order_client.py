"""order-service client: walks every page of a restaurant's orders."""

from __future__ import annotations

import httpx
import pytest

from app.adapter.clients import orders as orders_module
from app.adapter.clients.orders import OrderClient


def order(i: int) -> dict:
    return {
        "id": f"o{i}",
        "restaurant_id": "r1",
        "status": "DELIVERED",
        "total_amount_cents": 1000,
        "placed_at": "2026-10-10T12:00:00Z",
        "items": [],
    }


@pytest.mark.asyncio
async def test_follows_next_offset_until_the_last_page(monkeypatch):
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        calls.append(dict(request.url.params))
        if offset == 0:
            return httpx.Response(200, json=[order(1), order(2)], headers={"X-Next-Offset": "2"})
        return httpx.Response(200, json=[order(3)])

    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(orders_module.httpx, "AsyncClient", fake_client)

    result = await OrderClient("http://order").list_by_restaurant("r1", "tok")

    assert [o.id for o in result] == ["o1", "o2", "o3"]
    assert [c["offset"] for c in calls] == ["0", "2"]
    assert calls[0]["limit"] == "200"


@pytest.mark.asyncio
async def test_a_forbidden_restaurant_contributes_nothing(monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        orders_module.httpx,
        "AsyncClient",
        lambda *a, **k: real_client(*a, transport=httpx.MockTransport(lambda r: httpx.Response(403)), **k),
    )
    assert await OrderClient("http://order").list_by_restaurant("r1", "tok") == []
