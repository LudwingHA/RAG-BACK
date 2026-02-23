from pymongo import MongoClient
from typing import List, Dict

class MongoVectorStore:

    def __init__(self):
        self.client = MongoClient("mongodb://localhost:27017")
        self.db = self.client["sict_rag"]
        self.collection = self.db["documents"]

    def insert_document(self, content: str, embedding: List[float], metadata: Dict):
        self.collection.insert_one({
            "content": content,
            "embedding": embedding,
            "metadata": metadata
        })

    def search_similar(self, query_embedding: List[float], limit: int = 5):
        return list(self.collection.find().limit(limit))