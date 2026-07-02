from datetime import datetime, timedelta, timezone
import logging
from app import pg_ops, redis_ops
from app.db import dead_letters_collection, notifications_collection, serialize
from app.models import NotificationCreate
from app.state import clients

logger = logging.getLogger("notify")

def _resolve_schedule(payload: NotificationCreate) -> datetime | None:

    now = datetime.now(timezone.utc)
    if payload.scheduled_for is not None:
        when = payload.scheduled_for
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when if when > now else None  
    if payload.delay_seconds and payload.delay_seconds > 0:
        return now + timedelta(seconds=payload.delay_seconds)
    return None

async def create_notification(payload: NotificationCreate) -> dict:

    if not await pg_ops.is_type_enabled(payload.user_id, payload.type):
        logger.info("Skipped: %s has muted type '%s'", payload.user_id, payload.type)
        return {"skipped": True, "reason": "muted", "type": payload.type}

    deliver_at = _resolve_schedule(payload)

    doc = payload.model_dump(exclude={"delay_seconds", "scheduled_for"})
    doc["read"] = False
    doc["created_at"] = datetime.now(timezone.utc)
    doc["scheduled_for"] = deliver_at                    
    doc["status"] = "scheduled" if deliver_at else "queued"

    result = await notifications_collection().insert_one(doc)  
    doc["_id"] = result.inserted_id
    saved = serialize(doc)

    await redis_ops.increment_unread(saved["user_id"])

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
    cursor = (
        notifications_collection()
        .find({"user_id": user_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [serialize(doc) async for doc in cursor]

async def mark_all_read(user_id: str) -> int:
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
