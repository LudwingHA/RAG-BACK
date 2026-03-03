import os
from fastapi import APIRouter, HTTPException, Depends
from app.services.document_processor import DocumentProcessor
from app.services.embedding_service import GeminiEmbeddingService
from app.services.vector_store import MongoVectorStore
from app.services.rag_services import RAGService
from app.utils.auth_utils import get_current_user
from app.services.ConversationService import ConversationService
from pydantic import BaseModel
router = APIRouter()
processor = DocumentProcessor(chunk_size=1000, chunk_overlap=200)
embedding_service = GeminiEmbeddingService()
vector_store = MongoVectorStore()
rag_service = RAGService(embedding_service, vector_store)
conversation_service = ConversationService()
class ChatRequest(BaseModel):
    query: str
    conversation_id: str | None = None
@router.post("/api/ingest")
async def ingest(file_path: str):
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Archivo local no encontrado")
        
    chunks = processor.process_file(file_path)
    for chunk in chunks:
        embedding = embedding_service.generate_embedding(chunk["content"])
        vector_store.insert_document(chunk["content"], embedding, chunk["metadata"])
    return {"status": "success", "chunks": len(chunks)}

@router.post("/api/chat")
async def chat(request: ChatRequest, user_id: str = Depends(get_current_user)):
    query = request.query
    conversation_id = request.conversation_id
    if not query:
        raise HTTPException(status_code=400, detail="Consulta vacía")
    try:
        if not conversation_id:
            title = rag_service.generate_title(query)
            conversation_id = conversation_service.create_conversation(user_id, title)

        conversation_service.save_message(conversation_id, "user", query)

        result = rag_service.answer_question(query, user_id=user_id)
        ai_response = result.get("answer")
        conversation_service.save_message(conversation_id, "assistant", ai_response)
        return {
            "answer": ai_response,
            "conversation_id": conversation_id
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
@router.get("/api/conversations")
async def get_conversations(user_id: str = Depends(get_current_user)):
    conversations = conversation_service.get_user_conversations(user_id)
    return {"conversations": conversations}
@router.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    conversation = conversation_service.get_conversation(conversation_id)
    return conversation
@router.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    conversation_service.delete_conversation(conversation_id)
    return {"status": "deleted"}

# --- Utilidades ---

@router.delete("/api/admin/clear-db")
async def clear_db():
    vector_store.collection.delete_many({})
    return {"status": "success", "message": "Vectores eliminados"}