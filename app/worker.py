import logging
import random
from datetime import datetime, timezone

import asyncpg
import redis.asyncio as aioredis
from arq import Retry
from arq.connections import RedisSettings
from pymongo import AsyncMongoClient

from app import pg_ops, redis_ops
from app.config import settings
from app.email_channel import send_email
from app.mqtt import publish_notification
from app.state import clients  # shared pools, populated in startup() below

logger = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)

MAX_TRIES = 4  # total attempts before dead-lettering


async def _dead_letter(ctx, user_id: str, notification: dict, error: str) -> None:
    """Persist a permanently-failed job so it can be inspected / replayed."""
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


async def _maybe_email_fallback(user_id: str, notification: dict) -> None:
    """If the user is OFFLINE and email is enabled for this type, send an email.

    MQTT is the primary channel; email is the offline fallback. We do NOT email
    users who are currently online.
    """
    if await redis_ops.is_online(user_id):
        return  # online → real-time MQTT was enough

    ntype = notification.get("type", "general")
    if not await pg_ops.is_channel_enabled(user_id, ntype, "email"):
        return  # user hasn't opted into email for this type

    user = await pg_ops.get_user(user_id)
    if not (user and user.get("email")):
        return  # no email address on file

    try:
        await send_email(user["email"], notification)
        logger.info("Offline fallback: emailed %s for %s", user["email"], user_id)
    except Exception as e:
        # Email failure must not undo the successful MQTT delivery. Log it.
        # (A future phase could dead-letter the email leg separately.)
        logger.warning("Email fallback failed for %s: %s", user_id, e)


async def deliver_notification(ctx, user_id: str, notification: dict) -> str:
    """Deliver one notification, with retries and DLQ on final failure."""
    attempt = ctx["job_try"]          # 1, 2, 3, ...
    try:
        await publish_notification(user_id, notification)
    except Exception as e:
        if attempt < MAX_TRIES:
            # Exponential backoff + a little jitter to avoid thundering herds.
            delay = 2 ** attempt + random.uniform(0, 1)
            logger.warning(
                "Delivery failed (try %s/%s), retrying in %.1fs: %s",
                attempt, MAX_TRIES, delay, e,
            )
            raise Retry(defer=delay)
        # Out of retries → dead-letter it, then fail the job.
        await _dead_letter(ctx, user_id, notification, str(e))
        raise

    logger.info("Delivered notification %s to %s", notification.get("id"), user_id)

    await _maybe_email_fallback(user_id, notification)
    return "ok"

async def startup(ctx):
    clients["mongo"] = AsyncMongoClient(settings.MONGO_URI)
    clients["pg"] = await asyncpg.create_pool(dsn=settings.POSTGRES_DSN)
    clients["redis"] = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    # Keep a direct handle for the DLQ writer too.
    ctx["mongo"] = clients["mongo"]
    logger.info("Worker connections opened")

async def shutdown(ctx):
    if clients["pg"] is not None:
        await clients["pg"].close()

    if clients["mongo"] is not None:
        await clients["mongo"].close()

    if clients["redis"] is not None:
        await clients["redis"].aclose()

    logger.info("Worker connections closed")

class WorkerSettings:

    functions = [deliver_notification]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
    max_tries = MAX_TRIES
