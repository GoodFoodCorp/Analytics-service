"""Request id, structured logging, and JWT authentication.

Same contract as every other service: HS256, shared JWT_SECRET, claims
`sub` / `tenant_id` / `role_slugs`. Validation is local — no call back to
auth-service.
"""

from __future__ import annotations

import logging
import time
import uuid

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

from app.application.actor import Actor
from app.config import Settings, get_settings

HEADER_REQUEST_ID = "X-Request-ID"

logger = logging.getLogger("analytics")
bearer_scheme = HTTPBearer(auto_error=False)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Propagates the correlation id and emits one structured log line per
    request, mirroring the zerolog output of the Go services."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(HEADER_REQUEST_ID) or str(uuid.uuid4())
        request.state.request_id = request_id

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000

        response.headers[HEADER_REQUEST_ID] = request_id
        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 3),
            },
        )
        return response


def current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> Actor:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

    token = credentials.credentials
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token") from exc

    return Actor(
        user_id=claims.get("sub", ""),
        tenant_id=claims.get("tenant_id") or "",
        role_slugs=tuple(claims.get("role_slugs") or []),
        token=token,
    )
