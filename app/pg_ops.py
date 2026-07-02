"""PostgreSQL operations via asyncpg — users and notification preferences.

asyncpg basics:
  conn.execute(sql, *args)   -> run a write
  conn.fetchrow(sql, *args)  -> one row (or None)
  conn.fetch(sql, *args)     -> many rows
Parameters use $1, $2, ... (NOT ?), which safely prevents SQL injection.
"""

from pathlib import Path

from app.state import clients


def _pool():
    """Shortcut to the shared asyncpg pool opened at startup."""
    return clients["pg"]


async def init_schema() -> None:
    """Create tables if they don't exist (run once at startup)."""
    sql = Path(__file__).parent.joinpath("schema.sql").read_text()
    async with _pool().acquire() as conn:
        await conn.execute(sql)


# --------------------------------- Users -----------------------------------

async def create_user(user_id: str, email: str | None, name: str | None) -> dict:
    """Create or update a user (upsert)."""
    async with _pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (id, email, name)
            VALUES ($1, $2, $3)
            ON CONFLICT (id) DO UPDATE
                SET email = EXCLUDED.email, name = EXCLUDED.name
            RETURNING id, email, name, created_at
            """,
            user_id, email, name,
        )
        return dict(row)


async def get_user(user_id: str) -> dict | None:
    async with _pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, name, role, created_at FROM users WHERE id = $1",
            user_id,
        )
        return dict(row) if row else None


# ----------------------------- Auth (Phase 14) -----------------------------

async def create_auth_user(
    user_id: str, email: str, password_hash: str, name: str | None, role: str = "user"
) -> dict:
    """Register a user with a hashed password. Fails if id/email already taken."""
    async with _pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (id, email, name, password_hash, role)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, email, name, role, created_at
            """,
            user_id, email, name, password_hash, role,
        )
        return dict(row)


async def get_user_with_hash(email: str) -> dict | None:
    """Fetch a user by email INCLUDING the password hash (for login only)."""
    async with _pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, name, role, password_hash, created_at FROM users WHERE email = $1",
            email,
        )
        return dict(row) if row else None


# ------------------------------ Preferences --------------------------------

async def set_preference(user_id: str, type_: str, enabled: bool) -> None:
    """Set (or update) whether a notification type is enabled for a user."""
    async with _pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO notification_preferences (user_id, type, enabled)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, type) DO UPDATE
                SET enabled = EXCLUDED.enabled
            """,
            user_id, type_, enabled,
        )


async def is_type_enabled(user_id: str, type_: str) -> bool:
    """Enabled unless a row explicitly says otherwise (default = opt-in)."""
    async with _pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT enabled FROM notification_preferences WHERE user_id = $1 AND type = $2",
            user_id, type_,
        )
        return True if row is None else row["enabled"]


async def list_preferences(user_id: str) -> list[dict]:
    async with _pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT type, enabled FROM notification_preferences WHERE user_id = $1 ORDER BY type",
            user_id,
        )
        return [dict(r) for r in rows]


# --------------------------- Channel preferences ---------------------------

async def set_channel_preference(
    user_id: str, type_: str, channel: str, enabled: bool
) -> None:
    """Enable/disable a specific delivery channel for a (user, type)."""
    async with _pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO channel_preferences (user_id, type, channel, enabled)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, type, channel) DO UPDATE
                SET enabled = EXCLUDED.enabled
            """,
            user_id, type_, channel, enabled,
        )


async def is_channel_enabled(user_id: str, type_: str, channel: str) -> bool:
    """A channel is enabled ONLY if a row exists with enabled = TRUE.

    (Opt-in: no row => channel not used. Good for intrusive channels like email.)
    """
    async with _pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT enabled FROM channel_preferences
            WHERE user_id = $1 AND type = $2 AND channel = $3
            """,
            user_id, type_, channel,
        )
        return bool(row and row["enabled"])


async def list_channel_preferences(user_id: str) -> list[dict]:
    async with _pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT type, channel, enabled FROM channel_preferences
            WHERE user_id = $1 ORDER BY type, channel
            """,
            user_id,
        )
        return [dict(r) for r in rows]
