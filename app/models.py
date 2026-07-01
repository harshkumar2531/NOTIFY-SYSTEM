from datetime import datetime

from pydantic import BaseModel, Field


class NotificationCreate(BaseModel):
    """What a client SENDS to create a notification."""

    user_id: str                      # who the notification is for
    title: str
    body: str
    type: str = "general"             # e.g. "chat", "order", "system"
    data: dict = Field(default_factory=dict)  # optional extra payload


class NotificationOut(BaseModel):
    """What we SEND BACK to the client."""

    id: str
    user_id: str
    title: str
    body: str
    type: str
    data: dict
    read: bool
    created_at: datetime


# --------------------------- Users & preferences ---------------------------

class UserCreate(BaseModel):
    """What a client SENDS to create/update a user."""

    id: str
    email: str | None = None
    name: str | None = None


class PreferenceSet(BaseModel):
    """What a client SENDS to enable/disable a notification type (in-app)."""

    type: str
    enabled: bool


class ChannelPreferenceSet(BaseModel):
    """Enable/disable a specific delivery channel for a (user, type)."""

    type: str
    channel: str          # 'inapp' | 'email' | 'sms' | 'push'
    enabled: bool