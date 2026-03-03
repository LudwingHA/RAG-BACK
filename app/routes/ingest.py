import os
from fastapi import APIRouter, HTTPException, Depends
from app.services.document_processor import DocumentProcessor
from app.services.embedding_service import GeminiEmbeddingService
from app.services.vector_store import MongoVectorStore
from app.services.rag_services import RAGService
from app.utils.auth_utils import get_current_user
router = APIRouter()
processor = DocumentProcessor(chunk_size=1000, chunk_overlap=200)
embedding_service = GeminiEmbeddingService()
vector_store = MongoVectorStore()
rag_service = RAGService(embedding_service, vector_store)
@router.post("/api/ingest")
async def ingest(file_path: str):
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Archivo local no encontrado")
        
    chunks = processor.process_file(file_path)
    for chunk in chunks:
        embedding = embedding_service.generate_embedding(chunk["content"])
        vector_store.insert_document(chunk["content"], embedding, chunk["metadata"])
    return {"status": "success", "chunks": len(chunks)}

@router.get("/api/chat")
async def chat(query: str, user_id: str = Depends(get_current_user)):
    """
    Chat con memoria individual por usuario.
    El user_id vendrá del frontend tras el login.
    """
    if not query:
        raise HTTPException(status_code=400, detail="Consulta vacía")
    
    try:
        # Aquí RAGService ya usa la memoria ligada a user_id
        result = rag_service.answer_question(query, user_id=user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Utilidades ---

@router.delete("/api/admin/clear-db")
async def clear_db():
    vector_store.collection.delete_many({})
    return {"status": "success", "message": "Vectores eliminados"}