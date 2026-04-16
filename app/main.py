import os
from fastapi import FastAPI
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from app.routes import user, ingest, modelsGemini, baches
from fastapi.staticfiles import StaticFiles
app = FastAPI(title="SICT RAG - Professional Edition")
RESULTADOS_DIR = Path("/Applications/XAMPP/xamppfiles/htdocs/01-bache/resultados")
app.mount("/resultados", StaticFiles(directory=str(RESULTADOS_DIR), html=True), name="resultados")

origins = [
    "http://localhost:5173",  
    "http://localhost:3000",  
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ingest.router)
app.include_router(user.router)
app.include_router(modelsGemini.router)
app.include_router(baches.router)