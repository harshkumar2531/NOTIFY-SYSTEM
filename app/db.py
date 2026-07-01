from app.config import settings
from app.state import clients

def notifications_collection():
    return clients["mongo"][settings.MONGO_DB]["notifications"]

def dead_letters_collection():
    return clients["mongo"][settings.MONGO_DB]["dead_letters"]

def serialize(doc: dict) -> dict:

    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc