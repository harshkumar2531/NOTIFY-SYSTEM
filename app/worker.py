import logging
import random
from datetime import datetime, timezone
import asyncpg
import redis.asyncio as aioredis
from arq import Retry, cron
from arq.connections import RedisSettings
from bson import ObjectId
from pymongo import AsyncMongoClient
from app import pg_ops, redis_ops
from app.config import settings
from app.email_channel import send_email
from app.mqtt import publish_notification
from app.state import clients

logger = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)

MAX_TRIES = 4

def _notifications():
    return clients["mongo"][settings.MONGO_DB]["notifications"]

async def _dead_letter(
    ctx,
    user_id: str,
    notification: dict,
    error: str,
) -> None:
    coll = ctx["mongo"][settings.MONGO_DB]["dead_letters"]

    await coll.insert_one(
        {
            "task": "deliver_notification",
            "user_id": user_id,
            "notification": notification,
            "error": error,
            "failed_at": datetime.now(timezone.utc),
            "replayed": False,
        }
    )

    logger.error(
        "Dead-lettered notification %s for %s: %s",
        notification.get("id"),
        user_id,
        error,
    )

async def _maybe_email_fallback(
    user_id: str,
    notification: dict,
):
    if await redis_ops.is_online(user_id):
        return

    ntype = notification.get("type", "general")

    if not await pg_ops.is_channel_enabled(
        user_id,
        ntype,
        "email",
    ):
        return

    user = await pg_ops.get_user(user_id)

    if not user:
        return

    if not user.get("email"):
        return

    try:
        await send_email(
            user["email"],
            notification,
        )

        logger.info(
            "Offline fallback email sent to %s",
            user["email"],
        )

    except Exception:
        logger.exception(
            "Failed sending fallback email"
        )

async def deliver_notification(
    ctx,
    user_id: str,
    notification: dict,
) -> str:

    attempt = ctx["job_try"]

    try:
        await publish_notification(
            user_id,
            notification,
        )

    except Exception as e:

        if attempt < MAX_TRIES:

            delay = (2 ** attempt) + random.uniform(0, 1)

            logger.warning(
                "Delivery failed (%s/%s). Retrying in %.2fs",
                attempt,
                MAX_TRIES,
                delay,
            )

            raise Retry(defer=delay)

        await _dead_letter(
            ctx,
            user_id,
            notification,
            str(e),
        )

        raise

    logger.info(
        "Delivered notification %s",
        notification.get("id"),
    )

    nid = notification.get("id")

    if nid:
        try:
            await _notifications().update_one(
                {
                    "_id": ObjectId(nid)
                },
                {
                    "$set": {
                        "status": "delivered"
                    }
                },
            )

        except Exception:
            logger.exception(
                "Failed updating notification status"
            )

    await _maybe_email_fallback(
        user_id,
        notification,
    )

    return "ok"

async def sweep_scheduled(ctx) -> int:

    now = datetime.now(timezone.utc)

    coll = _notifications()

    cursor = coll.find(
        {
            "status": "scheduled",
            "scheduled_for": {
                "$lte": now,
            },
        }
    )

    count = 0

    async for doc in cursor:

        nid = doc["_id"]

        await coll.update_one(
            {
                "_id": nid,
            },
            {
                "$set": {
                    "status": "queued",
                }
            },
        )

        payload = dict(doc)
        payload["id"] = str(payload.pop("_id"))

        await ctx["redis"].enqueue_job(
            "deliver_notification",
            payload["user_id"],
            payload,
        )

        count += 1

    if count:
        logger.info(
            "Re-enqueued %d scheduled notifications",
            count,
        )

    return count

async def startup(ctx):

    try:

        clients["mongo"] = AsyncMongoClient(
            settings.MONGO_URI
        )

        clients["pg"] = await asyncpg.create_pool(
            dsn=settings.POSTGRES_DSN,
            min_size=1,
            max_size=10,
        )

        clients["redis"] = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=10,
            socket_timeout=10,
            health_check_interval=30,
        )

        await clients["redis"].ping()

        ctx["mongo"] = clients["mongo"]

        logger.info("Worker connections opened")

    except Exception:
        logger.exception(
            "Worker startup failed"
        )
        raise

async def shutdown(ctx):

    try:
        if clients.get("pg"):
            await clients["pg"].close()
    except Exception:
        logger.exception(
            "Failed closing PostgreSQL"
        )

    try:
        if clients.get("mongo"):
            clients["mongo"].close()
    except Exception:
        logger.exception(
            "Failed closing MongoDB"
        )

    try:
        if clients.get("redis"):
            await clients["redis"].aclose()
    except Exception:
        logger.exception(
            "Failed closing Redis"
        )

    logger.info("Worker connections closed")

class WorkerSettings:

    functions = [
        deliver_notification,
    ]

    cron_jobs = [
        cron(
            sweep_scheduled,
            minute=set(range(60)),
            run_at_startup=True,
        )
    ]

    redis_settings = RedisSettings(
        host="redis",
        port=6379,
        database=0,
        conn_timeout=30,
    )

    on_startup = startup

    on_shutdown = shutdown

    max_tries = MAX_TRIES