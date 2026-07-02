
from datetime import datetime

from pydantic import BaseModel, Field


class NotificationCreate(BaseModel):
    """What a client SENDS to create a notification."""

    user_id: str                      # who the notification is for
    title: str
    body: str
    type: str = "general"             # e.g. "chat", "order", "system"
    data: dict = Field(default_factory=dict)  # optional extra payload

    # Scheduling (optional). If both are given, scheduled_for wins.
    # If neither is given, the notification is delivered immediately.
    delay_seconds: int | None = None          # e.g. 30 -> deliver in 30s
    scheduled_for: datetime | None = None      # e.g. "2026-07-05T09:00:00Z"


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


# ------------------------------- Auth models -------------------------------

class RegisterRequest(BaseModel):
    id: str
    email: str
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
