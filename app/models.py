from datetime import datetime
from pydantic import BaseModel, Field

class NotificationCreate(BaseModel):
   
    user_id: str                      # who the notification is for
    title: str
    body: str
    type: str = "general"             # e.g. "chat", "order", "system"
    data: dict = Field(default_factory=dict)  

class NotificationOut(BaseModel):

    id: str
    user_id: str
    title: str
    body: str
    type: str
    data: dict
    read: bool
    created_at: datetime
    
class UserCreate(BaseModel):
    id: str
    email: str | None = None
    name: str | None = None

class PreferenceSet(BaseModel):
    type: str
    enabled: bool