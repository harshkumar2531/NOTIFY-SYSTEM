from pathlib import Path
from app.state import clients


def _pool():
    return clients["pg"]


async def init_schema() -> None:
    sql = Path(__file__).parent.joinpath("schema.sql").read_text()

    async with _pool().acquire() as conn:
        await conn.execute(sql)


async def create_user(user_id: str, email: str | None, name: str | None) -> dict:
    async with _pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (id, email, name)
            VALUES ($1, $2, $3)
            ON CONFLICT (id)
            DO UPDATE SET
                email = EXCLUDED.email,
                name = EXCLUDED.name
            RETURNING *;
            """,
            user_id,
            email,
            name,
        )
        return dict(row)


async def get_user(user_id: str) -> dict | None:
    async with _pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT *
            FROM users
            WHERE id = $1;
            """,
            user_id,
        )

        return dict(row) if row else None


async def set_preference(
    user_id: str,
    type_: str,
    enabled: bool,
) -> None:

    async with _pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO notification_preferences
                (user_id, type, enabled)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, type)
            DO UPDATE SET enabled = EXCLUDED.enabled;
            """,
            user_id,
            type_,
            enabled,
        )


async def is_type_enabled(user_id: str, type_: str) -> bool:
    async with _pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT enabled
            FROM notification_preferences
            WHERE user_id=$1
              AND type=$2;
            """,
            user_id,
            type_,
        )

        return True if row is None else row["enabled"]


async def list_preferences(user_id: str) -> list[dict]:
    async with _pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM notification_preferences
            WHERE user_id=$1
            ORDER BY type;
            """,
            user_id,
        )

        return [dict(r) for r in rows]


async def set_channel_preference(
    user_id: str,
    type_: str,
    channel: str,
    enabled: bool,
) -> None:

    async with _pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO channel_preferences
                (user_id, type, channel, enabled)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (user_id,type,channel)
            DO UPDATE SET enabled = EXCLUDED.enabled;
            """,
            user_id,
            type_,
            channel,
            enabled,
        )


async def is_channel_enabled(
    user_id: str,
    type_: str,
    channel: str,
) -> bool:

    async with _pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT enabled
            FROM channel_preferences
            WHERE user_id=$1
              AND type=$2
              AND channel=$3;
            """,
            user_id,
            type_,
            channel,
        )

        return bool(row and row["enabled"])


async def list_channel_preferences(user_id: str) -> list[dict]:
    async with _pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM channel_preferences
            WHERE user_id=$1
            ORDER BY type, channel;
            """,
            user_id,
        )

        return [dict(r) for r in rows]