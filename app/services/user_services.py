from passlib.context import CryptContext
from app.db.db import db
from app.models.userModel import UserCreate, UserInDB

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserService:
    def __init__(self):
        self.collection = db["users"]
    def get_password_hash(self, password):
        return pwd_context.hash(password)
    def create_user(self, user_in: UserCreate):
        user_dict = user_in.model_dump()
        user_dict["hashed_password"] = self.get_password_hash(user_dict.pop("password"))