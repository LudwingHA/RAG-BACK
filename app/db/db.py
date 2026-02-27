from pymongo import MongoClient
from app.core.config import settings

class Database:
    client: MongoClient = None
    @classmethod
    def connect(cls):
        if cls.client is None:
            cls.client = MongoClient(settings.MONGO_URL)
        return cls.client[settings.DB_NAME]
db = Database.connect()