"""franchise-service client — implements domain.ports.RestaurantSource.

Only used to turn restaurant ids into readable names: this service never
stores the directory, franchise-service owns it.
"""

from __future__ import annotations

import httpx

from app.domain.errors import DomainError


class RestaurantClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def list_restaurants(self, token: str) -> dict[str, str]:
        url = f"{self._base_url}/api/restaurants"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as exc:
            raise DomainError.upstream(f"franchise-service unreachable: {exc}") from exc

        if response.status_code >= 400:
            raise DomainError.upstream(f"franchise-service returned {response.status_code}")

        # franchise-service is ASP.NET Core: camelCase payload.
        return {item["id"]: item["name"] for item in response.json()}
