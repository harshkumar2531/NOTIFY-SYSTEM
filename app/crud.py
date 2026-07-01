
from datetime import datetime, timezone
import logging

from app import pg_ops, redis_ops
from app.db import dead_letters_collection, notifications_collection, serialize
from app.models import NotificationCreate
from app.state import clients

logger = logging.getLogger("notify")


async def create_notification(payload: NotificationCreate) -> dict:
    """Insert a new notification document, push it in real time, and return it.

    Returns the saved notification, OR {"skipped": True, ...} if the user has
    muted this notification type.
    """
    # 0) Respect user preference — skip muted types entirely (no store, no push).
    if not await pg_ops.is_type_enabled(payload.user_id, payload.type):
        logger.info("Skipped: %s has muted type '%s'", payload.user_id, payload.type)
        return {"skipped": True, "reason": "muted", "type": payload.type}

    doc = payload.model_dump()
    doc["read"] = False
    doc["created_at"] = datetime.now(timezone.utc)

    result = await notifications_collection().insert_one(doc)  # 1) STORE FIRST
    doc["_id"] = result.inserted_id
    saved = serialize(doc)

    # 2) Bump the unread badge counter in Redis.
    await redis_ops.increment_unread(saved["user_id"])

    # 3) ENQUEUE delivery (fast). The worker (app/worker.py) does the actual
    #    MQTT publish — and later email/SMS/push. If enqueue fails, the
    #    notification is still stored; the user can fetch it via GET.
    try:
        await clients["arq"].enqueue_job("deliver_notification", saved["user_id"], saved)
    except Exception as e:
        logger.warning("Enqueue failed (notification still stored): %s", e)

    return saved


async def list_notifications(user_id: str, limit: int = 50) -> list[dict]:
    """Return a user's notifications, newest first."""
    cursor = (
        notifications_collection()
        .find({"user_id": user_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [serialize(doc) async for doc in cursor]


async def mark_all_read(user_id: str) -> int:
    """Mark all of a user's notifications as read and reset the unread counter."""
    res = await notifications_collection().update_many(
        {"user_id": user_id, "read": False},
        {"$set": {"read": True}},
    )
    await redis_ops.reset_unread(user_id)
    return res.modified_count


# ---------------------------- Dead-letter queue ----------------------------

async def list_dead_letters(limit: int = 50) -> list[dict]:
    """List permanently-failed delivery jobs, newest first."""
    cursor = (
        dead_letters_collection()
        .find()
        .sort("failed_at", -1)
        .limit(limit)
    )
    return [serialize(doc) async for doc in cursor]


async def replay_dead_letter(dead_letter_id: str) -> dict:
    """Re-enqueue a dead-lettered job for delivery and mark it replayed."""
    from bson import ObjectId  # local import keeps top of file light

    coll = dead_letters_collection()
    doc = await coll.find_one({"_id": ObjectId(dead_letter_id)})
    if not doc:
        return {"found": False}

    # Re-enqueue the original delivery job.
    await clients["arq"].enqueue_job(
        "deliver_notification", doc["user_id"], doc["notification"]
    )
    await coll.update_one(
        {"_id": doc["_id"]}, {"$set": {"replayed": True}}
    )
    return {"found": True, "replayed": True, "user_id": doc["user_id"]}
