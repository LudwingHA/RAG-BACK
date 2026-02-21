from fastapi import FastAPI
from app.routes import health
from app.routes import routes
from app.services.document_processor import DocumentProcessor
from app.utils.chunking import TextChunker
app = FastAPI(title="SICT BACKEND")
# app.include_router(health.router)
app.include_router(routes.routes, prefix="/api")
@app.get("/")
def root ():
    return {"MESSAGE": "SICT RAG FUNCIONANDO CORRECTAMENTE"}

@app.get("/test-doc")
def test_doc():
    text = DocumentProcessor.process_file("textExcel.xlsx")
    return {"length": len(text), "text": text}
@app.get("/test-chunk")
def test_chunk():
    text = DocumentProcessor.process_file("testExcel.xlsx")
    chunks = TextChunker.chunk_text(text)
    return {
        "total_chunks": len(chunks),
        "first_chunk": chunks[0]
    }
