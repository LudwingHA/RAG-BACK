# app/services/document_processor.py

import os
import re
import unicodedata
import pandas as pd
from pypdf import PdfReader
from docx import Document
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime
import time
from collections import Counter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [DocumentProcessor] - %(message)s'
)

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """
    Procesador de documentos SICT con limpieza inteligente para:
    - Personal/RH
    - Obras e infraestructura
    - Baches y mantenimiento vial
    - Presupuestos y finanzas
    - Contratos y licitaciones
    - Inventarios y activos
    - Normativas y reglamentos
    """

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap debe ser menor que chunk_size")
        
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        self.ignorar_global = {
            'NOMBRE', 'APELLIDO', 'EDAD', 'CARGO', 'NACIONALIDAD', 'PUESTO',
            'NUM_EMPLEADO', 'DEPENDENCIA', 'AREA', 'FECHA', 'NOM', 'AP', 'LAST',
            'ID', 'CLAVE', 'CÓDIGO', 'CODIGO', 'DESCRIPCIÓN', 'DESCRIPCION',
            'CANTIDAD', 'UNIDAD', 'PRECIO', 'IMPORTE', 'TOTAL', 'SUBTOTAL',
            'IVA', 'RFC', 'CURP', 'TELEFONO', 'CORREO', 'DOMICILIO',
            'UBICACIÓN', 'UBICACION', 'DIRECCIÓN', 'DIRECCION', 'ESTADO',
            'MUNICIPIO', 'LOCALIDAD', 'LATITUD', 'LONGITUD', 'SUPERFICIE',
            'MONTO', 'PRESUPUESTO', 'EJERCICIO', 'AÑO', 'PERIODO',
            'CONTRATO', 'LICITACIÓN', 'LICITACION', 'PROVEEDOR', 'CONTRATISTA',
            'ESTATUS', 'ESTADO', 'OBSERVACIONES', 'COMENTARIOS'
        }
        
        self.patrones_tipos = {
            'PERSONAL': ['NOMBRE', 'APELLIDO', 'RFC', 'CURP', 'PUESTO', 'EMPLEADO'],
            'OBRAS': ['OBRA', 'PROYECTO', 'CARRETERA', 'PUENTE', 'INFRAESTRUCTURA', 'CONSTRUCCIÓN'],
            'BACHES': ['BACHE', 'MANTENIMIENTO VIAL', 'REPARACIÓN', 'PAVIMENTO', 'CARPETA ASFÁLTICA'],
            'PRESUPUESTO': ['PRESUPUESTO', 'MONTO', 'COSTO', 'GASTO', 'INVERSIÓN', 'FINANZAS'],
            'CONTRATOS': ['CONTRATO', 'LICITACIÓN', 'PROVEEDOR', 'ADJUDICACIÓN', 'CONTRATISTA'],
            'INVENTARIO': ['INVENTARIO', 'BIEN', 'ACTIVO', 'EQUIPO', 'MAQUINARIA', 'HERRAMIENTA'],
            'NORMATIVAS': ['NORMA', 'REGLAMENTO', 'LEY', 'LINEAMIENTO', 'PROCEDIMIENTO'],
            'ESTADISTICAS': ['ESTADÍSTICA', 'INDICADOR', 'MÉTRICA', 'REPORTE', 'DATOS']
        }

    def _normalize_text(self, text: str) -> str:
        """Normaliza texto: elimina caracteres especiales y espacios extras"""
        if not text:
            return ""
        text = unicodedata.normalize('NFKC', text)
        text = re.sub(r'[\r\n\t]+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _generate_chunks(self, text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Genera chunks de texto con solapamiento"""
        chunks = []
        if not text:
            return chunks
        
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = min(start + self.chunk_size, text_len)
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                chunks.append({
                    "content": chunk_text,
                    "metadata": metadata.copy()
                })
            
            if end == text_len:
                break
            start = end - self.chunk_overlap
        
        return chunks

    def _es_valor_valido(self, valor: str, header: str = "") -> bool:
        """
        Verifica si un valor es válido (no es header, no es basura)
        """
        if not valor or not isinstance(valor, str):
            return False
        
        valor_upper = valor.upper().strip()
        valor_limpio = valor.strip()
        
        if len(valor_limpio) < 2:
            return False
        
        if valor_upper in self.ignorar_global:
            return False
        
        if valor_upper == header.upper():
            return False
        
        if re.match(r'^\d{10,}$', valor_limpio):
            return False
        
        if 'UNNAMED' in valor_upper:
            return False
        
        if ',' in valor:
            partes = [p.strip().upper() for p in valor.split(',')]
            if all(p in self.ignorar_global for p in partes if p):
                return False
        
        return True

    def _limpiar_valor(self, valor: str, header: str = "") -> Optional[str]:
        """
        Limpia un valor y retorna None si no es válido
        """
        if pd.isna(valor):
            return None
        
        valor_str = str(valor).strip()
        
        valor_str = re.sub(r'[\n\r\t]', ' ', valor_str)
        valor_str = re.sub(r'\s+', ' ', valor_str)
        
        valor_str = re.sub(r'^:\s*', '', valor_str)
        valor_str = re.sub(r'^\|\s*', '', valor_str)
        
        if not self._es_valor_valido(valor_str, header):
            return None
        
        return valor_str

    def process_pdf(self, file_path: str) -> List[Dict]:
        """Procesa archivos PDF"""
        all_chunks = []
        try:
            reader = PdfReader(file_path)
            filename = os.path.basename(file_path)
            
            for i, page in enumerate(reader.pages):
                text = self._normalize_text(page.extract_text() or "")
                if text:
                    metadata = {
                        "source": filename,
                        "page": i + 1,
                        "format": "PDF",
                        "tipo_documento": self._detectar_tipo_contenido(text)
                    }
                    all_chunks.extend(self._generate_chunks(text, metadata))
            
            logger.info(f"✅ PDF procesado: {filename} - {len(all_chunks)} chunks")
        except Exception as e:
            logger.exception(f"Error PDF: {e}")
        return all_chunks

    def process_word(self, file_path: str) -> List[Dict]:
        """Procesa archivos Word"""
        all_chunks = []
        try:
            doc = Document(file_path)
            filename = os.path.basename(file_path)
            
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = self._normalize_text("\n".join(paragraphs))
            
            if text:
                metadata = {
                    "source": filename,
                    "format": "Word",
                    "tipo_documento": self._detectar_tipo_contenido(text)
                }
                all_chunks.extend(self._generate_chunks(text, metadata))
            
            logger.info(f"✅ Word procesado: {filename} - {len(all_chunks)} chunks")
        except Exception as e:
            logger.exception(f"Error Word: {e}")
        return all_chunks

    def process_txt(self, file_path: str) -> List[Dict]:
        """Procesa archivos TXT"""
        all_chunks = []
        try:
            filename = os.path.basename(file_path)
            
            with open(file_path, "r", encoding="utf-8") as f:
                text = self._normalize_text(f.read())
            
            if text:
                metadata = {
                    "source": filename,
                    "format": "TXT",
                    "tipo_documento": self._detectar_tipo_contenido(text)
                }
                all_chunks.extend(self._generate_chunks(text, metadata))
            
            logger.info(f"✅ TXT procesado: {filename} - {len(all_chunks)} chunks")
        except Exception as e:
            logger.exception(f"Error TXT: {e}")
        return all_chunks

    def _detectar_tipo_contenido(self, texto: str) -> str:
        """
        Detecta el tipo de contenido basado en el texto
        """
        texto_upper = texto.upper()
        puntajes = {}
        
        for tipo, patrones in self.patrones_tipos.items():
            score = sum(1 for p in patrones if p.upper() in texto_upper)
            if score > 0:
                puntajes[tipo] = score
        
        if puntajes:
            return max(puntajes, key=puntajes.get)
        return 'GENERAL'

    # ==================== MÉTODOS PRINCIPALES PARA EXCEL ====================

    def process_excel(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Procesa Excel con detección inteligente multi-tipo y tolerancia a errores humanos
        Maneja: Personal, Obras, Presupuestos, Inventario, Baches, Contratos, Incidencias
        """
        all_chunks = []
        start_time = time.time()
        
        try:
            filename = os.path.basename(file_path)
            logger.info(f"📊 Procesando Excel multi-tipo: {filename}")
            
            # Leer todas las hojas
            excel_file = pd.ExcelFile(file_path)
            
            for sheet_name in excel_file.sheet_names:
                logger.info(f"  📄 Hoja: {sheet_name}")
                
                # Intentar leer con múltiples estrategias (tolerancia a errores)
                df = self._leer_excel_tolerante(file_path, sheet_name)
                
                if df is None or df.empty:
                    logger.warning(f"  ⚠️ Hoja vacía o no se pudo leer: {sheet_name}")
                    continue
                
                # Detectar tipo de contenido de la hoja
                tipo_hoja = self._detectar_tipo_hoja(df, sheet_name)
                logger.info(f"    📌 Tipo detectado: {tipo_hoja}")
                
                # Limpieza inteligente
                df = self._limpieza_inteligente(df)
                
                if df.empty:
                    continue
                
                # Procesar según tipo detectado
                if tipo_hoja == 'PERSONAL':
                    chunks = self._procesar_personal(df, filename, sheet_name)
                elif tipo_hoja == 'OBRAS':
                    chunks = self._procesar_obras(df, filename, sheet_name)
                elif tipo_hoja == 'PRESUPUESTO':
                    chunks = self._procesar_presupuesto(df, filename, sheet_name)
                elif tipo_hoja == 'INVENTARIO':
                    chunks = self._procesar_inventario(df, filename, sheet_name)
                elif tipo_hoja == 'INCIDENCIAS':
                    chunks = self._procesar_incidencias(df, filename, sheet_name)
                elif tipo_hoja == 'CONTRATOS':
                    chunks = self._procesar_contratos(df, filename, sheet_name)
                else:
                    chunks = self._procesar_generico(df, filename, sheet_name)
                
                all_chunks.extend(chunks)
                logger.info(f"    ✅ {len(chunks)} chunks generados")
            
            elapsed = time.time() - start_time
            logger.info(f"✅ Excel procesado: {filename} - {len(all_chunks)} chunks en {elapsed:.2f}s")
            
        except Exception as e:
            logger.exception(f"Error procesando Excel {file_path}: {e}")
            all_chunks.append(self._crear_chunk_error(filename, str(e)))
        
        return all_chunks

    # ==================== MÉTODOS AUXILIARES PARA EXCEL ====================

    def _leer_excel_tolerante(self, file_path: str, sheet_name: str) -> Optional[pd.DataFrame]:
        """Múltiples estrategias de lectura tolerantes a errores"""
        estrategias = [
            lambda: pd.read_excel(file_path, sheet_name=sheet_name, header=0),
            lambda: pd.read_excel(file_path, sheet_name=sheet_name, header=None),
            lambda: pd.read_excel(file_path, sheet_name=sheet_name, skiprows=1, header=0),
            lambda: pd.read_excel(file_path, sheet_name=sheet_name, dtype=str),
            lambda: pd.read_excel(file_path, sheet_name=sheet_name, engine='openpyxl'),
        ]
        
        for i, estrategia in enumerate(estrategias):
            try:
                df = estrategia()
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                logger.debug(f"Estrategia {i+1} falló: {e}")
                continue
        
        return None

    def _detectar_tipo_hoja(self, df: pd.DataFrame, sheet_name: str) -> str:
        """Detecta el tipo de contenido basado en columnas y contenido"""
        cols = [str(col).upper().strip() for col in df.columns]
        cols_str = ' '.join(cols)
        sheet_lower = sheet_name.lower()
        
        sample_text = ' '.join([str(v).upper() for v in df.iloc[0:5].values.flatten() if pd.notna(v)])
        
        patrones = {
            'PERSONAL': {
                'columnas': ['NOMBRE', 'APELLIDO', 'EMPLEADO', 'RFC', 'CURP', 'PUESTO', 'CARGO'],
                'hoja': ['personal', 'rh', 'empleados', 'trabajadores'],
                'contenido': ['NOMBRE', 'APELLIDO', 'RFC', 'EMPLEADO']
            },
            'OBRAS': {
                'columnas': ['OBRA', 'PROYECTO', 'TIPO', 'UBICACIÓN', 'UBICACION', 'MONTO', 'AVANCE', 'RESPONSABLE'],
                'hoja': ['obra', 'proyecto', 'infraestructura', 'construcción'],
                'contenido': ['OBRA', 'PROYECTO', 'CONSTRUCCIÓN', 'INFRAESTRUCTURA']
            },
            'PRESUPUESTO': {
                'columnas': ['PRESUPUESTO', 'MONTO', 'COSTO', 'PARTIDA', 'CONCEPTO', 'EJERCICIO'],
                'hoja': ['presupuesto', 'finanzas', 'costos', 'partidas'],
                'contenido': ['PRESUPUESTO', 'MONTO', 'COSTO', 'PARTIDA']
            },
            'INVENTARIO': {
                'columnas': ['INVENTARIO', 'BIEN', 'ACTIVO', 'CÓDIGO', 'DESCRIPCIÓN', 'CANTIDAD'],
                'hoja': ['inventario', 'activos', 'bienes', 'equipo', 'maquinaria'],
                'contenido': ['INVENTARIO', 'BIEN', 'ACTIVO', 'CÓDIGO']
            },
            'INCIDENCIAS': {
                'columnas': ['INCIDENCIA', 'BACHE', 'REPORTE', 'GRAVEDAD', 'ESTADO', 'FECHA_REPORTE'],
                'hoja': ['incidencia', 'bache', 'reporte', 'queja', 'falla'],
                'contenido': ['INCIDENCIA', 'BACHE', 'REPORTE', 'GRAVEDAD', 'CRÍTICA']
            },
            'CONTRATOS': {
                'columnas': ['CONTRATO', 'LICITACIÓN', 'PROVEEDOR', 'CONTRATISTA', 'FECHA_INICIO', 'FECHA_FIN'],
                'hoja': ['contrato', 'licitación', 'proveedor', 'adjudicación'],
                'contenido': ['CONTRATO', 'LICITACIÓN', 'PROVEEDOR']
            }
        }
        
        max_score = 0
        detected_type = 'GENERAL'
        
        for tipo, patron in patrones.items():
            score = 0
            
            for col_patron in patron['columnas']:
                if col_patron in cols_str:
                    score += 3
            
            for hoja_patron in patron['hoja']:
                if hoja_patron in sheet_lower:
                    score += 5
            
            for cont_patron in patron['contenido']:
                if cont_patron in sample_text:
                    score += 2
            
            if score > max_score:
                max_score = score
                detected_type = tipo
        
        if max_score < 3:
            numeric_cols = df.select_dtypes(include=['number']).columns
            if len(numeric_cols) >= 2 and df[numeric_cols].notna().any().any():
                return 'PRESUPUESTO'
            elif len(df.columns) >= 3 and len(df) > 5:
                return 'GENERAL_TABULAR'
        
        return detected_type

    def _limpieza_inteligente(self, df: pd.DataFrame) -> pd.DataFrame:
        """Limpieza tolerante a errores humanos"""
        df = df.dropna(how='all').dropna(axis=1, how='all')
        
        threshold = int(len(df.columns) * 0.8)
        df = df.dropna(thresh=threshold, axis=0)
        
        df.columns = [
            str(col).strip().upper().replace(' ', '_').replace('Á', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U')
            if not str(col).startswith('Unnamed') else f'COL_{i}'
            for i, col in enumerate(df.columns)
        ]
        
        df = df.replace(['N/A', 'NA', 'NULL', 'null', 'None', ''], pd.NA)
        
        for col in df.columns:
            if df[col].dtype == 'object':
                try:
                    cleaned = df[col].astype(str).str.replace(r'[^\d.-]', '', regex=True)
                    df[col] = pd.to_numeric(cleaned, errors='ignore')
                except:
                    pass
        
        return df

    def _encontrar_columna(self, df: pd.DataFrame, posibles: List[str]) -> Optional[str]:
        """Encuentra la columna que coincide con posibles nombres (tolerante a errores)"""
        cols_upper = [str(col).upper().strip() for col in df.columns]
        
        for posible in posibles:
            posible_upper = posible.upper()
            
            if posible_upper in cols_upper:
                idx = cols_upper.index(posible_upper)
                return df.columns[idx]
            
            for i, col in enumerate(cols_upper):
                if posible_upper in col or col in posible_upper:
                    return df.columns[i]
        
        return None

    # ==================== PROCESAMIENTO POR TIPO ====================

    def _procesar_personal(self, df: pd.DataFrame, filename: str, sheet_name: str) -> List[Dict]:
        """Procesa datos de personal/RH"""
        chunks = []
        registros = df.to_dict(orient='records')
        
        col_mapping = {
            'nombre': ['NOMBRE', 'NOM', 'NOMBRES', 'EMPLEADO', 'TRABAJADOR'],
            'apellido': ['APELLIDO', 'APELLIDOS', 'AP', 'LAST_NAME'],
            'puesto': ['PUESTO', 'CARGO', 'POSICION', 'ROL', 'PUESTO_ACTUAL'],
            'rfc': ['RFC', 'REGISTRO_FEDERAL'],
            'curp': ['CURP'],
            'departamento': ['DEPARTAMENTO', 'AREA', 'DIRECCION', 'UNIDAD'],
            'fecha_ingreso': ['FECHA_INGRESO', 'INGRESO', 'FECHA_CONTRATACION', 'ANTIGÜEDAD']
        }
        
        columnas = {tipo: self._encontrar_columna(df, posibles) for tipo, posibles in col_mapping.items()}
        
        for idx, row in enumerate(registros):
            texto_parts = []
            metadata = {
                "source": filename,
                "sheet": sheet_name,
                "row": idx + 2,
                "format": "Excel",
                "tipo_documento": "PERSONAL",
                "tipo_contenido": "registro_personal"
            }
            
            for tipo, col in columnas.items():
                if col and pd.notna(row.get(col)):
                    valor = str(row[col]).strip()
                    if len(valor) > 1 and valor.upper() not in self.ignorar_global:
                        texto_parts.append(f"{tipo}: {valor}")
                        metadata[tipo] = valor
            
            if texto_parts:
                chunks.append({
                    "content": " | ".join(texto_parts),
                    "metadata": metadata
                })
        
        if len(registros) > 5:
            resumen = self._resumen_personal(registros, columnas, filename, sheet_name)
            if resumen:
                chunks.append(resumen)
        
        return chunks

    def _procesar_obras(self, df: pd.DataFrame, filename: str, sheet_name: str) -> List[Dict]:
        """Procesa datos de obras/infraestructura"""
        chunks = []
        registros = df.to_dict(orient='records')
        
        col_mapping = {
            'nombre': ['OBRA', 'PROYECTO', 'NOMBRE_OBRA', 'PROYECTO_OBRA', 'DESCRIPCION'],
            'tipo': ['TIPO', 'TIPO_OBRA', 'CATEGORIA', 'CLASIFICACION'],
            'ubicacion': ['UBICACION', 'UBICACIÓN', 'DIRECCION', 'DOMICILIO', 'MUNICIPIO', 'LOCALIDAD'],
            'monto': ['MONTO', 'PRESUPUESTO', 'COSTO', 'INVERSION', 'PRESUPUESTO_ASIGNADO'],
            'avance': ['AVANCE', 'PROGRESO', '%_AVANCE', 'PORCENTAJE'],
            'responsable': ['RESPONSABLE', 'INGENIERO', 'CONTRATISTA', 'ENCARGADO', 'SUPERVISOR'],
            'fecha_inicio': ['FECHA_INICIO', 'INICIO', 'FECHA_INICIO_OBRA'],
            'fecha_fin': ['FECHA_FIN', 'FIN', 'FECHA_TERMINO', 'CONCLUSION'],
            'estado': ['ESTADO', 'ESTATUS', 'SITUACION', 'CONDICION']
        }
        
        columnas = {tipo: self._encontrar_columna(df, posibles) for tipo, posibles in col_mapping.items()}
        
        for idx, row in enumerate(registros):
            texto_parts = []
            metadata = {
                "source": filename,
                "sheet": sheet_name,
                "row": idx + 2,
                "format": "Excel",
                "tipo_documento": "OBRAS",
                "tipo_contenido": "registro_obra"
            }
            
            for tipo, col in columnas.items():
                if col and pd.notna(row.get(col)):
                    valor = str(row[col]).strip()
                    if len(valor) > 1:
                        texto_parts.append(f"{tipo}: {valor}")
                        metadata[tipo] = valor
                        
                        if tipo == 'monto':
                            try:
                                metadata['monto_numerico'] = float(re.sub(r'[^\d.-]', '', valor))
                            except:
                                pass
                        elif tipo == 'avance':
                            try:
                                metadata['avance_numerico'] = float(re.sub(r'[^\d.-]', '', valor))
                            except:
                                pass
            
            if texto_parts:
                chunks.append({
                    "content": " | ".join(texto_parts),
                    "metadata": metadata
                })
        
        chunks.extend(self._agregaciones_obras(registros, columnas, filename, sheet_name))
        
        return chunks

    def _procesar_presupuesto(self, df: pd.DataFrame, filename: str, sheet_name: str) -> List[Dict]:
        """Procesa datos de presupuesto/finanzas"""
        chunks = []
        registros = df.to_dict(orient='records')
        
        col_mapping = {
            'concepto': ['CONCEPTO', 'DESCRIPCION', 'PARTIDA', 'CONCEPTO_PRESUPUESTAL', 'DETALLE'],
            'monto': ['MONTO', 'IMPORTE', 'CANTIDAD', 'MONTO_PRESUPUESTADO', 'COSTO'],
            'partida': ['PARTIDA', 'CLAVE', 'CODIGO', 'NUMERO_PARTIDA'],
            'ejercicio': ['EJERCICIO', 'AÑO', 'FECHA', 'PERIODO'],
            'fuente': ['FUENTE', 'ORIGEN', 'PROCEDENCIA']
        }
        
        columnas = {tipo: self._encontrar_columna(df, posibles) for tipo, posibles in col_mapping.items()}
        
        total_presupuesto = 0
        
        for idx, row in enumerate(registros):
            texto_parts = []
            metadata = {
                "source": filename,
                "sheet": sheet_name,
                "row": idx + 2,
                "format": "Excel",
                "tipo_documento": "PRESUPUESTO",
                "tipo_contenido": "partida_presupuestal"
            }
            
            for tipo, col in columnas.items():
                if col and pd.notna(row.get(col)):
                    valor = str(row[col]).strip()
                    if len(valor) > 1:
                        texto_parts.append(f"{tipo}: {valor}")
                        metadata[tipo] = valor
                        
                        if tipo == 'monto':
                            try:
                                monto_num = float(re.sub(r'[^\d.-]', '', valor))
                                metadata['monto_numerico'] = monto_num
                                total_presupuesto += monto_num
                            except:
                                pass
            
            if texto_parts:
                chunks.append({
                    "content": " | ".join(texto_parts),
                    "metadata": metadata
                })
        
        if total_presupuesto > 0:
            resumen = {
                "content": f"RESUMEN PRESUPUESTAL - {sheet_name}\nTotal de partidas: {len(registros)}\nPresupuesto total: ${total_presupuesto:,.2f}",
                "metadata": {
                    "source": filename,
                    "sheet": sheet_name,
                    "format": "Excel",
                    "tipo_documento": "PRESUPUESTO",
                    "tipo_contenido": "resumen_presupuestal",
                    "total_partidas": len(registros),
                    "presupuesto_total": total_presupuesto
                }
            }
            chunks.append(resumen)
        
        return chunks

    def _procesar_inventario(self, df: pd.DataFrame, filename: str, sheet_name: str) -> List[Dict]:
        """Procesa datos de inventario/activos"""
        chunks = []
        registros = df.to_dict(orient='records')
        
        col_mapping = {
            'codigo': ['CODIGO', 'CÓDIGO', 'CLAVE', 'ID', 'NUMERO_INVENTARIO', 'FOLIO'],
            'descripcion': ['DESCRIPCION', 'DESCRIPCIÓN', 'NOMBRE', 'BIEN', 'ACTIVO', 'EQUIPO'],
            'cantidad': ['CANTIDAD', 'NUMERO', 'TOTAL', 'EXISTENCIAS'],
            'ubicacion': ['UBICACION', 'UBICACIÓN', 'ALMACEN', 'DEPARTAMENTO', 'RESGUARDO'],
            'estado': ['ESTADO', 'CONDICION', 'ESTATUS', 'SITUACION']
        }
        
        columnas = {tipo: self._encontrar_columna(df, posibles) for tipo, posibles in col_mapping.items()}
        
        for idx, row in enumerate(registros):
            texto_parts = []
            metadata = {
                "source": filename,
                "sheet": sheet_name,
                "row": idx + 2,
                "format": "Excel",
                "tipo_documento": "INVENTARIO",
                "tipo_contenido": "item_inventario"
            }
            
            for tipo, col in columnas.items():
                if col and pd.notna(row.get(col)):
                    valor = str(row[col]).strip()
                    if len(valor) > 1:
                        texto_parts.append(f"{tipo}: {valor}")
                        metadata[tipo] = valor
            
            if texto_parts:
                chunks.append({
                    "content": " | ".join(texto_parts),
                    "metadata": metadata
                })
        
        return chunks

    def _procesar_incidencias(self, df: pd.DataFrame, filename: str, sheet_name: str) -> List[Dict]:
        """Procesa datos de incidencias/baches/reportes"""
        chunks = []
        registros = df.to_dict(orient='records')
        
        col_mapping = {
            'id': ['ID', '#', 'NUMERO', 'FOLIO', 'CONSECUTIVO'],
            'descripcion': ['DESCRIPCION', 'DESCRIPCIÓN', 'DETALLE', 'COMENTARIO', 'OBSERVACIONES'],
            'ubicacion': ['UBICACION', 'UBICACIÓN', 'DIRECCION', 'LUGAR', 'SITIO'],
            'gravedad': ['GRAVEDAD', 'SEVERIDAD', 'PRIORIDAD', 'CRITICIDAD', 'NIVEL'],
            'estado': ['ESTADO', 'ESTATUS', 'SITUACION', 'FASE', 'ETAPA'],
            'fecha': ['FECHA', 'FECHA_REPORTE', 'REGISTRO', 'CREACION'],
            'responsable': ['RESPONSABLE', 'ATIENDE', 'ASIGNADO', 'ENCARGADO']
        }
        
        columnas = {tipo: self._encontrar_columna(df, posibles) for tipo, posibles in col_mapping.items()}
        
        gravedades = {}
        estados = {}
        
        for idx, row in enumerate(registros):
            texto_parts = []
            metadata = {
                "source": filename,
                "sheet": sheet_name,
                "row": idx + 2,
                "format": "Excel",
                "tipo_documento": "INCIDENCIAS",
                "tipo_contenido": "registro_incidencia"
            }
            
            for tipo, col in columnas.items():
                if col and pd.notna(row.get(col)):
                    valor = str(row[col]).strip()
                    if len(valor) > 1:
                        texto_parts.append(f"{tipo}: {valor}")
                        metadata[tipo] = valor
                        
                        if tipo == 'gravedad':
                            gravedades[valor] = gravedades.get(valor, 0) + 1
                        elif tipo == 'estado':
                            estados[valor] = estados.get(valor, 0) + 1
            
            if texto_parts:
                chunks.append({
                    "content": " | ".join(texto_parts),
                    "metadata": metadata
                })
        
        if gravedades or estados:
            resumen_parts = [f"RESUMEN DE INCIDENCIAS - {sheet_name}", f"Total: {len(registros)}"]
            
            if gravedades:
                resumen_parts.append("\nPOR GRAVEDAD:")
                for g, c in sorted(gravedades.items(), key=lambda x: x[1], reverse=True):
                    resumen_parts.append(f"  • {g}: {c}")
            
            if estados:
                resumen_parts.append("\nPOR ESTADO:")
                for e, c in sorted(estados.items(), key=lambda x: x[1], reverse=True):
                    resumen_parts.append(f"  • {e}: {c}")
            
            chunks.append({
                "content": "\n".join(resumen_parts),
                "metadata": {
                    "source": filename,
                    "sheet": sheet_name,
                    "format": "Excel",
                    "tipo_documento": "INCIDENCIAS",
                    "tipo_contenido": "resumen_incidencias",
                    "total_incidencias": len(registros),
                    "gravedades": gravedades,
                    "estados": estados
                }
            })
        
        return chunks

    def _procesar_contratos(self, df: pd.DataFrame, filename: str, sheet_name: str) -> List[Dict]:
        """Procesa datos de contratos/licitaciones"""
        chunks = []
        registros = df.to_dict(orient='records')
        
        col_mapping = {
            'numero': ['NUMERO', 'CONTRATO', 'FOLIO', 'NO_CONTRATO', 'CONTRATO_NO'],
            'proveedor': ['PROVEEDOR', 'CONTRATISTA', 'EMPRESA', 'RAZON_SOCIAL'],
            'monto': ['MONTO', 'IMPORTE', 'MONTO_CONTRATO', 'VALOR'],
            'fecha_inicio': ['FECHA_INICIO', 'INICIO', 'VIGENCIA_DESDE'],
            'fecha_fin': ['FECHA_FIN', 'TERMINO', 'VIGENCIA_HASTA', 'CONCLUSION'],
            'objeto': ['OBJETO', 'DESCRIPCION', 'CONCEPTO', 'SERVICIO', 'SUMINISTRO']
        }
        
        columnas = {tipo: self._encontrar_columna(df, posibles) for tipo, posibles in col_mapping.items()}
        
        for idx, row in enumerate(registros):
            texto_parts = []
            metadata = {
                "source": filename,
                "sheet": sheet_name,
                "row": idx + 2,
                "format": "Excel",
                "tipo_documento": "CONTRATOS",
                "tipo_contenido": "registro_contrato"
            }
            
            for tipo, col in columnas.items():
                if col and pd.notna(row.get(col)):
                    valor = str(row[col]).strip()
                    if len(valor) > 1:
                        texto_parts.append(f"{tipo}: {valor}")
                        metadata[tipo] = valor
            
            if texto_parts:
                chunks.append({
                    "content": " | ".join(texto_parts),
                    "metadata": metadata
                })
        
        return chunks

    def _procesar_generico(self, df: pd.DataFrame, filename: str, sheet_name: str) -> List[Dict]:
        """Procesa cualquier otro tipo de datos de forma genérica"""
        chunks = []
        
        if len(df) * len(df.columns) < 100:
            text_content = []
            for idx, row in df.iterrows():
                row_text = " | ".join([f"{df.columns[i]}: {v}" for i, v in enumerate(row) if pd.notna(v)])
                if row_text:
                    text_content.append(row_text)
            
            if text_content:
                chunks.append({
                    "content": "\n".join(text_content),
                    "metadata": {
                        "source": filename,
                        "sheet": sheet_name,
                        "format": "Excel",
                        "tipo_documento": "GENERAL",
                        "tipo_contenido": "datos_genericos",
                        "filas": len(df),
                        "columnas": len(df.columns)
                    }
                })
        else:
            registros = df.to_dict(orient='records')
            for idx, row in enumerate(registros):
                row_clean = {k: v for k, v in row.items() if pd.notna(v)}
                if row_clean:
                    chunks.append({
                        "content": " | ".join([f"{k}: {v}" for k, v in row_clean.items()]),
                        "metadata": {
                            "source": filename,
                            "sheet": sheet_name,
                            "row": idx + 2,
                            "format": "Excel",
                            "tipo_documento": "GENERAL",
                            "tipo_contenido": "registro_generico"
                        }
                    })
        
        return chunks

    # ==================== AGREGACIONES Y RESUMENES ====================

    def _agregaciones_obras(self, registros: List[Dict], columnas: Dict, filename: str, sheet_name: str) -> List[Dict]:
        """Genera agregaciones para obras"""
        chunks = []
        
        tipo_col = columnas.get('tipo')
        if tipo_col:
            tipos = {}
            montos_por_tipo = {}
            
            for row in registros:
                if pd.notna(row.get(tipo_col)):
                    tipo = str(row[tipo_col]).strip()
                    tipos[tipo] = tipos.get(tipo, 0) + 1
                    
                    monto_col = columnas.get('monto')
                    if monto_col and pd.notna(row.get(monto_col)):
                        try:
                            monto = float(re.sub(r'[^\d.-]', '', str(row[monto_col])))
                            montos_por_tipo[tipo] = montos_por_tipo.get(tipo, 0) + monto
                        except:
                            pass
            
            if tipos:
                content = [f"DISTRIBUCIÓN DE OBRAS POR TIPO - {sheet_name}", f"Total: {len(registros)} obras", ""]
                for tipo, count in sorted(tipos.items(), key=lambda x: x[1], reverse=True):
                    content.append(f"• {tipo}: {count} obras")
                    if tipo in montos_por_tipo:
                        content.append(f"  Monto total: ${montos_por_tipo[tipo]:,.2f}")
                
                chunks.append({
                    "content": "\n".join(content),
                    "metadata": {
                        "source": filename,
                        "sheet": sheet_name,
                        "format": "Excel",
                        "tipo_documento": "OBRAS",
                        "tipo_contenido": "agregacion_por_tipo",
                        "distribucion_tipos": tipos
                    }
                })
        
        monto_col = columnas.get('monto')
        if monto_col:
            max_monto = 0
            obra_max = None
            
            for row in registros:
                if pd.notna(row.get(monto_col)):
                    try:
                        monto = float(re.sub(r'[^\d.-]', '', str(row[monto_col])))
                        if monto > max_monto:
                            max_monto = monto
                            obra_max = row
                    except:
                        pass
            
            if obra_max and max_monto > 0:
                nombre_col = columnas.get('nombre')
                nombre = str(obra_max.get(nombre_col, 'No especificado')) if nombre_col else 'No especificado'
                tipo = str(obra_max.get(columnas.get('tipo'), 'No especificado')) if columnas.get('tipo') else 'No especificado'
                
                content = [
                    f"OBRA CON MAYOR PRESUPUESTO",
                    f"Nombre: {nombre}",
                    f"Monto: ${max_monto:,.2f}",
                    f"Tipo: {tipo}"
                ]
                
                chunks.append({
                    "content": "\n".join(content),
                    "metadata": {
                        "source": filename,
                        "sheet": sheet_name,
                        "format": "Excel",
                        "tipo_documento": "OBRAS",
                        "tipo_contenido": "mayor_presupuesto",
                        "monto_maximo": max_monto
                    }
                })
        
        return chunks

    def _resumen_personal(self, registros: List[Dict], columnas: Dict, filename: str, sheet_name: str) -> Optional[Dict]:
        """Genera resumen de personal"""
        puesto_col = columnas.get('puesto')
        if not puesto_col:
            return None
        
        puestos = {}
        for row in registros:
            if pd.notna(row.get(puesto_col)):
                puesto = str(row[puesto_col]).strip()
                puestos[puesto] = puestos.get(puesto, 0) + 1
        
        if puestos:
            content = [f"RESUMEN DE PERSONAL - {sheet_name}", f"Total: {len(registros)} empleados", "", "DISTRIBUCIÓN POR PUESTO:"]
            for puesto, count in sorted(puestos.items(), key=lambda x: x[1], reverse=True)[:10]:
                content.append(f"  • {puesto}: {count}")
            
            return {
                "content": "\n".join(content),
                "metadata": {
                    "source": filename,
                    "sheet": sheet_name,
                    "format": "Excel",
                    "tipo_documento": "PERSONAL",
                    "tipo_contenido": "resumen_personal",
                    "total_empleados": len(registros),
                    "distribucion_puestos": puestos
                }
            }
        
        return None

    def _crear_chunk_error(self, filename: str, error: str) -> Dict:
        """Crea chunk de error"""
        return {
            "content": f"ERROR EN PROCESAMIENTO\nArchivo: {filename}\nError: {error}",
            "metadata": {
                "source": filename,
                "format": "Excel",
                "tipo_contenido": "error",
                "error": error
            }
        }
    

    # ==================== MÉTODO PRINCIPAL ====================

    def process_file(self, file_path: str) -> List[Dict]:
        """
        Procesa cualquier archivo según su extensión
        """
        if not os.path.exists(file_path):
            logger.error(f"No existe: {file_path}")
            return []
        
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == ".pdf":
            return self.process_pdf(file_path)
        elif ext == ".docx":
            return self.process_word(file_path)
        elif ext in [".xlsx", ".xls"]:
            return self.process_excel(file_path)
        elif ext == ".txt":
            return self.process_txt(file_path)
        else:
            logger.warning(f"Formato no soportado: {ext}")
            return []