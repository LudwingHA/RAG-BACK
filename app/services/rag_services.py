# app/services/rag_services.py

import google.generativeai as genai
from app.core.config import settings
from typing import List, Dict, Any, Optional
import logging
from google.api_core import exceptions
import time
import hashlib
from datetime import datetime, timedelta
from pymongo import MongoClient, ASCENDING, DESCENDING
import re
import json

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GEMINI_API)

def build_context(results, max_chars=3000):
    """Construye el bloque de texto con las fuentes encontradas."""
    sorted_results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)
    context = ""
    for r in sorted_results:
        source = r['metadata'].get('source', 'Documento SICT')
        doc_type = r['metadata'].get('tipo_documento', 'General')
        sheet = f" - {r['metadata'].get('sheet')}" if r['metadata'].get('sheet') else ""
        page = f" (Pág. {r['metadata'].get('page')})" if r['metadata'].get('page') else ""
        
        piece = f"\n[Fuente: {source}{sheet}{page} | Tipo: {doc_type}]\nContenido:\n{r['content']}\n"
        
        if len(context) + len(piece) > max_chars:
            break
        context += piece
    return context.strip()

SYSTEM_PROMPT = """
Eres un asistente experto institucional de la Secretaría de Infraestructura, Comunicaciones y Transportes (SICT).
Tu objetivo es ayudar a los usuarios basándote exclusivamente en la documentación oficial proporcionada.

TIPOS DE DOCUMENTOS DISPONIBLES:
- Obras y proyectos de infraestructura
- Reportes de baches y mantenimiento vial
- Presupuestos y ejercicios fiscales
- Contratos y licitaciones
- Personal y recursos humanos
- Normativas y reglamentos
- Inventarios y activos
- Permisos y concesiones
- Estadísticas y reportes

REGLAS DE ORO:
1. Responde únicamente usando el CONTEXTO proporcionado
2. Si la respuesta no está en el contexto, responde: "No se encontró información suficiente en los documentos institucionales."
3. Mantén un tono formal, claro y profesional
4. Si encuentras datos numéricos o estadísticos, preséntalos de forma clara
5. Para información de obras/proyectos, incluye ubicación, fechas y montos si están disponibles
6. No menciones el 'Contexto' directamente al usuario
"""

class CacheManager:
    """
    Gestor de cache inteligente para preguntas y respuestas.
    Almacena en MongoDB y memoria para acceso rápido.
    """
    
    def __init__(self, mongo_client, db_name: str, ttl_horas: int = 24):
        self.ttl_segundos = ttl_horas * 3600
        self.memory_cache = {}
        self.memory_cache_size = 200
        
        self.db = mongo_client[db_name]
        self.cache_collection = self.db["respuestas_cache"]
        
        self._crear_indices()
        logger.info(f"✅ CacheManager inicializado - TTL: {ttl_horas} horas")
    
    def _crear_indices(self):
        try:
            self.cache_collection.create_index([("query_hash", ASCENDING)], unique=True)
            self.cache_collection.create_index([("timestamp", ASCENDING)], expireAfterSeconds=self.ttl_segundos)
            self.cache_collection.create_index([("ultimo_acceso", DESCENDING)])
            self.cache_collection.create_index([("frecuencia", DESCENDING)])
            self.cache_collection.create_index([("user_id", ASCENDING)])
            self.cache_collection.create_index([("tipo_consulta", ASCENDING)])
            logger.info("✅ Índices de cache creados")
        except Exception as e:
            logger.warning(f"Error creando índices: {e}")
    
    def _generar_query_hash(self, query: str, user_id: str = None) -> str:
        """Genera hash único para la consulta"""
        query_normalized = ' '.join(query.lower().split())
        query_normalized = re.sub(r'[^\w\s]', '', query_normalized)
        hash_input = f"{query_normalized}_{user_id}" if user_id else query_normalized
        return hashlib.sha256(hash_input.encode()).hexdigest()
    
    def _detectar_tipo_consulta(self, query: str) -> str:
        """Detecta el tipo de consulta para mejor organización"""
        query_lower = query.lower()
        
        tipos = {
            'obra': ['obra', 'proyecto', 'construcción', 'infraestructura', 'carretera', 'puente', 'vial'],
            'bache': ['bache', 'baches', 'mantenimiento vial', 'reparación', 'pavimento'],
            'presupuesto': ['presupuesto', 'costo', 'gasto', 'inversión', 'monto', 'millones', 'pesos'],
            'personal': ['persona', 'empleado', 'trabajador', 'funcionario', 'director', 'encargado'],
            'contrato': ['contrato', 'licitación', 'proveedor', 'adjudicación'],
            'normativa': ['norma', 'reglamento', 'ley', 'lineamiento', 'procedimiento'],
            'estadistica': ['estadística', 'dato', 'indicador', 'métrica', 'reporte'],
            'inventario': ['inventario', 'bien', 'activo', 'equipo', 'maquinaria'],
            'permiso': ['permiso', 'concesión', 'autorización', 'licencia']
        }
        
        for tipo, patrones in tipos.items():
            if any(patron in query_lower for patron in patrones):
                return tipo
        
        return 'general'
    
    def obtener(self, query: str, user_id: str = None) -> Optional[Dict]:
        """Obtiene una respuesta del cache"""
        query_hash = self._generar_query_hash(query, user_id)
        
        # 1. Buscar en memoria
        if query_hash in self.memory_cache:
            cached = self.memory_cache[query_hash]
            if time.time() - cached['timestamp'] < self.ttl_segundos:
                logger.info(f"🎯 Cache HIT (Memoria): {query[:50]}...")
                self._actualizar_estadisticas(query_hash, cached)
                return cached['respuesta']
            else:
                del self.memory_cache[query_hash]
        
        # 2. Buscar en MongoDB
        try:
            cached = self.cache_collection.find_one({"query_hash": query_hash})
            if cached:
                if time.time() - cached['timestamp'] < self.ttl_segundos:
                    logger.info(f"🎯 Cache HIT (MongoDB): {query[:50]}...")
                    self._guardar_en_memoria(query_hash, cached)
                    
                    self.cache_collection.update_one(
                        {"_id": cached['_id']},
                        {
                            "$inc": {"frecuencia": 1},
                            "$set": {"ultimo_acceso": time.time()}
                        }
                    )
                    return cached['respuesta']
                else:
                    self.cache_collection.delete_one({"_id": cached['_id']})
        except Exception as e:
            logger.warning(f"Error buscando en MongoDB: {e}")
        
        logger.info(f"❌ Cache MISS: {query[:50]}...")
        return None
    
    def guardar(self, query: str, respuesta: Dict, user_id: str = None):
        """Guarda una respuesta en cache"""
        query_hash = self._generar_query_hash(query, user_id)
        tipo_consulta = self._detectar_tipo_consulta(query)
        
        cache_data = {
            'query': query,
            'query_hash': query_hash,
            'respuesta': respuesta,
            'timestamp': time.time(),
            'ultimo_acceso': time.time(),
            'frecuencia': 1,
            'user_id': user_id,
            'tipo_consulta': tipo_consulta,
            'metadata': {
                'longitud_query': len(query),
                'palabras_clave': self._extraer_palabras_clave(query),
                'modelo_usado': respuesta.get('model_used', 'unknown'),
                'total_resultados': respuesta.get('total_resultados', 0)
            }
        }
        
        # Guardar en MongoDB
        try:
            self.cache_collection.update_one(
                {"query_hash": query_hash},
                {"$set": cache_data},
                upsert=True
            )
            logger.info(f"💾 Cache guardado en MongoDB: {query[:50]}...")
        except Exception as e:
            logger.warning(f"Error guardando en MongoDB: {e}")
        
        # Guardar en memoria
        self._guardar_en_memoria(query_hash, cache_data)
    
    def _guardar_en_memoria(self, query_hash: str, cache_data: Dict):
        self.memory_cache[query_hash] = cache_data
        if len(self.memory_cache) > self.memory_cache_size:
            self._limpiar_memoria()
    
    def _limpiar_memoria(self):
        items_ordenados = sorted(
            self.memory_cache.items(),
            key=lambda x: (x[1].get('frecuencia', 0), x[1].get('ultimo_acceso', 0)),
            reverse=True
        )
        self.memory_cache = dict(items_ordenados[:self.memory_cache_size])
        logger.info(f"🧹 Memoria cache limpiada: {len(self.memory_cache)} items")
    
    def _actualizar_estadisticas(self, query_hash: str, cache_data: Dict):
        try:
            cache_data['frecuencia'] = cache_data.get('frecuencia', 1) + 1
            cache_data['ultimo_acceso'] = time.time()
            
            self.cache_collection.update_one(
                {"query_hash": query_hash},
                {
                    "$inc": {"frecuencia": 1},
                    "$set": {"ultimo_acceso": time.time()}
                }
            )
        except:
            pass
    
    def _extraer_palabras_clave(self, query: str) -> List[str]:
        stopwords = {'el', 'la', 'los', 'las', 'de', 'del', 'y', 'o', 'a', 'ante', 'bajo',
                     'con', 'contra', 'desde', 'en', 'entre', 'hacia', 'hasta', 'para',
                     'por', 'segun', 'sin', 'sobre', 'tras', 'un', 'una', 'unos', 'unas',
                     'me', 'mi', 'tu', 'su', 'nos', 'les', 'que', 'cual', 'como'}
        
        palabras = re.findall(r'\b\w{4,}\b', query.lower())
        return [p for p in palabras if p not in stopwords][:5]
    
    def obtener_estadisticas(self) -> Dict:
        try:
            total_mongodb = self.cache_collection.count_documents({})
            
            # Estadísticas por tipo de consulta
            pipeline = [
                {"$group": {
                    "_id": "$tipo_consulta",
                    "count": {"$sum": 1},
                    "total_frecuencia": {"$sum": "$frecuencia"}
                }},
                {"$sort": {"count": -1}}
            ]
            tipos_stats = list(self.cache_collection.aggregate(pipeline))
            
            # Top preguntas más frecuentes
            top_preguntas = list(self.cache_collection.find(
                {},
                {"query": 1, "frecuencia": 1, "tipo_consulta": 1, "ultimo_acceso": 1}
            ).sort("frecuencia", -1).limit(10))
            
            for p in top_preguntas:
                p['_id'] = str(p['_id'])
            
            return {
                'en_memoria': len(self.memory_cache),
                'en_mongodb': total_mongodb,
                'por_tipo': tipos_stats,
                'top_preguntas': top_preguntas,
                'ttl_horas': self.ttl_segundos / 3600
            }
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return {'error': str(e)}
    
    def limpiar_usuario(self, user_id: str = None) -> int:
        query = {"user_id": user_id} if user_id else {}
        try:
            result = self.cache_collection.delete_many(query)
            if user_id:
                to_delete = [k for k, v in self.memory_cache.items() 
                           if v.get('user_id') == user_id]
                for k in to_delete:
                    del self.memory_cache[k]
            else:
                self.memory_cache.clear()
            logger.info(f"🧹 Cache limpiado: {result.deleted_count} registros")
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error limpiando cache: {e}")
            return 0

class RAGService:
    """
    Servicio RAG principal para TODOS los documentos SICT.
    """
    
    def __init__(self, embedding_service, vector_store):
        from app.services.embedding_service import LocalEmbeddingService
        
        self.embedding_service = LocalEmbeddingService()
        self.vector_store = vector_store
        self.model = genai.GenerativeModel("models/gemini-1.5-flash")
        self.user_sessions: Dict[str, genai.ChatSession] = {}
        
        if hasattr(vector_store, 'client'):
            self.cache_manager = CacheManager(
                mongo_client=vector_store.client,
                db_name=settings.DB_NAME,
                ttl_horas=24
            )
            logger.info("✅ Sistema de cache inteligente inicializado")
        else:
            self.cache_manager = None
            logger.warning("⚠️ Cache no disponible")

    def safe_execute(self, func, *args, **kwargs):
        """Maneja límites de Gemini"""
        for attempt in range(5):
            try:
                return func(*args, **kwargs)
            except exceptions.ResourceExhausted:
                wait_time = (2 ** attempt) + 2
                logger.warning(f"Límite alcanzado. Reintentando en {wait_time}s...")
                time.sleep(wait_time)
        raise Exception("Gemini API: Cuota agotada definitivamente.")

    def _generar_respuesta_fallback_generica(self, query: str, relevant_docs: List[Dict]) -> str:
        """
        Genera respuesta FALLBACK para CUALQUIER tipo de documento.
        Analiza el contenido y estructura la respuesta apropiadamente.
        """
        if not relevant_docs:
            return "No se encontró información relevante en los documentos."
        
        # Analizar los documentos para determinar el tipo de contenido
        tipos_contenido = set()
        palabras_clave_totales = []
        tiene_numeros = False
        tiene_fechas = False
        total_registros = len(relevant_docs)
        
        # Primer pase: análisis de contenido
        for doc in relevant_docs:
            contenido = doc['content']
            metadata = doc.get('metadata', {})
            
            # Detectar tipo por metadata
            if 'tipo_documento' in metadata:
                tipos_contenido.add(metadata['tipo_documento'])
            
            # Detectar números
            if re.search(r'\d+\.?\d*', str(contenido)):
                tiene_numeros = True
            
            # Detectar fechas
            if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', str(contenido)):
                tiene_fechas = True
            
            # Extraer palabras clave del contenido
            palabras = re.findall(r'\b[A-ZÁÉÍÓÚÑ]{4,}\b', str(contenido).upper())
            palabras_clave_totales.extend(palabras[:10])
        
        # Detectar tipo de consulta
        query_lower = query.lower()
        
        # ===== RESPUESTAS ESPECIALIZADAS POR TIPO =====
        
        # 1. OBRAS/INFRAESTRUCTURA
        if any(word in query_lower for word in ['obra', 'proyecto', 'carretera', 'puente', 'construcción']):
            return self._formatear_respuesta_obras(relevant_docs)
        
        # 2. BACHES/MANTENIMIENTO
        elif any(word in query_lower for word in ['bache', 'baches', 'mantenimiento', 'reparación']):
            return self._formatear_respuesta_baches(relevant_docs)
        
        # 3. PRESUPUESTOS/FINANZAS
        elif any(word in query_lower for word in ['presupuesto', 'costo', 'gasto', 'inversión', 'millones', 'pesos']):
            return self._formatear_respuesta_presupuestos(relevant_docs)
        
        # 4. PERSONAL/RECURSOS HUMANOS
        elif any(word in query_lower for word in ['personal', 'empleado', 'trabajador', 'funcionario', 'director']):
            return self._formatear_respuesta_personal(relevant_docs)
        
        # 5. CONTRATOS/LICITACIONES
        elif any(word in query_lower for word in ['contrato', 'licitación', 'proveedor']):
            return self._formatear_respuesta_contratos(relevant_docs)
        
        # 6. NORMATIVAS/REGLAMENTOS
        elif any(word in query_lower for word in ['norma', 'reglamento', 'ley', 'lineamiento']):
            return self._formatear_respuesta_normativas(relevant_docs)
        
        # 7. ESTADÍSTICAS/REPORTES
        elif any(word in query_lower for word in ['estadística', 'reporte', 'dato', 'indicador']):
            return self._formatear_respuesta_estadisticas(relevant_docs)
        
        # 8. INVENTARIOS/ACTIVOS
        elif any(word in query_lower for word in ['inventario', 'bien', 'activo', 'equipo']):
            return self._formatear_respuesta_inventarios(relevant_docs)
        
        # 9. RESPUESTA GENÉRICA PARA OTROS TIPOS
        else:
            return self._formatear_respuesta_generica(relevant_docs, query)
    
    def _formatear_respuesta_obras(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de obras"""
        respuesta = "**🏗️ INFORMACIÓN DE OBRAS Y PROYECTOS SICT**\n\n"
        
        for i, doc in enumerate(docs[:5], 1):
            metadata = doc.get('metadata', {})
            contenido = doc['content']
            
            respuesta += f"**Obra/Proyecto {i}**\n"
            
            # Intentar extraer información estructurada
            if ' | ' in str(contenido):
                partes = str(contenido).split(' | ')
                for parte in partes[:6]:  # Limitar a 6 campos
                    respuesta += f"• {parte}\n"
            else:
                # Si no está estructurado, mostrar primeros 200 caracteres
                respuesta += f"• {str(contenido)[:200]}...\n"
            
            # Añadir metadatos relevantes
            if metadata.get('sheet'):
                respuesta += f"• Hoja: {metadata.get('sheet')}\n"
            if metadata.get('ubicacion'):
                respuesta += f"• Ubicación: {metadata.get('ubicacion')}\n"
            
            respuesta += "\n"
        
        if len(docs) > 5:
            respuesta += f"*... y {len(docs) - 5} documentos más*"
        
        return respuesta
    
    def _formatear_respuesta_baches(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de baches"""
        respuesta = "**🕳️ REPORTES DE BACHES Y MANTENIMIENTO VIAL**\n\n"
        
        total_baches = 0
        ubicaciones = set()
        
        for doc in docs:
            contenido = str(doc['content'])
            
            # Intentar extraer números
            numeros = re.findall(r'\d+', contenido)
            if numeros:
                total_baches += sum(int(n) for n in numeros[:3])  # Sumar primeros números
            
            # Intentar extraer ubicaciones
            lineas = contenido.split('\n')
            for linea in lineas:
                if any(palabra in linea.upper() for palabra in ['UBICACIÓN', 'DIRECCIÓN', 'CALLE', 'AVENIDA']):
                    ubicaciones.add(linea[:100])
        
        if total_baches > 0:
            respuesta += f"**Total aproximado:** {total_baches} baches reportados\n\n"
        
        if ubicaciones:
            respuesta += "**Ubicaciones mencionadas:**\n"
            for ubicacion in list(ubicaciones)[:5]:
                respuesta += f"• {ubicacion}\n"
            respuesta += "\n"
        
        # Detalles de los reportes
        respuesta += "**Detalles de reportes recientes:**\n\n"
        for i, doc in enumerate(docs[:3], 1):
            contenido = str(doc['content'])[:200]
            respuesta += f"**Reporte {i}:**\n{contenido}...\n\n"
        
        return respuesta
    
    def _formatear_respuesta_presupuestos(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de presupuestos"""
        respuesta = "**💰 INFORMACIÓN PRESUPUESTAL SICT**\n\n"
        
        total_montos = []
        
        for doc in docs:
            contenido = str(doc['content'])
            
            # Buscar montos en diferentes formatos
            montos = re.findall(r'\$?\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s?(?:millones|mdp|pesos)?', contenido)
            for monto in montos:
                # Limpiar y convertir
                monto_limpio = monto.replace(',', '')
                try:
                    total_montos.append(float(monto_limpio))
                except:
                    pass
        
        if total_montos:
            respuesta += f"**Montos identificados:**\n"
            respuesta += f"• Total aproximado: ${sum(total_montos):,.2f}\n"
            respuesta += f"• Monto promedio: ${sum(total_montos)/len(total_montos):,.2f}\n"
            respuesta += f"• Rango: ${min(total_montos):,.2f} - ${max(total_montos):,.2f}\n\n"
        
        respuesta += "**Documentos presupuestales encontrados:**\n\n"
        for i, doc in enumerate(docs[:3], 1):
            fuente = doc['metadata'].get('source', 'Documento')
            sheet = doc['metadata'].get('sheet', '')
            contenido = str(doc['content'])[:150]
            
            respuesta += f"**{i}. {fuente}**"
            if sheet:
                respuesta += f" - {sheet}"
            respuesta += f"\n{contenido}...\n\n"
        
        return respuesta
    
    def _formatear_respuesta_personal(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de personal"""
        respuesta = "**👥 INFORMACIÓN DE PERSONAL SICT**\n\n"
        
        personas = []
        puestos = set()
        
        for doc in docs:
            contenido = str(doc['content'])
            datos = {}
            
            # Parsear contenido estructurado
            if ' | ' in contenido:
                for parte in contenido.split(' | '):
                    if ':' in parte:
                        key, value = parte.split(':', 1)
                        datos[key.strip()] = value.strip()
                        
                        if key.strip().upper() in ['PUESTO', 'CARGO']:
                            puestos.add(value.strip())
            
            if datos:
                personas.append(datos)
        
        if puestos:
            respuesta += "**Puestos identificados:**\n"
            for puesto in list(puestos)[:5]:
                respuesta += f"• {puesto}\n"
            respuesta += "\n"
        
        respuesta += "**Registros encontrados:**\n\n"
        for i, persona in enumerate(personas[:5], 1):
            nombre = persona.get('NOMBRE', persona.get('nombre', ''))
            apellido = persona.get('APELLIDO', persona.get('apellido', ''))
            puesto = persona.get('PUESTO', persona.get('CARGO', 'No especificado'))
            
            respuesta += f"**{i}. {nombre} {apellido}**".strip()
            if len(respuesta.split('\n')[-1]) < 10:  # Si no hay nombre
                respuesta += f"**Registro {i}**"
            
            respuesta += f"\n   • Puesto: {puesto}\n"
            
            # Otros datos relevantes
            for key, value in persona.items():
                if key.upper() not in ['NOMBRE', 'APELLIDO', 'PUESTO', 'CARGO']:
                    respuesta += f"   • {key}: {value}\n"
            respuesta += "\n"
        
        return respuesta
    
    def _formatear_respuesta_contratos(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de contratos"""
        respuesta = "**📄 CONTRATOS Y LICITACIONES SICT**\n\n"
        
        for i, doc in enumerate(docs[:3], 1):
            metadata = doc.get('metadata', {})
            contenido = str(doc['content'])
            
            respuesta += f"**Contrato/Licitación {i}**\n"
            respuesta += f"• Fuente: {metadata.get('source', 'No especificada')}\n"
            
            # Buscar números de contrato
            numeros_contrato = re.findall(r'(?:contrato|licitación)\s*(?:n[úo]m\.?)?\s*:?\s*([A-Z0-9-]+)', contenido, re.IGNORECASE)
            if numeros_contrato:
                respuesta += f"• Número: {numeros_contrato[0]}\n"
            
            # Buscar montos
            montos = re.findall(r'\$?\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', contenido)
            if montos:
                respuesta += f"• Monto: ${montos[0]}\n"
            
            # Buscar fechas
            fechas = re.findall(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', contenido)
            if fechas:
                respuesta += f"• Fecha: {fechas[0]}\n"
            
            respuesta += "\n"
        
        return respuesta
    
    def _formatear_respuesta_normativas(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de normativas"""
        respuesta = "**📚 NORMATIVAS Y REGLAMENTOS SICT**\n\n"
        
        for i, doc in enumerate(docs[:5], 1):
            metadata = doc.get('metadata', {})
            contenido = str(doc['content'])
            
            respuesta += f"**Documento {i}:** {metadata.get('source', 'Normativa')}\n"
            
            # Buscar artículos o secciones
            articulos = re.findall(r'(?:artículo|art\.?)\s*(\d+)', contenido, re.IGNORECASE)
            if articulos:
                respuesta += f"• Artículos mencionados: {', '.join(articulos[:3])}\n"
            
            # Mostrar primeras líneas relevantes
            lineas = contenido.split('\n')[:3]
            for linea in lineas:
                if len(linea.strip()) > 20:  # Solo líneas con contenido
                    respuesta += f"• {linea[:100]}...\n"
            
            respuesta += "\n"
        
        return respuesta
    
    def _formatear_respuesta_estadisticas(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de estadísticas"""
        respuesta = "**📊 ESTADÍSTICAS Y REPORTES SICT**\n\n"
        
        todos_numeros = []
        
        for doc in docs:
            contenido = str(doc['content'])
            
            # Extraer todos los números
            numeros = re.findall(r'\d+(?:\.\d+)?', contenido)
            numeros_float = [float(n) for n in numeros if len(n) < 10]  # Ignorar IDs muy largos
            todos_numeros.extend(numeros_float)
        
        if todos_numeros:
            respuesta += f"**Resumen estadístico:**\n"
            respuesta += f"• Total de datos numéricos: {len(todos_numeros)}\n"
            respuesta += f"• Promedio: {sum(todos_numeros)/len(todos_numeros):.2f}\n"
            respuesta += f"• Mínimo: {min(todos_numeros):.2f}\n"
            respuesta += f"• Máximo: {max(todos_numeros):.2f}\n\n"
        
        respuesta += "**Reportes encontrados:**\n\n"
        for i, doc in enumerate(docs[:3], 1):
            metadata = doc.get('metadata', {})
            contenido = str(doc['content'])[:150]
            
            respuesta += f"**{i}. {metadata.get('source', 'Reporte')}**\n"
            respuesta += f"{contenido}...\n\n"
        
        return respuesta
    
    def _formatear_respuesta_inventarios(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de inventarios"""
        respuesta = "**📦 INVENTARIOS Y ACTIVOS SICT**\n\n"
        
        items = []
        
        for doc in docs:
            contenido = str(doc['content'])
            
            # Buscar patrones de items en inventario
            if ' | ' in contenido:
                items.append(contenido[:150])
            else:
                # Si es texto plano, tomar primeras líneas
                lineas = contenido.split('\n')[:3]
                items.extend([l for l in lineas if len(l.strip()) > 20])
        
        respuesta += f"**Total de registros de inventario:** {len(docs)}\n\n"
        
        if items:
            respuesta += "**Items identificados:**\n"
            for i, item in enumerate(items[:10], 1):
                respuesta += f"{i}. {item[:80]}...\n"
        
        return respuesta
    
    def _formatear_respuesta_generica(self, docs: List[Dict], query: str) -> str:
        """Formatea respuesta genérica para cualquier otro tipo de documento"""
        respuesta = f"**📑 INFORMACIÓN ENCONTRADA EN DOCUMENTOS SICT**\n\n"
        respuesta += f"**Consulta:** {query}\n"
        respuesta += f"**Documentos relevantes:** {len(docs)}\n\n"
        
        for i, doc in enumerate(docs[:5], 1):
            metadata = doc.get('metadata', {})
            contenido = str(doc['content'])
            
            fuente = metadata.get('source', 'Documento')
            tipo = metadata.get('tipo_documento', metadata.get('format', 'General'))
            sheet = metadata.get('sheet', '')
            
            respuesta += f"**Documento {i}:** {fuente}\n"
            respuesta += f"**Tipo:** {tipo}\n"
            if sheet:
                respuesta += f"**Sección:** {sheet}\n"
            
            # Mostrar preview del contenido
            preview = contenido[:200] + "..." if len(contenido) > 200 else contenido
            respuesta += f"**Contenido:**\n{preview}\n\n"
        
        if len(docs) > 5:
            respuesta += f"*... y {len(docs) - 5} documentos más*"
        
        return respuesta

    def answer_question(self, query: str, user_id: str) -> Dict:
        """
        Responde una pregunta usando RAG con cache inteligente.
        """
        start_time = time.time()
        
        # ===== 1. VERIFICAR CACHE =====
        if self.cache_manager:
            cached_response = self.cache_manager.obtener(query, user_id)
            if cached_response:
                cached_response['from_cache'] = True
                cached_response['tiempo_respuesta_ms'] = round((time.time() - start_time) * 1000)
                cached_response['cache_hit'] = True
                logger.info(f"⚡ Respuesta desde cache en {cached_response['tiempo_respuesta_ms']}ms")
                return cached_response
        
        # ===== 2. RECUPERACIÓN VECTORIAL =====
        chat = self._get_user_session(user_id)
        
        query_embedding = self.embedding_service.generate_embedding(query, is_query=True)
        results = self.vector_store.search_similar(query_embedding, limit=15)

        logger.info(f"Total de resultados: {len(results)}")
        for res in results[:5]:
            logger.info(f"Candidato - Score: {res.get('score', 0):.4f} - Tipo: {res.get('metadata', {}).get('tipo_documento', 'N/A')}")

        if not results:
            respuesta_base = {
                "answer": "No se encontró información en los documentos institucionales.",
                "sources": [],
                "confidence_top": 0,
                "total_resultados": 0,
                "tipo_documentos": []
            }
            
            if self.cache_manager:
                self.cache_manager.guardar(query, respuesta_base, user_id)
            
            respuesta_base['tiempo_respuesta_ms'] = round((time.time() - start_time) * 1000)
            respuesta_base['from_cache'] = False
            return respuesta_base

        relevant_docs = results[:5] if len(results) >= 5 else results
        context = build_context(relevant_docs)
        
        # Detectar tipos de documentos para logging
        tipos_docs = list(set([r['metadata'].get('tipo_documento', 'General') for r in relevant_docs]))
        
        prompt = f"""{SYSTEM_PROMPT}

CONTEXTO OFICIAL (documentos recuperados):
{context}

PREGUNTA DEL USUARIO: {query}

INSTRUCCIONES ESPECÍFICAS:
- Utiliza EXCLUSIVAMENTE la información del contexto
- Si el contexto contiene datos de obras, presupuestos, personal u otros, adáptate
- Para datos numéricos, preséntalos de forma clara
- Si encuentras información parcial, sé honesto al respecto

RESPUESTA:
"""
        
        # ===== 3. INTENTAR CON GEMINI =====
        try:
            response = self.safe_execute(chat.send_message, prompt)
            
            respuesta_final = {
                "answer": response.text,
                "sources": [r["metadata"] for r in relevant_docs],
                "confidence_top": results[0].get("score") if results else 0,
                "total_resultados": len(results),
                "tipo_documentos": tipos_docs,
                "model_used": "gemini",
                "from_cache": False
            }
            
        except Exception as e:
            logger.error(f"Error con Gemini, usando fallback: {e}")
            
            # ===== 4. FALLBACK GENÉRICO =====
            fallback_answer = self._generar_respuesta_fallback_generica(query, relevant_docs)
            
            respuesta_final = {
                "answer": fallback_answer,
                "sources": [r["metadata"] for r in relevant_docs],
                "confidence_top": results[0].get("score") if results else 0,
                "total_resultados": len(results),
                "tipo_documentos": tipos_docs,
                "model_used": "fallback_generico",
                "error_gemini": str(e),
                "from_cache": False
            }
        
        # ===== 5. GUARDAR EN CACHE =====
        if self.cache_manager:
            self.cache_manager.guardar(query, respuesta_final, user_id)
            logger.info(f"💾 Respuesta guardada en cache para: {query[:50]}...")
        
        respuesta_final['tiempo_respuesta_ms'] = round((time.time() - start_time) * 1000)
        
        return respuesta_final

    def safe_generate_content(self, prompt):
        for attempt in range(5):
            try:
                return self.model.generate_content(prompt)
            except exceptions.ResourceExhausted:
                wait_time = (2 ** attempt) + 5 
                logger.warning(f"Esperando {wait_time}s por cuota...")
                time.sleep(wait_time)
        raise Exception("Cuota excedida.")
    
    def generate_title(self, query: str) -> str:
        try:
            prompt = f"Genera un título corto (máximo 6 palabras) para esta consulta: {query}"
            response = self.safe_generate_content(prompt)
            return response.text.strip().replace('"', '')
        except Exception:
            return "Nueva Consulta SICT"

    def _get_user_session(self, user_id: str) -> genai.ChatSession:
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = self.model.start_chat(history=[])
        return self.user_sessions[user_id]
    
    def get_cache_stats(self) -> Dict:
        if self.cache_manager:
            return self.cache_manager.obtener_estadisticas()
        return {"enabled": False, "message": "Cache no disponible"}
    
    def clear_user_cache(self, user_id: str = None) -> int:
        if self.cache_manager:
            return self.cache_manager.limpiar_usuario(user_id)
        return 0