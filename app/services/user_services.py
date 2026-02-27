from passlib.context import CryptContext
from app.db.db import db
from app.models.userModel import UserCreate, UserInDB
from datetime import datetime
pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto"
)

class UserService:
    def __init__(self):
        self.collection = db["users"]

    def hash_password(self, password: str):
        return pwd_context.hash(password)

    def verify_password(self, plain_password, hashed_password):
        return pwd_context.verify(plain_password, hashed_password)

    def create_user(self, user_in: UserCreate):
        email = user_in.email.lower().strip()

        if self.collection.find_one({"email": email}):
            return None

        user_dict = user_in.model_dump()
        user_dict["email"] = email
        user_dict["hashed_password"] = self.hash_password(user_dict.pop("password"))
        user_dict["created_at"] = datetime.utcnow()
        user_dict["is_active"] = True
        user_dict["role"] = "user"

        result = self.collection.insert_one(user_dict)

        user_dict["_id"] = str(result.inserted_id)
        del user_dict["hashed_password"]

        return user_dict
    def get_user_by_email(self, email: str):
        return self.collection.find_one({"email": email})
    def authenticate_user(self, email: str, password: str):
        user = self.collection.find_one({"email": email})
        if not user:
            return False
        if not self.verify_password(password, user["hashed_password"]):
            return False
        return user