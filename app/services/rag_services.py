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
from collections import Counter


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
        """Formatea respuesta para consultas de obras - VERSIÓN MEJORADA"""
        respuesta = []
        respuesta.append("🏗️ **OBRAS Y PROYECTOS DE INFRAESTRUCTURA**")
        respuesta.append("")
        
        for i, doc in enumerate(docs[:5], 1):
            metadata = doc.get('metadata', {})
            contenido = str(doc['content'])
            
            respuesta.append(f"**{i}. {metadata.get('source', 'Obra SICT')}**")
            
            # Extraer información clave
            lineas = []
            
            # Buscar ubicación
            ubicacion = self._extraer_valor(contenido, 'UBICACIÓN') or self._extraer_valor(contenido, 'DIRECCIÓN')
            if ubicacion:
                lineas.append(f"📍 Ubicación: {ubicacion}")
            
            # Buscar fechas
            fechas = re.findall(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', contenido)
            if fechas:
                lineas.append(f"📅 Fecha: {fechas[0]}")
            
            # Buscar montos
            montos = re.findall(r'\$?\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', contenido)
            if montos:
                lineas.append(f"💰 Monto: ${montos[0]}")
            
            # Buscar estatus
            estatus = self._extraer_valor(contenido, 'ESTATUS') or self._extraer_valor(contenido, 'ESTADO')
            if estatus:
                lineas.append(f"📊 Estatus: {estatus}")
            
            if lineas:
                for linea in lineas:
                    respuesta.append(f"  {linea}")
            else:
                # Si no hay info estructurada, mostrar preview limpio
                preview = contenido.replace(' | ', ' • ').replace('_x000d_', '')
                preview = preview[:150] + "..." if len(preview) > 150 else preview
                respuesta.append(f"  {preview}")
            
            respuesta.append("")
        
        if len(docs) > 5:
            respuesta.append(f"*... y {len(docs) - 5} obras más*")
        
        return "\n".join(respuesta)
        
    def _formatear_respuesta_baches(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de baches - VERSIÓN MEJORADA"""
        respuesta = []
        respuesta.append("🕳️ **REPORTES DE BACHES Y MANTENIMIENTO VIAL**")
        respuesta.append("")
        
        ubicaciones = []
        total_reportes = len(docs)
        
        for i, doc in enumerate(docs[:5], 1):
            contenido = str(doc['content'])
            metadata = doc.get('metadata', {})
            
            respuesta.append(f"**Reporte {i}**")
            
            # Extraer ubicación
            for linea in contenido.split('\n'):
                if any(p in linea.upper() for p in ['UBICACIÓN', 'DIRECCIÓN', 'CALLE', 'AVENIDA']):
                    ubicacion = linea.replace('UBICACIÓN:', '').replace('DIRECCIÓN:', '').strip()
                    if ubicacion and len(ubicacion) < 100:
                        respuesta.append(f"  📍 {ubicacion}")
                        ubicaciones.append(ubicacion)
                        break
            
            # Extraer fecha
            fechas = re.findall(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', contenido)
            if fechas:
                respuesta.append(f"  📅 {fechas[0]}")
            
            # Extraer severidad
            if 'SEVERIDAD' in contenido.upper() or 'GRAVEDAD' in contenido.upper():
                severidad = self._extraer_valor(contenido, 'SEVERIDAD') or self._extraer_valor(contenido, 'GRAVEDAD')
                if severidad:
                    respuesta.append(f"  ⚠️ Severidad: {severidad}")
            
            # Mostrar preview del reporte
            preview = contenido.replace('\n', ' ').strip()
            preview = preview[:100] + "..." if len(preview) > 100 else preview
            respuesta.append(f"  📝 {preview}")
            respuesta.append("")
        
        # Resumen ejecutivo
        respuesta.append("**📊 RESUMEN EJECUTIVO**")
        respuesta.append(f"  • Total de reportes: {total_reportes}")
        
        if ubicaciones:
            respuesta.append(f"  • Ubicaciones afectadas: {len(set(ubicaciones))}")
            if len(set(ubicaciones)) <= 3:
                respuesta.append(f"  • {', '.join(set(ubicaciones))}")
        
        return "\n".join(respuesta)
    
    def _formatear_respuesta_presupuestos(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de presupuestos - VERSIÓN MEJORADA"""
        respuesta = []
        respuesta.append("💰 **INFORMACIÓN PRESUPUESTAL Y FINANCIERA**")
        respuesta.append("")
        
        todos_montos = []
        
        for i, doc in enumerate(docs[:5], 1):
            contenido = str(doc['content'])
            metadata = doc.get('metadata', {})
            
            respuesta.append(f"**{i}. {metadata.get('source', 'Documento Presupuestal')}**")
            
            # Extraer concepto
            concepto = self._extraer_valor(contenido, 'CONCEPTO') or self._extraer_valor(contenido, 'DESCRIPCIÓN')
            if concepto:
                respuesta.append(f"  📋 {concepto[:100]}")
            
            # Extraer montos
            montos = re.findall(r'\$?\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', contenido)
            montos_limpios = []
            for m in montos[:3]:  # Máximo 3 montos por documento
                try:
                    monto_num = float(m.replace(',', ''))
                    montos_limpios.append(monto_num)
                    todos_montos.append(monto_num)
                    respuesta.append(f"  💵 ${monto_num:,.2f}")
                except:
                    respuesta.append(f"  💵 {m}")
            
            # Extraer ejercicio fiscal
            ejercicio = self._extraer_valor(contenido, 'EJERCICIO') or self._extraer_valor(contenido, 'AÑO')
            if ejercicio:
                respuesta.append(f"  📅 Ejercicio: {ejercicio}")
            
            respuesta.append("")
        
        # Análisis financiero
        if todos_montos:
            respuesta.append("**📊 ANÁLISIS FINANCIERO**")
            respuesta.append(f"  • Monto total: ${sum(todos_montos):,.2f}")
            respuesta.append(f"  • Promedio: ${sum(todos_montos)/len(todos_montos):,.2f}")
            respuesta.append(f"  • Mínimo: ${min(todos_montos):,.2f}")
            respuesta.append(f"  • Máximo: ${max(todos_montos):,.2f}")
        
        return "\n".join(respuesta)
    
    def _formatear_respuesta_personal(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de personal - VERSIÓN CON LIMPIEZA"""
        respuesta = []
        respuesta.append("👥 **PERSONAL DE LA SICT**")
        respuesta.append("")
        
        personas = []
        puestos = Counter()
        
        # Palabras a ignorar (headers)
        ignorar = {'NOMBRE', 'APELLIDO', 'EDAD', 'CARGO', 'NACIONALIDAD', 'PUESTO', 'NUM_EMPLEADO'}
        
        # Procesar documentos
        for doc in docs:
            contenido = str(doc['content'])
            
            # Si es el formato con pipes
            if ' | ' in contenido:
                datos = {}
                for parte in contenido.split(' | '):
                    if ':' in parte:
                        key, value = parte.split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Limpiar valores que son headers
                        if value not in ignorar and len(value) > 1:
                            datos[key] = value
                            
                            if key.upper() in ['PUESTO', 'CARGO'] and value not in ignorar:
                                puestos[value] += 1
                
                # Solo agregar si tiene al menos un nombre o apellido válido
                nombre_valido = datos.get('NOMBRE', '') not in ignorar and len(datos.get('NOMBRE', '')) > 1
                apellido_valido = datos.get('APELLIDO', '') not in ignorar and len(datos.get('APELLIDO', '')) > 1
                
                if nombre_valido or apellido_valido:
                    personas.append(datos)
        
        if not personas:
            # Fallback: intentar extraer de otra manera
            return "No se encontró información de personal en formato válido."
        
        # Mostrar personas en formato tabla
        for i, p in enumerate(personas[:10], 1):
            nombre = p.get('NOMBRE', '')
            apellido = p.get('APELLIDO', '')
            
            # Validar que no sean headers
            if nombre in ignorar:
                nombre = ''
            if apellido in ignorar:
                apellido = ''
            
            nombre_completo = f"{nombre} {apellido}".strip()
            
            if not nombre_completo:
                # Intentar construir de otras formas
                otros_campos = [v for k, v in p.items() if k not in ignorar and len(v) > 2]
                if otros_campos:
                    nombre_completo = otros_campos[0]
                else:
                    nombre_completo = f"Persona {i}"
            
            linea = f"**{i}. {nombre_completo}**"
            puesto = p.get('PUESTO', p.get('CARGO', ''))
            if puesto and puesto not in ignorar:
                linea += f" — *{puesto}*"
            respuesta.append(linea)
            
            # Detalles adicionales en una línea
            detalles = []
            if p.get('EDAD') and p['EDAD'] not in ignorar:
                detalles.append(f"Edad: {p['EDAD']}")
            if p.get('NACIONALIDAD') and p['NACIONALIDAD'] not in ignorar:
                detalles.append(f"Nac: {p['NACIONALIDAD']}")
            
            if detalles:
                respuesta.append(f"  ▫️ {' | '.join(detalles)}")
            respuesta.append("")
        
        # Resumen
        respuesta.append("**📊 RESUMEN**")
        respuesta.append(f"  • Total de personas: {len(personas)}")
        
        if puestos:
            respuesta.append("  • Puestos principales:")
            for puesto, count in puestos.most_common(3):
                if puesto not in ignorar:
                    respuesta.append(f"    - {puesto}: {count}")
        
        if len(personas) > 10:
            respuesta.append(f"\n*... y {len(personas) - 10} personas más*")
        
        return "\n".join(respuesta)
    
    def _formatear_respuesta_contratos(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de contratos - VERSIÓN MEJORADA"""
        respuesta = []
        respuesta.append("📄 **CONTRATOS Y LICITACIONES**")
        respuesta.append("")
        
        for i, doc in enumerate(docs[:5], 1):
            contenido = str(doc['content'])
            metadata = doc.get('metadata', {})
            
            respuesta.append(f"**Contrato {i}**")
            
            # Número de contrato
            num_contrato = (
                self._extraer_valor(contenido, 'CONTRATO') or 
                self._extraer_valor(contenido, 'NÚMERO') or
                re.search(r'[A-Z0-9]{5,15}', contenido)
            )
            if num_contrato:
                respuesta.append(f"  🏷️ Número: {num_contrato}")
            
            # Proveedor
            proveedor = self._extraer_valor(contenido, 'PROVEEDOR') or self._extraer_valor(contenido, 'CONTRATISTA')
            if proveedor:
                respuesta.append(f"  🏢 Proveedor: {proveedor}")
            
            # Monto
            monto = self._extraer_valor(contenido, 'MONTO')
            if monto:
                respuesta.append(f"  💰 Monto: ${monto}")
            else:
                montos = re.findall(r'\$?\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', contenido)
                if montos:
                    respuesta.append(f"  💰 Monto: ${montos[0]}")
            
            # Fechas
            fechas = re.findall(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', contenido)
            if fechas:
                fecha_str = f"  📅 "
                if len(fechas) >= 2:
                    fecha_str += f"Inicio: {fechas[0]} | Fin: {fechas[1]}"
                else:
                    fecha_str += f"Fecha: {fechas[0]}"
                respuesta.append(fecha_str)
            
            # Estatus
            estatus = self._extraer_valor(contenido, 'ESTATUS')
            if estatus:
                respuesta.append(f"  📊 Estatus: {estatus}")
            
            respuesta.append("")
        
        return "\n".join(respuesta)
    
    def _formatear_respuesta_normativas(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de normativas - VERSIÓN MEJORADA"""
        respuesta = []
        respuesta.append("📚 **NORMATIVAS Y REGLAMENTOS**")
        respuesta.append("")
        
        for i, doc in enumerate(docs[:5], 1):
            contenido = str(doc['content'])
            metadata = doc.get('metadata', {})
            
            titulo = metadata.get('source', 'Documento Normativo')
            if metadata.get('sheet'):
                titulo += f" - {metadata.get('sheet')}"
            
            respuesta.append(f"**{i}. {titulo}**")
            
            # Buscar artículos citados
            articulos = re.findall(r'(?:Artículo|Art\.?)\s*(\d+)', contenido, re.IGNORECASE)
            if articulos:
                respuesta.append(f"  📌 Artículos: {', '.join(articulos[:5])}")
            
            # Buscar capítulos o secciones
            capitulos = re.findall(r'(?:Capítulo|Cap\.?)\s*(\d+|[IVXLCDM]+)', contenido, re.IGNORECASE)
            if capitulos:
                respuesta.append(f"  📑 Capítulos: {', '.join(capitulos[:3])}")
            
            # Mostrar primeras líneas relevantes
            lineas = contenido.split('\n')
            texto_relevante = []
            for linea in lineas[:5]:
                linea_limpia = linea.strip()
                if linea_limpia and len(linea_limpia) > 20 and 'Fuente:' not in linea_limpia:
                    texto_relevante.append(linea_limpia[:100])
            
            if texto_relevante:
                respuesta.append(f"  📝 {texto_relevante[0]}")
            
            respuesta.append("")
        
        return "\n".join(respuesta)
    
    def _formatear_respuesta_estadisticas(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de estadísticas - VERSIÓN MEJORADA"""
        respuesta = []
        respuesta.append("📊 **ESTADÍSTICAS Y REPORTES**")
        respuesta.append("")
        
        todos_numeros = []
        categorias = Counter()
        
        for doc in docs:
            contenido = str(doc['content'])
            metadata = doc.get('metadata', {})
            
            # Identificar categoría
            categoria = metadata.get('tipo_documento', 'General')
            categorias[categoria] += 1
            
            # Extraer números
            numeros = re.findall(r'\d+(?:\.\d+)?', contenido)
            numeros_float = [float(n) for n in numeros if len(n) < 6 and float(n) < 1000000]
            todos_numeros.extend(numeros_float)
        
        # Resumen estadístico general
        if todos_numeros:
            respuesta.append("**📈 RESUMEN ESTADÍSTICO**")
            respuesta.append(f"  • Total de datos: {len(todos_numeros)}")
            respuesta.append(f"  • Promedio: {sum(todos_numeros)/len(todos_numeros):.2f}")
            respuesta.append(f"  • Mediana: {sorted(todos_numeros)[len(todos_numeros)//2]:.2f}")
            respuesta.append(f"  • Mínimo: {min(todos_numeros):.2f}")
            respuesta.append(f"  • Máximo: {max(todos_numeros):.2f}")
            respuesta.append("")
        
        # Distribución por categoría
        if categorias:
            respuesta.append("**📁 DISTRIBUCIÓN POR TIPO**")
            for cat, count in categorias.most_common():
                respuesta.append(f"  • {cat}: {count} documento(s)")
            respuesta.append("")
        
        # Lista de reportes
        respuesta.append("**📋 REPORTES DISPONIBLES**")
        for i, doc in enumerate(docs[:5], 1):
            metadata = doc.get('metadata', {})
            fuente = metadata.get('source', 'Reporte').replace('.xlsx', '').replace('.pdf', '')
            respuesta.append(f"  {i}. {fuente}")
        
        return "\n".join(respuesta)
    def _formatear_respuesta_inventarios(self, docs: List[Dict]) -> str:
        """Formatea respuesta para consultas de inventarios - VERSIÓN MEJORADA"""
        respuesta = []
        respuesta.append("📦 **INVENTARIOS Y ACTIVOS**")
        respuesta.append("")
        
        items_totales = 0
        categorias = Counter()
        
        for i, doc in enumerate(docs[:3], 1):
            contenido = str(doc['content'])
            metadata = doc.get('metadata', {})
            
            fuente = metadata.get('source', 'Inventario')
            respuesta.append(f"**{i}. {fuente}**")
            
            # Contar items en este documento
            if ' | ' in contenido:
                items = contenido.split(' | ')
                items_totales += len(items)
                
                # Mostrar algunos items
                for item in items[:5]:
                    item_limpio = item.replace('_x000d_', '').strip()
                    if ':' in item_limpio:
                        respuesta.append(f"  • {item_limpio}")
                    else:
                        respuesta.append(f"  • {item_limpio[:80]}")
            else:
                # Si es texto plano, contar líneas con contenido
                lineas = [l for l in contenido.split('\n') if l.strip() and len(l.strip()) > 10]
                items_totales += len(lineas)
                
                for linea in lineas[:5]:
                    respuesta.append(f"  • {linea[:80]}")
            
            respuesta.append("")
        
        # Resumen
        respuesta.append("**📊 RESUMEN DE INVENTARIO**")
        respuesta.append(f"  • Total de documentos: {len(docs)}")
        respuesta.append(f"  • Total aproximado de items: {items_totales}")
        
        return "\n".join(respuesta)
    
    def _formatear_respuesta_generica(self, docs: List[Dict], query: str) -> str:
        """Formatea respuesta genérica - VERSIÓN MEJORADA Y LIMPIA"""
        respuesta = []
        
        # Detectar tipo de consulta
        query_lower = query.lower()
        
        # Si es consulta de conteo
        if any(word in query_lower for word in ['cuantos', 'cuántos', 'total', 'número', 'cantidad']):
            return self._formatear_respuesta_conteo(docs, query)
        
        # Si es consulta de lista
        if any(word in query_lower for word in ['lista', 'listado', 'muestra', 'dime']):
            respuesta.append("📋 **RESULTADO DE BÚSQUEDA**")
        else:
            respuesta.append("📑 **INFORMACIÓN ENCONTRADA**")
        
        respuesta.append("")
        respuesta.append(f"**Consulta:** {query}")
        respuesta.append(f"**Documentos relevantes:** {len(docs)}")
        respuesta.append("")
        
        # Agrupar por archivo
        archivos = {}
        for doc in docs:
            fuente = doc['metadata'].get('source', 'Documento')
            if fuente not in archivos:
                archivos[fuente] = []
            archivos[fuente].append(doc)
        
        # Mostrar información agrupada
        for fuente, docs_fuente in archivos.items():
            respuesta.append(f"**📁 {fuente}**")
            
            for i, doc in enumerate(docs_fuente[:5], 1):
                contenido = doc['content']
                metadata = doc.get('metadata', {})
                
                # Si es un registro de persona, formatear bonito
                if 'NOMBRE:' in contenido and 'APELLIDO:' in contenido:
                    nombre = self._extraer_valor(contenido, 'NOMBRE')
                    apellido = self._extraer_valor(contenido, 'APELLIDO')
                    puesto = self._extraer_valor(contenido, 'PUESTO') or self._extraer_valor(contenido, 'CARGO')
                    
                    linea = f"  • {nombre} {apellido}".strip()
                    if puesto:
                        linea += f" — *{puesto}*"
                    respuesta.append(linea)
                else:
                    # Contenido genérico - limpiar y mostrar
                    preview = contenido.replace(' | ', ' • ').replace('_x000d_', '')
                    preview = preview.replace('NOMBRE:', '**Nombre:**').replace('APELLIDO:', '**Apellido:**')
                    preview = preview[:100] + "..." if len(preview) > 100 else preview
                    respuesta.append(f"  • {preview}")
            
            if len(docs_fuente) > 5:
                respuesta.append(f"  *... y {len(docs_fuente) - 5} registros más*")
            respuesta.append("")
        
        return "\n".join(respuesta)
    def _extraer_valor(self, texto: str, campo: str) -> str:
        """Extrae el valor de un campo específico del texto"""
        patron = rf'{campo}:\s*([^|]+)'
        match = re.search(patron, texto)
        return match.group(1).strip() if match else ""

    def _formatear_respuesta_conteo(self, docs: List[Dict], query: str) -> str:
        """Formatea respuestas de conteo de manera limpia - VERSIÓN CON LIMPIEZA"""
        respuesta = []
        respuesta.append("🔢 **RESULTADO DE CONTEO**")
        respuesta.append("")
        
        # Detectar qué estamos contando
        query_lower = query.lower()
        
        # Contar personas (VERSIÓN MEJORADA CON LIMPIEZA)
        if any(word in query_lower for word in ['nombre', 'persona', 'empleado', 'trabajador']):
            personas = set()
            
            for doc in docs:
                contenido = doc['content']
                
                # LIMPIEZA: Eliminar texto repetido y basura
                if 'NOMBRE:' in contenido:
                    # Extraer solo los nombres reales
                    partes = contenido.split(' | ')
                    for parte in partes:
                        if parte.startswith('NOMBRE:'):
                            nombre = parte.replace('NOMBRE:', '').strip()
                            # Ignorar si es un encabezado o texto repetido
                            if nombre and nombre not in ['NOMBRE', 'APELLIDO', 'EDAD', 'CARGO', 'NACIONALIDAD']:
                                # Limpiar nombres que parecen listas
                                if ',' in nombre:
                                    # Si tiene comas, tomar solo el primer nombre real
                                    nombres_lista = [n.strip() for n in nombre.split(',') if n.strip() and len(n.strip()) > 2]
                                    for n in nombres_lista:
                                        if n not in ['NOMBRE', 'APELLIDO', 'EDAD', 'CARGO', 'NACIONALIDAD']:
                                            personas.add(n)
                                else:
                                    personas.add(nombre)
                        
                        elif parte.startswith('APELLIDO:'):
                            apellido = parte.replace('APELLIDO:', '').strip()
                            # Similar limpieza para apellidos
                            if apellido and apellido not in ['NOMBRE', 'APELLIDO', 'EDAD', 'CARGO', 'NACIONALIDAD']:
                                if ',' in apellido:
                                    apellidos_lista = [a.strip() for a in apellido.split(',') if a.strip() and len(a.strip()) > 2]
                                    for a in apellidos_lista:
                                        if a not in ['NOMBRE', 'APELLIDO', 'EDAD', 'CARGO', 'NACIONALIDAD']:
                                            # Buscamos si ya tenemos este apellido asociado a algún nombre
                                            pass
                                else:
                                    # No podemos agregar solo apellidos sin nombre
                                    pass
            
            # Si encontramos nombres, mostrarlos
            if personas:
                # Filtrar nombres válidos (más de 2 caracteres y no son headers)
                personas_validas = {p for p in personas if len(p) > 2 and p not in ['NOMBRE', 'APELLIDO', 'EDAD', 'CARGO', 'NACIONALIDAD']}
                
                respuesta.append(f"**Total de personas:** {len(personas_validas)}")
                
                if personas_validas:
                    respuesta.append("")
                    respuesta.append("**Lista de personas:**")
                    for persona in sorted(personas_validas):
                        respuesta.append(f"  • {persona}")
            else:
                # Fallback: intentar extraer de otra manera
                nombres_encontrados = self._extraer_nombres_de_documentos(docs)
                if nombres_encontrados:
                    respuesta.append(f"**Total de personas:** {len(nombres_encontrados)}")
                    respuesta.append("")
                    respuesta.append("**Lista de personas:**")
                    for nombre in sorted(nombres_encontrados):
                        respuesta.append(f"  • {nombre}")
                else:
                    respuesta.append(f"**Total de registros:** {len(docs)}")
        
        # Contar documentos
        elif 'documento' in query_lower or 'archivo' in query_lower:
            respuesta.append(f"**Total de documentos:** {len(docs)}")
            
            # Agrupar por tipo
            tipos = Counter()
            for doc in docs:
                tipo = doc['metadata'].get('format', 'Desconocido')
                tipos[tipo] += 1
            
            if tipos:
                respuesta.append("")
                respuesta.append("**Por tipo:**")
                for tipo, count in tipos.items():
                    respuesta.append(f"  • {tipo}: {count}")
        
        # Conteo genérico
        else:
            respuesta.append(f"**Total de registros encontrados:** {len(docs)}")
        
        return "\n".join(respuesta)

    def _extraer_nombres_de_documentos(self, docs: List[Dict]) -> set:
        """Extrae nombres reales de los documentos"""
        nombres = set()
        
        # Lista de palabras a ignorar (headers, etc.)
        ignorar = {'NOMBRE', 'APELLIDO', 'EDAD', 'CARGO', 'NACIONALIDAD', 'PUESTO', 'NUM_EMPLEADO'}
        
        for doc in docs:
            contenido = doc['content']
            
            # Buscar patrones de nombre/apellido
            lineas = contenido.split('\n')
            for linea in lineas:
                # Buscar líneas con formato "NOMBRE: X | APELLIDO: Y"
                if 'NOMBRE:' in linea and 'APELLIDO:' in linea:
                    partes = linea.split(' | ')
                    nombre = ''
                    apellido = ''
                    
                    for parte in partes:
                        if parte.startswith('NOMBRE:'):
                            nombre = parte.replace('NOMBRE:', '').strip()
                        elif parte.startswith('APELLIDO:'):
                            apellido = parte.replace('APELLIDO:', '').strip()
                    
                    # Validar que sean nombres reales
                    if nombre and nombre not in ignorar and len(nombre) > 2:
                        if apellido and apellido not in ignorar and len(apellido) > 2:
                            nombres.add(f"{nombre} {apellido}".strip())
                        else:
                            nombres.add(nombre)
        
        return nombres

    def _formatear_respuesta_personal_mejorada(self, docs: List[Dict]) -> str:
        """Formatea información de personal de manera más visual"""
        respuesta = []
        respuesta.append("👥 **PERSONAL ENCONTRADO**")
        respuesta.append("")
        
        personas = []
        for doc in docs:
            contenido = doc['content']
            persona = {
                'nombre': self._extraer_valor(contenido, 'NOMBRE'),
                'apellido': self._extraer_valor(contenido, 'APELLIDO'),
                'puesto': self._extraer_valor(contenido, 'PUESTO') or self._extraer_valor(contenido, 'CARGO'),
                'edad': self._extraer_valor(contenido, 'EDAD'),
                'nacionalidad': self._extraer_valor(contenido, 'NACIONALIDAD')
            }
            if persona['nombre'] or persona['apellido']:
                personas.append(persona)
        
        # Mostrar en formato tabla limpia
        for i, p in enumerate(personas, 1):
            nombre_completo = f"{p['nombre']} {p['apellido']}".strip()
            linea = f"**{i}. {nombre_completo}**"
            if p['puesto']:
                linea += f" — *{p['puesto']}*"
            respuesta.append(linea)
            
            detalles = []
            if p['edad']:
                detalles.append(f"Edad: {p['edad']}")
            if p['nacionalidad']:
                detalles.append(f"Nacionalidad: {p['nacionalidad']}")
            
            if detalles:
                respuesta.append(f"   ▫️ {' | '.join(detalles)}")
            respuesta.append("")
        
        respuesta.append(f"**Total:** {len(personas)} personas")
        
        return "\n".join(respuesta)

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