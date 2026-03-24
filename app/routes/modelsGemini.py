from fastapi import APIRouter, HTTPException
import google.generativeai as genai
from app.core.config import settings
from typing import List, Dict

router = APIRouter()

genai.configure(api_key=settings.GEMINI_API)

@router.get("/api/gemini-models")
async def get_available_models():
    """
    Lista todos los modelos de Gemini disponibles para la API Key configurada,
    filtrando por aquellos que soportan generación de contenido.
    """
    try:
        available_models = []
        
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                model_data = {
                    "id": m.name,
                    "display_name": m.display_name,
                    "description": m.description,
                    "input_token_limit": m.input_token_limit,
                    "output_token_limit": m.output_token_limit,
                    "supported_methods": m.supported_generation_methods
                }
                available_models.append(model_data)
        
        return {
            "total_models": len(available_models),
            "models": available_models
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error al conectar con Google Generative AI: {str(e)}"
        )