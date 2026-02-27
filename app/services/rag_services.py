import google.generativeai as genai
from app.core.config import settings
from typing import List, Dict

genai.configure(api_key=settings.GEMINI_API)

def build_context(results, max_chars=6000):
    sorted_results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)
    context = ""
    for r in sorted_results:
        piece = f"\nFuente: {r['metadata'].get('source', 'Desconocido')}\nContenido:\n{r['content']}\n"
        if len(context) + len(piece) > max_chars:
            break
        context += piece
    return context.strip()

SYSTEM_PROMPT = """
Eres un asistente experto institucional de la SICT.
Tu objetivo es ayudar a los usuarios basándote en documentos oficiales.
Responde únicamente usando el CONTEXTO proporcionado y el historial de la conversación.
Si la respuesta no está en el contexto, responde exactamente:
"No se encontró información suficiente en los documentos institucionales."

No inventes información. No asumas. Sé claro, preciso y profesional.
"""

class RAGService:
    def __init__(self, embedding_service, vector_store):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.model = genai.GenerativeModel("models/gemini-1.5-flash")
        self.sessions: Dict[str, genai.ChatSession] = {}

    def _get_chat_session(self, session_id: str) -> genai.ChatSession:
        """Obtiene o crea una sesión de chat con el System Prompt configurado."""
        if session_id not in self.sessions:
            self.sessions[session_id] = self.model.start_chat(history=[])
        return self.sessions[session_id]

    def answer_question(self, query: str, session_id: str = "default"):
        chat = self._get_chat_session(session_id)
        query_embedding = self.embedding_service.generate_embedding(query, is_query=True)
        results = self.vector_store.search_similar(
            query_embedding=query_embedding,
            limit=7
        )
        relevant_results = [r for r in results if r.get("score", 0) >= 0.70]

        if not relevant_results:
            context = "No se encontró información nueva en los documentos."
        else:
            context = build_context(relevant_results)

        prompt_with_context = f"""
        {SYSTEM_PROMPT}

        CONTEXTO ACTUALIZADO:
        {context}

        PREGUNTA DEL USUARIO:
        {query}
        """
        response = chat.send_message(prompt_with_context)

        return {
            "answer": response.text,
            "sources": [r["metadata"] for r in relevant_results],
            "session_id": session_id
        }