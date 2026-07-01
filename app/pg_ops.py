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

            user_id, email, name,
        )
        return dict(row)

async def get_user(user_id: str) -> dict | None:
    async with _pool().acquire() as conn:
        row = await conn.fetchrow(
   
            user_id,
        )
        return dict(row) if row else None

async def set_preference(user_id: str, type_: str, enabled: bool) -> None:

    async with _pool().acquire() as conn:
        await conn.execute(

            user_id, type_, enabled,
        )

async def is_type_enabled(user_id: str, type_: str) -> bool:
    async with _pool().acquire() as conn:
        row = await conn.fetchrow(

            user_id, type_,
        )
        return True if row is None else row["enabled"]

async def list_preferences(user_id: str) -> list[dict]:
    async with _pool().acquire() as conn:
        rows = await conn.fetch(
            user_id,
        )
        return [dict(r) for r in rows]

async def set_channel_preference(
    user_id: str, type_: str, channel: str, enabled: bool
) -> None:

    async with _pool().acquire() as conn:
        await conn.execute(

            user_id, type_, channel, enabled,
        )

async def is_channel_enabled(user_id: str, type_: str, channel: str) -> bool:

    async with _pool().acquire() as conn:
        row = await conn.fetchrow(

            user_id, type_, channel,
        )
        return bool(row and row["enabled"])

async def list_channel_preferences(user_id: str) -> list[dict]:
    async with _pool().acquire() as conn:
        rows = await conn.fetch(

            user_id,
        )
        return [dict(r) for r in rows]
    
