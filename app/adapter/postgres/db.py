"""Connection pool and a minimal migration runner.

The Go services use golang-migrate with embedded SQL; the equivalent here is
small enough to keep in-house rather than pull in a migration framework.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

logger = logging.getLogger(__name__)


async def connect(database_url: str, attempts: int = 15, delay_seconds: float = 2.0) -> asyncpg.Pool:
    """Postgres usually needs a few seconds more than the app container."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=10)
        except (OSError, asyncpg.PostgresError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            logger.warning("database not ready (attempt %s/%s), retrying in %ss", attempt, attempts, delay_seconds)
            await asyncio.sleep(delay_seconds)
    raise RuntimeError(f"database unreachable after {attempts} attempts: {last_error}")


async def migrate(pool: asyncpg.Pool) -> None:
    """Applies every .sql file in order, once."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        applied = {row["version"] for row in await conn.fetch("SELECT version FROM schema_migrations")}

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            async with conn.transaction():
                await conn.execute(path.read_text(encoding="utf-8"))
                await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", path.name)
            logger.info("applied migration %s", path.name)


async def ping(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
