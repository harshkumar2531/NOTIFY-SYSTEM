from arq import create_pool
from arq.connections import RedisSettings
from app.config import settings

def redis_settings() -> RedisSettings:
    """Build ARQ's Redis connection from your existing REDIS_URL.

    Works for both dev (redis://localhost:6379/0) and in-container
    (redis://redis:6379/0) — ARQ parses the DSN either way.
    """
    return RedisSettings.from_dsn(settings.REDIS_URL)

async def get_arq_pool():
    """Open an ARQ connection pool (called once at startup in main.py)."""
    return await create_pool(redis_settings())

