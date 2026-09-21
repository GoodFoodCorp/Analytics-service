"""JWT middleware tests — the shared auth contract with the other services."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.adapter.http.middleware import current_actor
from app.config import Settings

SECRET = "test-secret"

settings = Settings(
    port=8091,
    log_level="info",
    database_url="postgres://x/y",
    jwt_secret=SECRET,
    order_service_url="http://order",
    franchise_service_url="http://franchise",
    cache_ttl_seconds=60,
)


def make_token(claims: dict, secret: str = SECRET) -> HTTPAuthorizationCredentials:
    payload = {"exp": datetime.now(UTC) + timedelta(minutes=15), **claims}
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=jwt.encode(payload, secret, algorithm="HS256"))


def test_claims_are_mapped_onto_the_actor():
    actor = current_actor(
        make_token({"sub": "u1", "tenant_id": "resto-a", "role_slugs": ["manager"]}),
        settings,
    )

    assert actor.user_id == "u1"
    assert actor.tenant_id == "resto-a"
    assert actor.is_manager
    assert not actor.is_admin


def test_a_customer_token_carries_no_tenant():
    actor = current_actor(make_token({"sub": "u2", "tenant_id": "", "role_slugs": ["user"]}), settings)
    assert actor.tenant_id == ""
    assert not actor.is_manager


def test_missing_token_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        current_actor(None, settings)
    assert excinfo.value.status_code == 401


def test_token_signed_with_another_secret_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        current_actor(make_token({"sub": "u1"}, secret="wrong-secret"), settings)
    assert excinfo.value.status_code == 401


def test_expired_token_is_rejected():
    expired = jwt.encode(
        {"sub": "u1", "exp": datetime.now(UTC) - timedelta(minutes=1)}, SECRET, algorithm="HS256"
    )
    with pytest.raises(HTTPException) as excinfo:
        current_actor(HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired), settings)
    assert excinfo.value.status_code == 401
