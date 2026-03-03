import os
from fastapi import APIRouter, HTTPException, Depends
from app.services.document_processor import DocumentProcessor
from app.services.embedding_service import GeminiEmbeddingService
from app.services.vector_store import MongoVectorStore
from app.services.rag_services import RAGService
from app.utils.auth_utils import get_current_user
from app.services.ConversationService import ConversationService
router = APIRouter()
processor = DocumentProcessor(chunk_size=1000, chunk_overlap=200)
embedding_service = GeminiEmbeddingService()
vector_store = MongoVectorStore()
rag_service = RAGService(embedding_service, vector_store)
conversation_service = ConversationService()
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
        conversation_service.save_message(user_id, "user", query)
        # Aquí RAGService ya usa la memoria ligada a user_id
        result = rag_service.answer_question(query, user_id=user_id)
        ai_response = result.get("answer")
        conversation_service.save_message(user_id, "assitant", ai_response)

        return{
            "answer": ai_response
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/api/chat/history")
async def get_history(user_id: str = Depends(get_current_user)):
    conversation = conversation_service.get_conversation(user_id)
    if not conversation:
        return {"messages": [

        ]}
    return {
        "messages": conversation.get("messages", [])
    }

# --- Utilidades ---

@router.delete("/api/admin/clear-db")
async def clear_db():
    vector_store.collection.delete_many({})
    return {"status": "success", "message": "Vectores eliminados"}