from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    cargo: str
    role: str = "user"
    is_active: bool = True
class UserCreate(UserBase):
    password: str
class UserInDB(UserBase):
    id: Optional[str] = Field(None, alias="_id")
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None