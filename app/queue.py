from arq import create_pool
from arq.connections import RedisSettings
from app.config import settings

def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.REDIS_URL)

async def get_arq_pool():
    return await create_pool(redis_settings())

