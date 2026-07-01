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
from app.models import NotificationCreate, NotificationOut, PreferenceSet, UserCreate
from app.state import clients  # shared dict, opened once at startup, reused everywhere

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs startup code, yields while the app serves requests, then cleans up."""
    # ---- STARTUP: open connections once ----
    clients["pg"] = await asyncpg.create_pool(dsn=settings.POSTGRES_DSN)
    clients["mongo"] = AsyncMongoClient(settings.MONGO_URI)
    clients["redis"] = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    # ARQ job-queue pool — used to enqueue delivery jobs for the worker.
    clients["arq"] = await get_arq_pool()

    # Create Postgres tables if they don't exist yet.
    await pg_ops.init_schema()
    print("Connections opened")

    yield  # <-- the app handles requests here, reusing the connections above

    # ---- SHUTDOWN: close connections cleanly ----
    await clients["pg"].close()
    await clients["mongo"].close()
    await clients["redis"].aclose()
    await clients["arq"].aclose()
    print("Connections closed")


app = FastAPI(title="Realtime Notification System", lifespan=lifespan)


@app.get("/")
async def root():
    return {"message": "Notification system is running 🚀"}


@app.get("/health")
async def health():
    """Ping every backing service and report which are reachable."""
    status: dict[str, str] = {}

    # Redis
    try:
        await clients["redis"].ping()
        status["redis"] = "ok"
    except Exception as e:
        status["redis"] = f"error: {e}"

    # PostgreSQL
    try:
        async with clients["pg"].acquire() as conn:
            await conn.fetchval("SELECT 1")
        status["postgres"] = "ok"
    except Exception as e:
        status["postgres"] = f"error: {e}"

    # MongoDB
    try:
        await clients["mongo"].admin.command("ping")
        status["mongodb"] = "ok"
    except Exception as e:
        status["mongodb"] = f"error: {e}"

    # VerneMQ (MQTT): if the connect/disconnect handshake works, the broker is up.
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
    """Store + push a notification — unless the user has muted its type.

    Returns the saved notification, or {"skipped": true, ...} if muted.
    (No strict response_model here because the shape can differ.)
    """
    return await crud.create_notification(payload)


@app.get("/notifications/{user_id}", response_model=list[NotificationOut])
async def get_notifications(user_id: str):
    """List a user's notifications, newest first."""
    return await crud.list_notifications(user_id)

@app.get("/notifications/{user_id}/unread-count")
async def unread_count(user_id: str):
    """Fast badge value from Redis."""
    return {"user_id": user_id, "unread": await redis_ops.get_unread(user_id)}


@app.post("/notifications/{user_id}/mark-all-read", dependencies=[Depends(require_api_key)])
async def mark_all_read(user_id: str):
    """Mark all notifications read in Mongo and reset the Redis counter."""
    updated = await crud.mark_all_read(user_id)
    return {"user_id": user_id, "marked_read": updated, "unread": 0}


@app.post("/presence/{user_id}/heartbeat")
async def heartbeat(user_id: str):
    """Client calls this periodically to stay 'online' (refreshes the TTL)."""
    await redis_ops.set_online(user_id)
    return {"user_id": user_id, "online": True, "ttl_seconds": redis_ops.PRESENCE_TTL}


@app.get("/presence/{user_id}")
async def presence(user_id: str):
    """Is the user currently online?"""
    return {"user_id": user_id, "online": await redis_ops.is_online(user_id)}


# -------------------- Users & preferences (Phase 7) --------------------

@app.post("/users", dependencies=[Depends(require_api_key)])
async def create_user(payload: UserCreate):
    """Create or update a user (PostgreSQL = source of truth)."""
    return await pg_ops.create_user(payload.id, payload.email, payload.name)


@app.get("/users/{user_id}")
async def get_user(user_id: str):
    user = await pg_ops.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.put("/users/{user_id}/preferences", dependencies=[Depends(require_api_key)])
async def set_preference(user_id: str, payload: PreferenceSet):
    """Enable or disable a notification type for a user."""
    await pg_ops.set_preference(user_id, payload.type, payload.enabled)
    return {"user_id": user_id, "type": payload.type, "enabled": payload.enabled}


@app.get("/users/{user_id}/preferences")
async def get_preferences(user_id: str):
    return await pg_ops.list_preferences(user_id)


# -------------------- Dead-letter queue admin (Phase 11) --------------------
# Open (no API key) for dev convenience — lock down with require_api_key later.

@app.get("/admin/dead-letters")
async def admin_list_dead_letters(limit: int = 50):
    """List delivery jobs that failed all retries."""
    return await crud.list_dead_letters(limit)


@app.post("/admin/dead-letters/{dead_letter_id}/replay")
async def admin_replay_dead_letter(dead_letter_id: str):
    """Re-enqueue a failed job (e.g. after the broker is back up)."""
    result = await crud.replay_dead_letter(dead_letter_id)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail="Dead-letter not found")
    return result


# -------------------- Static web client (Phase 9) --------------------
# MUST be mounted LAST: a StaticFiles mount at "/" matches every path, so it
# would shadow the API routes above if mounted earlier. html=True serves
# static/index.html at the root URL ("/").
app.mount("/", StaticFiles(directory="static", html=True), name="static")
