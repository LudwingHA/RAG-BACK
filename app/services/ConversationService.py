from datetime import datetime
from bson import ObjectId
from app.db.db import db

class ConversationService:
    def __init__(self):
        self.collection = db["conversations"]

    def _format_doc(self, doc):
        """Helper interno para convertir ObjectId a string y limpiar el documento."""
        if doc:
            doc["id"] = str(doc["_id"])
            del doc["_id"]
        return doc

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
        
        try:
            self.collection.update_one(
                {"_id": ObjectId(conversation_id)},
                {
                    "$push": {"messages": message},
                    "$set": {"updated_at": now}
                }
            )
        except Exception as e:
            print(f"Error al guardar mensaje: {e}")

    def get_user_conversations(self, user_id: str):
        """Retorna todas las conversaciones de un usuario (sin los mensajes pesados)."""
        conversations = self.collection.find(
            {"user_id": user_id},
            {"messages": 0}
        ).sort("updated_at", -1)
        
        return [self._format_doc(c) for c in conversations]

    def get_conversation(self, conversation_id: str):
        """Retorna una conversación específica con todos sus mensajes."""
        try:
            doc = self.collection.find_one({"_id": ObjectId(conversation_id)})
            return self._format_doc(doc)
        except Exception:
            return None

    def delete_conversation(self, conversation_id: str):
        """Elimina la conversación de la base de datos."""
        try:
            result = self.collection.delete_one({"_id": ObjectId(conversation_id)})
            return result.deleted_count > 0
        except Exception:
            return False