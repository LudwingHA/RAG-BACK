from datetime import datetime
from bson import ObjectId
from app.db.db import db

class ConversationService:
    def __init__(self):
        self.collection = db["conversations"]

    def create_conversation(self, user_id: str, title: str):
        now = datetime.utcnow()

        result = self.collection.insert_one({
            "user_id": user_id,
            "title": title,
            "messages": [],
            "created_at": now,
            "updated_at": now
        })

        return str(result.inserted_id)

    def save_message(self, conversation_id: str, role: str, content: str):
        now = datetime.utcnow()

        message = {
            "role": role,
            "content": content,
            "timestamp": now
        }

        self.collection.update_one(
            {"_id": ObjectId(conversation_id)},
            {
                "$push": {"messages": message},
                "$set": {"updated_at": now}
            }
        )

    def get_user_conversations(self, user_id: str):
        conversations = self.collection.find(
            {"user_id": user_id},
            {"messages": 0}
        ).sort("updated_at", -1)

        return list(conversations)

    def get_conversation(self, conversation_id: str):
        return self.collection.find_one({"_id": ObjectId(conversation_id)})

    def delete_conversation(self, conversation_id: str):
        self.collection.delete_one({"_id": ObjectId(conversation_id)})