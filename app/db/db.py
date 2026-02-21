from pymongo import MongoClient
from app.core.config import settings
client = MongoClient(settings.MONGO_URL)
db = client[settings.DB_NAME]
chunks_collection = db["chunks"]