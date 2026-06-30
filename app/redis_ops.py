from app.state import clients

PRESENCE_TTL = 60  
def _r():
    
    return clients["redis"]

async def increment_unread(user_id: str) -> int:
  
    return await _r().incr(f"unread:{user_id}")

async def get_unread(user_id: str) -> int:
   
    val = await _r().get(f"unread:{user_id}")
    return int(val) if val else 0

async def reset_unread(user_id: str) -> None:
   
    await _r().set(f"unread:{user_id}", 0)

async def set_online(user_id: str) -> None:

    await _r().set(f"presence:{user_id}", "1", ex=PRESENCE_TTL)

async def is_online(user_id: str) -> bool:
    
    return await _r().exists(f"presence:{user_id}") == 1
