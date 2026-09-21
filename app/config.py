"""Typed configuration from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    port: int
    log_level: str
    database_url: str
    jwt_secret: str
    order_service_url: str
    franchise_service_url: str
    cache_ttl_seconds: int


@lru_cache
def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "")
    jwt_secret = os.getenv("JWT_SECRET", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    if not jwt_secret:
        raise RuntimeError("JWT_SECRET is required")

    return Settings(
        port=int(os.getenv("PORT", "8091")),
        log_level=os.getenv("LOG_LEVEL", "info"),
        database_url=database_url,
        jwt_secret=jwt_secret,
        order_service_url=os.getenv("ORDER_SERVICE_URL", "http://localhost:8082"),
        franchise_service_url=os.getenv("FRANCHISE_SERVICE_URL", "http://localhost:8089"),
        cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "60")),
    )
