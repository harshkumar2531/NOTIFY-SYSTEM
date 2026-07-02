from app.config import settings
from app.state import clients

async def ensure_indexes():
    await notifications_collection().create_index([("user_id", 1), ("_id", -1)])
    await notifications_collection().create_index([("status", 1), ("scheduled_for", 1)])
    await dead_letters_collection().create_index([("failed_at", -1)])

def notifications_collection():

    return clients["mongo"][settings.MONGO_DB]["notifications"]

def dead_letters_collection():

    return clients["mongo"][settings.MONGO_DB]["dead_letters"]

def notifications_collection_for(mongo_client):

    return mongo_client[settings.MONGO_DB]["notifications"]

def serialize(doc: dict) -> dict:

    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc
