import google.generativeai as genai
from app.core.config import settings
genai.configure(api_key=settings.GEMINI_API)
def build_context(results, max_chars=6000):

    sorted_results = sorted(results, key=lambda x: x["score"], reverse=True)

    context = ""
    for r in sorted_results:
        piece = f"\nFuente: {r['metadata'].get('source')}\nContenido:\n{r['content']}\n"
        
        if len(context) + len(piece) > max_chars:
            break
        
        context += piece

    return context.strip()
SYSTEM_PROMPT = """
Eres un asistente experto institucional.
Responde únicamente usando el contexto proporcionado.
Si la respuesta no está en el contexto, responde:
"No se encontró información suficiente en los documentos institucionales."

No inventes información.
No asumas.
Sé claro, preciso y profesional.
"""
class RAGService:

    def __init__(self, embedding_service, vector_store):
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    def answer_question(self, query: str):

        # 1️⃣ Generar embedding de consulta
        query_embedding = self.embedding_service.generate_embedding(query, is_query=True)

        # 2️⃣ Buscar similares
        results = self.vector_store.search_similar(
            query_embedding=query_embedding,
            limit=7,
            score_threshold=0.70
        )

        if not results:
            return {
                "answer": "No se encontró información relevante en los documentos.",
                "sources": []
            }
        context = build_context(results)

        prompt = f"""
        {SYSTEM_PROMPT}

        CONTEXTO:
        {context}

        PREGUNTA:
        {query}

        RESPUESTA:
        """

        model = genai.GenerativeModel("models/gemini-2.5-flash")

        response = model.generate_content(prompt)

        return {
            "answer": response.text,
            "sources": [r["metadata"] for r in results]
        }