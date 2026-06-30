from datetime import datetime, timezone
import logging
from app import redis_ops
from app.db import notifications_collection, serialize
from app.models import NotificationCreate
from app.mqtt import publish_notification
from app import pg_ops

async def create_notification(payload: NotificationCreate) -> dict:

    if not await pg_ops.is_type_enabled(payload.user_id, payload.type):
        logger.info("Skipped: %s muted '%s'", payload.user_id, payload.type)
        return {"skipped": True, "reason": "muted", "type": payload.type}

logger = logging.getLogger("notify")

async def create_notification(payload: NotificationCreate) -> dict:
   
    doc = payload.model_dump()
    doc["read"] = False
    doc["created_at"] = datetime.now(timezone.utc)

    result = await notifications_collection().insert_one(doc)  
    doc["_id"] = result.inserted_id
    saved = serialize(doc)

    await redis_ops.increment_unread(saved["user_id"])

    try:
        await publish_notification(saved["user_id"], saved)
    except Exception as e:
        logger.warning("MQTT publish failed (notification still stored): %s", e)

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
