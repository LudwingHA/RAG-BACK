from pymongo import MongoClient
from typing import List, Dict
from app.core.config import settings

class MongoVectorStore:
    def __init__(self):
        self.client = MongoClient(settings.MONGO_URL)
        self.db = self.client[settings.DB_NAME]
        self.collection = self.db["documents"]

    def insert_document(self, content: str, embedding: List[float], metadata: Dict):
        """Inserta un solo documento (uso para pruebas o actualizaciones pequeñas)."""
        self.collection.insert_one({
            "content": content,
            "embedding": embedding,
            "metadata": metadata
        })

    def insert_many_documents(self, documents: List[Dict]):
        """
        Inserta múltiples documentos en una sola operación.
        ¡Mucho más rápido para archivos grandes de la SICT!
        """
        if documents:
            # MongoDB Atlas recomienda insert_many para rendimiento
            self.collection.insert_many(documents)

    def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        score_threshold: float = 0.40
    ):
        """
        Búsqueda semántica avanzada con filtro de score.
        """
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index", 
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": 300, # Aumentado para mayor precisión
                    "limit": limit
                }
            },
            {
                "$addFields": {
                    "score": {"$meta": "vectorSearchScore"}
                }
            },
            {
                "$match": {
                    "score": {"$gte": score_threshold}
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "embedding": 0 # No enviamos el vector al LLM
                }
            }
        ]

        return list(self.collection.aggregate(pipeline))