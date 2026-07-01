from app.config import settings
from app.state import clients

def notifications_collection():
    """Return the MongoDB 'notifications' collection."""
    return clients["mongo"][settings.MONGO_DB]["notifications"]


def dead_letters_collection():
    """Return the MongoDB 'dead_letters' collection (permanently-failed jobs)."""
    return clients["mongo"][settings.MONGO_DB]["dead_letters"]


def serialize(doc: dict) -> dict:
    """Convert a Mongo document into clean JSON.

    MongoDB auto-creates an _id of type ObjectId, which is not valid JSON.
    We rename it to a string `id` field so it serializes nicely.
    """
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc