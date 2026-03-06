import google.generativeai as genai
from typing import List
from fastapi import HTTPException
from app.core.config import settings 

class GeminiEmbeddingService:
    def __init__(self):
        api_key = settings.GEMINI_API 
        if not api_key:
            raise ValueError("La API Key de Gemini no está configurada.")
        
        genai.configure(api_key=api_key)
        self.model = "models/gemini-embedding-001"

    def generate_embedding(self, text: str, is_query: bool = False) -> List[float]:
        task = "retrieval_query" if is_query else "retrieval_document"
        
        try:
            response = genai.embed_content(
                model=self.model,
                content=text,
                task_type=task
            )
            return response["embedding"]
            
        except Exception as e:
            if "404" in str(e) and "004" in self.model:
                print(f"Modelo {self.model} no disponible. Usando fallback a embedding-001.")
                self.model = "models/gemini-embedding-001"
                return self.generate_embedding(text, is_query)
            
            raise HTTPException(
                status_code=500, 
                detail=f"Error en Gemini Embedding: {str(e)}"
            )
        
    def generate_embeddings_batch(self, texts: list[str]):
        """Envía una lista de textos y recibe una lista de vectores."""
        try:
          result = genai.embed_content(
            model=self.model,
            content=texts,
            task_type="retrieval_document"
        )
          return result['embedding']
        except Exception as e:
            print(f"Error en batch embedding: {e}")
            return None 