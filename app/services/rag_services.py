import google.generativeai as genai
from app.core.config import settings
from typing import List, Dict

genai.configure(api_key=settings.GEMINI_API)

def build_context(results, max_chars=6000):
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
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

        self.user_sessions: Dict[str, genai.ChatSession] = {}

    def _get_user_session(self, user_id: str) -> genai.ChatSession:
        """Recupera la sesión de chat específica del usuario o crea una nueva."""
        if user_id not in self.user_sessions:
            # Iniciamos chat limpio para el nuevo usuario identificado
            self.user_sessions[user_id] = self.model.start_chat(history=[])
        return self.user_sessions[user_id]

    def answer_question(self, query: str, user_id: str):
        """
        Procesa la pregunta vinculándola a un ID de usuario de MongoDB.
        """

        chat = self._get_user_session(user_id)


        query_embedding = self.embedding_service.generate_embedding(query, is_query=True)
        results = self.vector_store.search_similar(
            query_embedding=query_embedding,
            limit=7
        )


        relevant_results = [r for r in results if r.get("score", 0) >= 0.70]

        if not relevant_results:
            context = "No se encontró información relevante en los documentos para esta consulta específica."
        else:
            context = build_context(relevant_results)


        prompt_with_context = f"""
        {SYSTEM_PROMPT}

        CONTEXTO OFICIAL:
        {context}

        PREGUNTA DEL USUARIO:
        {query}
        """

        response = chat.send_message(prompt_with_context)

        return {
            "answer": response.text,
            "sources": [r["metadata"] for r in relevant_results],
            "user_id": user_id,  
            "confidence_top": relevant_results[0].get("score") if relevant_results else 0
        }
    def generate_title(self, query: str):
        prompt = f"Genera un título corto (máximo 6 palabras) para esta conversación: {query}"
        response = self.model.generate_content(prompt)
        return response.text.strip()