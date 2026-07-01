from contextlib import asynccontextmanager
import aiomqtt
import asyncpg
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pymongo import AsyncMongoClient  # new built-in async API (replaces deprecated motor)
from app import crud, pg_ops, redis_ops
from app.auth import require_api_key
from app.config import settings
from app.queue import get_arq_pool
from app.models import (
    ChannelPreferenceSet,
    NotificationCreate,
    NotificationOut,
    PreferenceSet,
    UserCreate,
)
from app.state import clients  

@asynccontextmanager
async def lifespan(app: FastAPI):

    clients["pg"] = await asyncpg.create_pool(dsn=settings.POSTGRES_DSN)
    clients["mongo"] = AsyncMongoClient(settings.MONGO_URI)
    clients["redis"] = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    clients["arq"] = await get_arq_pool()

    await pg_ops.init_schema()
    print(" Connections opened")

    yield  

    await clients["pg"].close()
    await clients["mongo"].close()
    await clients["redis"].aclose()
    await clients["arq"].aclose()
    print(" Connections closed")

app = FastAPI(title="Realtime Notification System", lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "Notification system is running 🚀"}

@app.get("/health")
async def health():

    status: dict[str, str] = {}

    try:
        await clients["redis"].ping()
        status["redis"] = "ok"
    except Exception as e:
        status["redis"] = f"error: {e}"

    try:
        async with clients["pg"].acquire() as conn:
            await conn.fetchval("SELECT 1")
        status["postgres"] = "ok"
    except Exception as e:
        status["postgres"] = f"error: {e}"

    try:
        await clients["mongo"].admin.command("ping")
        status["mongodb"] = "ok"
    except Exception as e:
        status["mongodb"] = f"error: {e}"

    try:
        async with aiomqtt.Client(settings.MQTT_HOST, port=settings.MQTT_PORT):
            pass
        status["vernemq"] = "ok"
    except Exception as e:
        status["vernemq"] = f"error: {e}"

    overall = "healthy" if all(v == "ok" for v in status.values()) else "degraded"
    return {"status": overall, "services": status}

@app.post("/notifications", dependencies=[Depends(require_api_key)])
async def create_notification(payload: NotificationCreate):
    return await crud.create_notification(payload)

@app.get("/notifications/{user_id}", response_model=list[NotificationOut])
async def get_notifications(user_id: str):
    return await crud.list_notifications(user_id)

@app.get("/notifications/{user_id}/unread-count")
async def unread_count(user_id: str):
    return {"user_id": user_id, "unread": await redis_ops.get_unread(user_id)}

@app.post("/notifications/{user_id}/mark-all-read", dependencies=[Depends(require_api_key)])
async def mark_all_read(user_id: str):
    updated = await crud.mark_all_read(user_id)
    return {"user_id": user_id, "marked_read": updated, "unread": 0}

@app.post("/presence/{user_id}/heartbeat")
async def heartbeat(user_id: str):
    await redis_ops.set_online(user_id)
    return {"user_id": user_id, "online": True, "ttl_seconds": redis_ops.PRESENCE_TTL}

@app.get("/presence/{user_id}")
async def presence(user_id: str):
    return {"user_id": user_id, "online": await redis_ops.is_online(user_id)}

@app.post("/users", dependencies=[Depends(require_api_key)])
async def create_user(payload: UserCreate):
    return await pg_ops.create_user(payload.id, payload.email, payload.name)

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    user = await pg_ops.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.put("/users/{user_id}/preferences", dependencies=[Depends(require_api_key)])
async def set_preference(user_id: str, payload: PreferenceSet):
    await pg_ops.set_preference(user_id, payload.type, payload.enabled)
    return {"user_id": user_id, "type": payload.type, "enabled": payload.enabled}

@app.get("/users/{user_id}/preferences")
async def get_preferences(user_id: str):
    return await pg_ops.list_preferences(user_id)

@app.put("/users/{user_id}/channel-preferences", dependencies=[Depends(require_api_key)])
async def set_channel_preference(user_id: str, payload: ChannelPreferenceSet):
    await pg_ops.set_channel_preference(
        user_id, payload.type, payload.channel, payload.enabled
    )
    return {
        "user_id": user_id,
        "type": payload.type,
        "channel": payload.channel,
        "enabled": payload.enabled,
    }

@app.get("/users/{user_id}/channel-preferences")
async def get_channel_preferences(user_id: str):
    return await pg_ops.list_channel_preferences(user_id)

@app.get("/admin/dead-letters")
async def admin_list_dead_letters(limit: int = 50):
    return await crud.list_dead_letters(limit)

@app.post("/admin/dead-letters/{dead_letter_id}/replay")
async def admin_replay_dead_letter(dead_letter_id: str):
    result = await crud.replay_dead_letter(dead_letter_id)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail="Dead-letter not found")
    return result

app.mount("/", StaticFiles(directory="static", html=True), name="static")
