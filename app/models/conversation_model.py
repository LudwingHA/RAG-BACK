from datetime import datetime
from pydantic import BaseModel
from typing import List
class Message(BaseModel):
    role: str
    content: str
class Conversation(BaseModel):
    user_id: str
    message: List[Message]
    created_at: datetime
    updated_at: datetime