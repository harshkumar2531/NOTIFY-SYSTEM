from datetime import datetime, timedelta, timezone
import logging
from app import pg_ops, redis_ops
from app.db import dead_letters_collection, notifications_collection, serialize
from app.models import NotificationCreate
from app.state import clients

logger = logging.getLogger("notify")

def _resolve_schedule(payload: NotificationCreate) -> datetime | None:
    """Return the UTC datetime this notification should be delivered, or None
    for immediate. scheduled_for wins over delay_seconds if both are given."""
    now = datetime.now(timezone.utc)
    if payload.scheduled_for is not None:
        when = payload.scheduled_for
        # Treat naive datetimes as UTC.
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when if when > now else None  # past/now -> immediate
    if payload.delay_seconds and payload.delay_seconds > 0:
        return now + timedelta(seconds=payload.delay_seconds)
    return None

async def create_notification(payload: NotificationCreate) -> dict:
    """Insert a notification, then deliver it now OR schedule it for later.

    Returns the saved notification, OR {"skipped": True, ...} if the user has
    muted this notification type.
    """
    # 0) Respect user preference — skip muted types entirely (no store, no push).
    if not await pg_ops.is_type_enabled(payload.user_id, payload.type):
        logger.info("Skipped: %s has muted type '%s'", payload.user_id, payload.type)
        return {"skipped": True, "reason": "muted", "type": payload.type}

    deliver_at = _resolve_schedule(payload)

    doc = payload.model_dump(exclude={"delay_seconds", "scheduled_for"})
    doc["read"] = False
    doc["created_at"] = datetime.now(timezone.utc)
    doc["scheduled_for"] = deliver_at                       # None for immediate
    doc["status"] = "scheduled" if deliver_at else "queued"

    result = await notifications_collection().insert_one(doc)  # 1) STORE FIRST
    doc["_id"] = result.inserted_id
    saved = serialize(doc)

    # 2) Bump the unread badge counter in Redis (at create time, per your choice).
    await redis_ops.increment_unread(saved["user_id"])

    # 3) Deliver now, or schedule via ARQ defer. The worker does the actual send.
    try:
        if deliver_at:
            await clients["arq"].enqueue_job(
                "deliver_notification", saved["user_id"], saved,
                _defer_until=deliver_at,
            )
            logger.info("Scheduled notification %s for %s", saved["id"], deliver_at)
        else:
            await clients["arq"].enqueue_job(
                "deliver_notification", saved["user_id"], saved,
            )
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

async def list_dead_letters(limit: int = 50) -> list[dict]:

    cursor = (
        dead_letters_collection()
        .find()
        .sort("failed_at", -1)
        .limit(limit)
    )
    return [serialize(doc) async for doc in cursor]

async def replay_dead_letter(dead_letter_id: str) -> dict:
    from bson import ObjectId  

    coll = dead_letters_collection()
    doc = await coll.find_one({"_id": ObjectId(dead_letter_id)})
    if not doc:
        return {"found": False}

    await clients["arq"].enqueue_job(
        "deliver_notification", doc["user_id"], doc["notification"]
    )
    await coll.update_one(
        {"_id": doc["_id"]}, {"$set": {"replayed": True}}
    )
    return {"found": True, "replayed": True, "user_id": doc["user_id"]}
