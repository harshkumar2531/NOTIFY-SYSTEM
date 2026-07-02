from contextlib import asynccontextmanager
import aiomqtt
import asyncpg
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pymongo import AsyncMongoClient  # new built-in async API (replaces deprecated motor)
import jwt

from app import crud, pg_ops, redis_ops
from app.auth import (
    get_current_user,
    is_refresh_revoked,
    require_owner_or_admin,
    revoke_refresh_token,
)
from app.config import settings
from app.queue import get_arq_pool
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import (
    ChannelPreferenceSet,
    LoginRequest,
    NotificationCreate,
    NotificationOut,
    PreferenceSet,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserCreate,
)
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
    print(" Connections opened")

    yield  # <-- the app handles requests here, reusing the connections above

    # ---- SHUTDOWN: close connections cleanly ----
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


# -------------------- Auth (Phase 14) --------------------
@app.post("/auth/register")
async def register(payload: RegisterRequest):
    try:
        user = await pg_ops.create_auth_user(
            payload.id,
            payload.email,
            hash_password(payload.password),
            payload.name,
        )
        return user

    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=409,
            detail="User id or email already exists",
        )

    except Exception as e:
        print("REGISTER ERROR:", repr(e))
        raise


@app.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    """Verify credentials and issue access + refresh tokens."""
    user = await pg_ops.get_user_with_hash(payload.email)
    if not user or not user.get("password_hash") or not verify_password(
        payload.password, user["password_hash"]
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return TokenResponse(
        access_token=create_access_token(user["id"], user["role"]),
        refresh_token=create_refresh_token(user["id"]),
    )


@app.post("/auth/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest):
    """Exchange a valid, non-revoked refresh token for a fresh token pair."""
    token = payload.refresh_token
    try:
        claims = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if claims.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    if await is_refresh_revoked(token):
        raise HTTPException(status_code=401, detail="Refresh token revoked")

    sub = claims["sub"]
    user = await pg_ops.get_user(sub)
    role = user["role"] if user else "user"
    # Rotate: revoke the old refresh token, issue a new pair.
    await revoke_refresh_token(token)
    return TokenResponse(
        access_token=create_access_token(sub, role),
        refresh_token=create_refresh_token(sub),
    )

@app.post("/auth/logout")
async def logout(payload: RefreshRequest):
    """Revoke a refresh token so it can no longer mint access tokens."""
    await revoke_refresh_token(payload.refresh_token)
    return {"revoked": True}

@app.get("/auth/me")
async def me(current_user: dict = Depends(get_current_user)):
    """Return the currently-authenticated caller."""
    if current_user["role"] == "service":
        return current_user
    user = await pg_ops.get_user(current_user["id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/notifications")
async def create_notification(
    payload: NotificationCreate,
    current_user: dict = Depends(get_current_user),
):

    require_owner_or_admin(payload.user_id, current_user)
    return await crud.create_notification(payload)

@app.get("/notifications/{user_id}", response_model=list[NotificationOut])
async def get_notifications(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """List a user's notifications, newest first (own data only)."""
    require_owner_or_admin(user_id, current_user)
    return await crud.list_notifications(user_id)

@app.get("/notifications/{user_id}/unread-count")
async def unread_count(
    user_id: str, current_user: dict = Depends(get_current_user)
):
    """Fast badge value from Redis (own data only)."""
    require_owner_or_admin(user_id, current_user)
    return {"user_id": user_id, "unread": await redis_ops.get_unread(user_id)}


@app.post("/notifications/{user_id}/mark-all-read")
async def mark_all_read(
    user_id: str, current_user: dict = Depends(get_current_user)
):
    """Mark all notifications read in Mongo and reset the Redis counter."""
    require_owner_or_admin(user_id, current_user)
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

@app.post("/users", dependencies=[Depends(get_current_user)])
async def create_user(payload: UserCreate):
    """Create or update a user profile (service/admin action)."""
    return await pg_ops.create_user(payload.id, payload.email, payload.name)


@app.get("/users/{user_id}")
async def get_user(user_id: str, current_user: dict = Depends(get_current_user)):
    require_owner_or_admin(user_id, current_user)
    user = await pg_ops.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.put("/users/{user_id}/preferences")
async def set_preference(
    user_id: str, payload: PreferenceSet,
    current_user: dict = Depends(get_current_user),
):
    """Enable or disable a notification type for a user."""
    require_owner_or_admin(user_id, current_user)
    await pg_ops.set_preference(user_id, payload.type, payload.enabled)
    return {"user_id": user_id, "type": payload.type, "enabled": payload.enabled}

@app.get("/users/{user_id}/preferences")
async def get_preferences(user_id: str, current_user: dict = Depends(get_current_user)):
    require_owner_or_admin(user_id, current_user)
    return await pg_ops.list_preferences(user_id)

@app.put("/users/{user_id}/channel-preferences")
async def set_channel_preference(
    user_id: str, payload: ChannelPreferenceSet,
    current_user: dict = Depends(get_current_user),
):
    """Enable/disable a delivery channel (e.g. 'email') for a notification type."""
    require_owner_or_admin(user_id, current_user)
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
async def get_channel_preferences(
    user_id: str, current_user: dict = Depends(get_current_user)
):
    require_owner_or_admin(user_id, current_user)
    return await pg_ops.list_channel_preferences(user_id)

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

app.mount("/", StaticFiles(directory="static", html=True), name="static")
