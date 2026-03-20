from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from bson import ObjectId

class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    cargo: str
    role: str = "user"
    is_active: bool = True

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class UserInDB(UserBase):
    id: Optional[str] = Field(None, alias="_id")
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    # Nuevos campos
    phone: Optional[str] = None
    extension: Optional[str] = None
    office: Optional[str] = None
    address: Optional[str] = None
    employee_id: Optional[str] = None
    department: Optional[str] = None
    area: Optional[str] = None
    supervisor: Optional[str] = None
    profile_picture: Optional[str] = None
    updated_at: Optional[datetime] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    
class UserResponse(UserBase):
    id: str = Field(..., alias="_id")
    created_at: datetime
    last_login: Optional[datetime] = None
    phone: Optional[str] = None
    extension: Optional[str] = None
    office: Optional[str] = None
    address: Optional[str] = None
    employee_id: Optional[str] = None
    department: Optional[str] = None
    area: Optional[str] = None
    supervisor: Optional[str] = None
    profile_picture: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}
class ProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    cargo: Optional[str] = None
    phone: Optional[str] = None
    extension: Optional[str] = None
    office: Optional[str] = None
    address: Optional[str] = None
    employee_id: Optional[str] = None
    department: Optional[str] = None
    area: Optional[str] = None
    supervisor: Optional[str] = None
    profile_picture: Optional[str] = None
    email: Optional[EmailStr] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)
    
    def validate_passwords(self):
        if self.new_password != self.confirm_password:
            raise ValueError("Las contraseñas nuevas no coinciden")
        return True