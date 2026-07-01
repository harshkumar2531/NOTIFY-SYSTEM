import logging
import random
from datetime import datetime, timezone
from arq import Retry
from arq.connections import RedisSettings
from pymongo import AsyncMongoClient
from app.config import settings
from app.mqtt import publish_notification

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
    return "ok"


# ---- Worker lifecycle: give the worker its own Mongo client for the DLQ ----

async def startup(ctx):
    ctx["mongo"] = AsyncMongoClient(settings.MONGO_URI)


async def shutdown(ctx):
    await ctx["mongo"].close()


class WorkerSettings:
    """ARQ discovers this when you run `arq app.worker.WorkerSettings`."""

    functions = [deliver_notification]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
    max_tries = MAX_TRIES