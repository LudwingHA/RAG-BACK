import google.generativeai as genai
from app.core.config import settings
from typing import List, Dict
import re
import logging
from google.api_core import exceptions
import time

logger=logging.getLogger(__name__)

genai.configure(api_key=settings.GEMINI_API)

def build_context(results, max_chars=3000):
    """Construye el bloque de texto con las fuentes encontradas."""
    sorted_results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)
    context = ""
    for r in sorted_results:
        source = r['metadata'].get('source', 'Documento SICT')
        page = f" (Pág. {r['metadata'].get('page')})" if r['metadata'].get('page') else ""
        piece = f"\nFuente: {source}{page}\nContenido:\n{r['content']}\n"
        if len(context) + len(piece) > max_chars:
            break
        context += piece
    return context.strip()

SYSTEM_PROMPT = """
Eres un asistente experto institucional de la Secretaría de Infraestructura, Comunicaciones y Transportes (SICT).
Tu objetivo es ayudar a los usuarios basándote exclusivamente en la normativa y documentos oficiales proporcionados.

REGLAS DE ORO:
1. Responde únicamente usando el CONTEXTO y el historial de la conversación.
2. Si la respuesta no está en el contexto, responde: "No se encontró información suficiente en los documentos institucionales."
3. Mantén un tono formal, claro y profesional.
4. No menciones el 'Contexto' directamente al usuario, solo usa la información.
"""
class RAGService:
    def __init__(self, embedding_service, vector_store):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.model = genai.GenerativeModel("models/gemini-2.0-flash")
        self.user_sessions: Dict[str, genai.ChatSession] = {}

    def safe_execute(self, func, *args, **kwargs):
        """Wrapper centralizado para manejar cuotas de Gemini."""
        for attempt in range(5):
            try:
                return func(*args, **kwargs)
            except exceptions.ResourceExhausted:
                wait_time = (2 ** attempt) + 2
                logger.warning(f"Límite alcanzado. Reintentando en {wait_time}s...")
                time.sleep(wait_time)
        raise Exception("Gemini API: Cuota agotada definitivamente.")

    def answer_question(self, query: str, user_id: str):
        chat = self._get_user_session(user_id)

        # 1. Recuperación Vectorial
        query_embedding = self.embedding_service.generate_embedding(query, is_query=True)
        results = self.vector_store.search_similar(query_embedding, limit=10)

        # DEBUG
        for res in results:
            logger.info(f"Candidato - Score: {res.get('score')} - Content: {res['content'][:50]}...")

        relevant_docs = [r for r in results if r.get("score", 0) >= 0.40] 

        if not relevant_docs:
            if results:
                logger.warning("Usando top 2 por fallback.")
                relevant_docs = results[:2]
            else:
                return {"answer": "No encontré información oficial.", "sources": []}

        # --- AQUÍ ESTABA EL ERROR: Faltaba retornar la respuesta final ---
        
        # 2. Construcción de Contexto
        context = build_context(relevant_docs)
        
        # 3. Generación con Contexto (Llamada a Gemini)
        prompt = f"{SYSTEM_PROMPT}\nCONTEXTO OFICIAL:\n{context}\nPREGUNTA: {query}"
        
        # Usamos safe_execute para el envío del mensaje
        response = self.safe_execute(chat.send_message, prompt)

        return {
            "answer": response.text,
            "sources": [r["metadata"] for r in relevant_docs],
            "confidence_top": results[0].get("score") if results else 0
        }
    def safe_generate_content(self, prompt):
        for attempt in range(5):
            try:
                return self.model.generate_content(prompt)
            except exceptions.ResourceExhausted:
                wait_time = (2 ** attempt) + 5 
                logger.warning(f"Esperando {wait_time}s por cuota...")
                time.sleep(wait_time)
        raise Exception("Cuota excedida.")
    def generate_title(self, query: str):
        """Genera un título corto para la conversación."""
        try:
            prompt = f"Genera un título corto (máximo 6 palabras) para esta consulta: {query}"
            # Usamos safe_generate_content para evitar el error 429 también aquí
            response = self.safe_generate_content(prompt)
            return response.text.strip().replace('"', '')
        except Exception:
            return "Nueva Consulta SICT"

    def _get_user_session(self, user_id: str) -> genai.ChatSession:
        """Maneja el historial de chat por usuario."""
        if user_id not in self.user_sessions:
            # Iniciamos sesión con el modelo configurado
            self.user_sessions[user_id] = self.model.start_chat(history=[])
        return self.user_sessions[user_id]