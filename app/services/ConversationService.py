from datetime import datetime
from app.db.db import db
class ConversationService:
    def __init__(self):
        self.collection = db["conversations"]
    def save_message(self, user_id:str, role:str, content:str):
        now = datetime.utcnow()
        conversation = self.collection.find_one({
            "user_id": user_id
        })
        message = {
            "role": role,
            "content": content,
            "timestamp": now
        }
        if conversation:
            self.collection.update_one(
                {"user_id": user_id},
                {
                    "$push": {"message":message},
                    "$set": {"updated_at": now}
                }
            )
        else:
            self.collection.insert_one({
                "user_id":user_id,
                "messages": [message],
                "created_at": now,
                "updated_at": now
            })
    def get_conversation(self, user_id:str):
        return self.collection.find_one({
            "user_id":user_id
        })