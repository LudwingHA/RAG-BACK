import os
from fastapi import FastAPI, HTTPException
from app.routes import routes
from app.services.document_processor import DocumentProcessor
from app.utils.chunking import TextChunker
from app.services.embedding_service import GeminiEmbeddingService
from app.services.vector_store import MongoVectorStore

# ===================================
# INICIALIZACIÓN APP
# ===================================

app = FastAPI(title="SICT BACKEND - RAG")

app.include_router(routes.routes, prefix="/api")

# Inicializar processor global
processor = DocumentProcessor(chunk_size=1000, chunk_overlap=200)

# ===================================
# ROOT
# ===================================

@app.get("/")
def root():
    return {
        "message": "SICT RAG FUNCIONANDO CORRECTAMENTE",
        "status": "OK"
    }

# ===================================
# TEST DOCUMENTO
# ===================================
embedding_service = GeminiEmbeddingService()
vector_store = MongoVectorStore()

@app.post("/ingest")
def ingest(file_path: str):
    chunks = processor.process_file(file_path)

    for chunk in chunks:
        embedding = embedding_service.generate_embedding(chunk["content"])
        vector_store.insert_document(
            content=chunk["content"],
            embedding=embedding,
            metadata=chunk["metadata"]
        )

    return {"status": "Documento indexado", "chunks": len(chunks)}

@app.get("/test-doc")
def test_doc():

    file_path = os.path.abspath("textExcel.xlsx")

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"Archivo no encontrado en ruta: {file_path}"
        )

    chunks = processor.process_file(file_path)

    return {
        "file": file_path,
        "exists": True,
        "total_chunks": len(chunks),
        "preview": chunks[:3] if chunks else []
    }

# ===================================
# TEST CHUNKING
# ===================================

@app.get("/test-chunk")
def test_chunk():

    file_path = os.path.abspath("testExcel.xlsx")

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"Archivo no encontrado en ruta: {file_path}"
        )

    documents = processor.process_file(file_path)

    if not documents:
        return {
            "message": "No se generaron fragmentos del Excel",
            "total_chunks": 0
        }

    # Ahora sí chunking correcto
    all_chunks = []

    for doc in documents:
        content = doc["content"]
        chunks = TextChunker.chunk_text(content)

        for chunk in chunks:
            all_chunks.append({
                "content": chunk,
                "metadata": doc["metadata"]
            })

    return {
        "total_original_rows": len(documents),
        "total_chunks_after_processing": len(all_chunks),
        "first_chunk": all_chunks[0] if all_chunks else None
    }