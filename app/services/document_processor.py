import os
import re
import unicodedata
import pandas as pd
from pypdf import PdfReader
from docx import Document
from typing import List, Dict, Any
import logging
from datetime import datetime
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [DocumentProcessor] - %(message)s'
)

logger = logging.getLogger(__name__)


class DocumentProcessor:

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap debe ser menor que chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""

        text = unicodedata.normalize('NFKC', text)
        text = re.sub(r'[\r\n\t]+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _generate_chunks(self, text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
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
    def process_pdf(self, file_path: str):
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
                        "format": "PDF"
                    }

                    all_chunks.extend(self._generate_chunks(text, metadata))

        except Exception as e:
            logger.exception(f"Error PDF: {e}")

        return all_chunks
    def process_word(self, file_path: str):
        all_chunks = []

        try:
            doc = Document(file_path)
            filename = os.path.basename(file_path)

            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = self._normalize_text("\n".join(paragraphs))

            if text:
                metadata = {
                    "source": filename,
                    "format": "Word"
                }

                all_chunks.extend(self._generate_chunks(text, metadata))

        except Exception as e:
            logger.exception(f"Error Word: {e}")

        return all_chunks
    
def process_excel(self, file_path: str) -> List[Dict[str, Any]]:
    """
    Procesador ESPECIALIZADO para documentos SICT.
    Maneja formatos oficiales mexicanos, nomenclaturas gubernamentales y datos estructurales.
    """
    all_chunks = []
    start_time = time.time()
    
    try:
        filename = os.path.basename(file_path)
        logger.info(f"📊 SICT - Procesando Excel: {filename}")
        
        # 1. DETECCIÓN DE TIPO DE DOCUMENTO SICT
        documento_tipo = self._detectar_tipo_documento_sict(filename)
        
        # 2. LECTURA ROBUSTA
        excel_file = None
        for engine in ['openpyxl', 'xlrd']:
            try:
                excel_file = pd.ExcelFile(file_path, engine=engine)
                logger.info(f"✅ Motor {engine} exitoso")
                break
            except:
                continue
        
        if excel_file is None:
            raise Exception("No se pudo leer el Excel SICT")
        
        # 3. PROCESAR CADA HOJA
        for sheet_name in excel_file.sheet_names:
            try:
                logger.info(f"Procesando hoja SICT: {sheet_name}")
                
                # 4. ESTRATEGIAS DE LECTURA SICT
                df = self._leer_hoja_inteligente(excel_file, sheet_name)
                
                if df is None or df.empty:
                    continue
                
                # 5. LIMPIEZA ESPECIALIZADA SICT
                df = self._limpiar_dataframe_sict(df)
                
                # 6. DETECCIÓN DE ENCABEZADOS GUBERNAMENTALES
                headers, header_row_idx = self._detectar_encabezados_sict(df)
                
                # 7. DETECCIÓN DE COLUMNAS CRÍTICAS SICT
                columnas_criticas = self._identificar_columnas_criticas_sict(headers)
                
                # 8. GENERACIÓN DE CHUNKS ESPECIALIZADOS
                
                # ESTRATEGIA 1: Registros individuales con formato oficial
                individual_chunks = self._crear_chunks_individuales_sict(
                    df, headers, header_row_idx, filename, sheet_name, columnas_criticas
                )
                
                # ESTRATEGIA 2: Agrupaciones por dependencia/área (típico SICT)
                if 'DEPENDENCIA' in columnas_criticas or 'AREA' in columnas_criticas:
                    chunks_agrupados = self._agrupar_por_dependencia_sict(
                        individual_chunks, df, headers, filename, sheet_name
                    )
                    all_chunks.extend(chunks_agrupados)
                
                # ESTRATEGIA 3: Resúmenes ejecutivos (para reportes)
                resumen = self._crear_resumen_ejecutivo_sict(
                    df, headers, filename, sheet_name, documento_tipo
                )
                if resumen:
                    all_chunks.append(resumen)
                
                # ESTRATEGIA 4: Metadatos del documento SICT
                metadata_chunk = self._crear_chunk_metadatos_sict(
                    filename, sheet_name, documento_tipo, df, headers
                )
                all_chunks.append(metadata_chunk)
                
                # Añadir chunks individuales
                all_chunks.extend(individual_chunks)
                
            except Exception as e:
                logger.error(f"Error en hoja SICT {sheet_name}: {e}")
                continue
        
        # 9. LOG DE ESTADÍSTICAS SICT
        elapsed = time.time() - start_time
        logger.info(f"✅ SICT Excel procesado: {len(all_chunks)} chunks en {elapsed:.2f}s")
        
        # 10. CHUNK DE CONTROL INTERNO
        all_chunks.append(self._crear_chunk_control_sict(filename, len(all_chunks)))
        
    except Exception as e:
        logger.exception(f"💥 Error crítico SICT: {e}")
        all_chunks.append(self._crear_chunk_error_sict(filename, str(e)))
    
    return all_chunks

def _detectar_tipo_documento_sict(self, filename: str) -> str:
    """Detecta el tipo de documento SICT por nombre"""
    filename_upper = filename.upper()
    
    tipos = {
        'PERSONAL': ['PERSONAL', 'EMPLOYEES', 'TRABAJADORES', 'NOMINA', 'RH'],
        'OBRAS': ['OBRA', 'PROYECTO', 'INFRAESTRUCTURA', 'CARRETERA', 'PUENTE'],
        'CONTRATOS': ['CONTRATO', 'LICITACION', 'PROVEEDORES', 'ADQUISICIONES'],
        'PERMISOS': ['PERMISO', 'AUTORIZACION', 'LICENCIA', 'CONCESION'],
        'INVENTARIO': ['INVENTARIO', 'BIENES', 'ACTIVOS', 'EQUIPAMIENTO'],
        'PRESUPUESTO': ['PRESUPUESTO', 'FINANZAS', 'GASTO', 'EJERCICIO']
    }
    
    for tipo, patrones in tipos.items():
        if any(patron in filename_upper for patron in patrones):
            return tipo
    
    return 'GENERAL'

def _leer_hoja_inteligente(self, excel_file, sheet_name: str):
    """Múltiples estrategias de lectura para hojas SICT"""
    estrategias = [
        lambda: pd.read_excel(excel_file, sheet_name=sheet_name, header=0),
        lambda: pd.read_excel(excel_file, sheet_name=sheet_name, header=None),
        lambda: pd.read_excel(excel_file, sheet_name=sheet_name, skiprows=range(3), header=0),
        lambda: pd.read_excel(excel_file, sheet_name=sheet_name, dtype=str),
        lambda: pd.read_excel(excel_file, sheet_name=sheet_name, encoding='latin1')
    ]
    
    for estrategia in estrategias:
        try:
            df = estrategia()
            if df is not None and not df.empty:
                return df
        except:
            continue
    
    return None

def _limpiar_dataframe_sict(self, df):
    """Limpieza especializada para datos SICT"""
    # Eliminar filas/columnas completamente vacías
    df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
    
    # Eliminar filas que son solo separadores (----, ====, etc)
    mask = df.apply(lambda row: row.astype(str).str.contains('^-+$|^=+$|^_+$').any(), axis=1)
    df = df[~mask]
    
    # Resetear índice
    df = df.reset_index(drop=True)
    
    return df

def _detectar_encabezados_sict(self, df):
    """Detecta encabezados en formatos SICT"""
    patrones_sict = [
        # Español (formatos SICT)
        'NOMBRE', 'APELLIDO', 'RFC', 'CURP', 'DEPENDENCIA', 'AREA',
        'PUESTO', 'CARGO', 'ADSCRIPCION', 'DOMICILIO', 'TELEFONO',
        'CORREO', 'FECHA INGRESO', 'NUMERO EMPLEADO', 'PLAZA',
        'HORARIO', 'JEFE', 'DIRECTOR', 'SECRETARIA',
        # Inglés (posibles)
        'NAME', 'LAST NAME', 'ID', 'DEPARTMENT', 'POSITION',
        'PHONE', 'EMAIL', 'START DATE', 'EMPLOYEE NUMBER'
    ]
    
    headers = []
    header_row_idx = 0
    
    # Buscar en primeras 10 filas
    for idx in range(min(10, len(df))):
        row = df.iloc[idx]
        row_text = ' '.join([str(x).upper() for x in row if pd.notna(x)])
        
        # Calcular score de coincidencia
        matches = sum(1 for patron in patrones_sict if patron.upper() in row_text)
        
        if matches >= 2:  # Al menos 2 coincidencias
            headers = [str(col).strip() if pd.notna(col) else f'COL_{j+1}' 
                      for j, col in enumerate(row)]
            header_row_idx = idx
            logger.info(f"✅ Encabezados SICT detectados en fila {idx+1} ({matches} coincidencias)")
            break
    
    # Si no detectó, crear encabezados genéricos
    if not headers:
        headers = [f'COLUMNA_{j+1}' for j in range(len(df.columns))]
        header_row_idx = -1
    
    return headers, header_row_idx

def _identificar_columnas_criticas_sict(self, headers):
    """Identifica columnas importantes en documentos SICT"""
    criticas = {
        'NOMBRE': ['NOMBRE', 'NAME', 'NOM'],
        'APELLIDO': ['APELLIDO', 'AP', 'LAST'],
        'RFC': ['RFC', 'RFC'],
        'CURP': ['CURP', 'CURP'],
        'DEPENDENCIA': ['DEPENDENCIA', 'DEP', 'DEPARTMENT'],
        'AREA': ['AREA', 'AREA', 'ÁREA'],
        'PUESTO': ['PUESTO', 'CARGO', 'POSITION'],
        'FECHA': ['FECHA', 'DATE'],
        'NUM_EMPLEADO': ['NUM', 'NO.', 'NÚMERO', 'NUMBER', 'ID', 'CLAVE']
    }
    
    encontradas = {}
    headers_upper = [str(h).upper() for h in headers]
    
    for clave, patrones in criticas.items():
        for i, header in enumerate(headers_upper):
            if any(patron in header for patron in patrones):
                encontradas[clave] = i
                break
    
    return encontradas

def _crear_chunks_individuales_sict(self, df, headers, header_row_idx, filename, sheet_name, columnas_criticas):
    """Crea chunks con formato oficial SICT"""
    chunks = []
    data_start = header_row_idx + 1 if header_row_idx >= 0 else 0
    
    for idx in range(data_start, len(df)):
        row = df.iloc[idx]
        
        # Saltar filas vacías
        if row.isna().all():
            continue
        
        # Construir registro con formato SICT
        registro = []
        
        # Priorizar información crítica
        for campo, col_idx in columnas_criticas.items():
            if col_idx < len(row) and pd.notna(row.iloc[col_idx]):
                valor = str(row.iloc[col_idx]).strip()
                if valor and valor.lower() != 'nan':
                    registro.append(f"{campo}: {valor}")
        
        # Agregar otras columnas
        for j, val in enumerate(row):
            if j < len(headers) and j not in columnas_criticas.values():
                if pd.notna(val) and str(val).strip():
                    col_name = headers[j]
                    valor = str(val).strip()
                    if valor.lower() != 'nan':
                        registro.append(f"{col_name}: {valor}")
        
        if registro:
            chunks.append({
                "content": " | ".join(registro),
                "metadata": {
                    "source": filename,
                    "sheet": sheet_name,
                    "row": idx + 2,
                    "format": "Excel",
                    "type": "registro_sict",
                    "campos_criticos": list(columnas_criticas.keys())
                }
            })
    
    return chunks

def _agrupar_por_dependencia_sict(self, individual_chunks, df, headers, filename, sheet_name):
    """Agrupa registros por dependencia/área SICT"""
    chunks = []
    
    # Identificar columna de dependencia
    dep_col = None
    for j, header in enumerate(headers):
        if any(p in str(header).upper() for p in ['DEPENDENCIA', 'AREA', 'DEPARTMENT']):
            dep_col = j
            break
    
    if dep_col is None:
        return chunks
    
    # Agrupar
    grupos = {}
    for chunk in individual_chunks:
        # Extraer dependencia del chunk
        lines = chunk['content'].split(' | ')
        dependencia = 'NO ESPECIFICADA'
        
        for line in lines:
            if line.startswith('DEPENDENCIA:') or line.startswith('AREA:'):
                dependencia = line.split(':', 1)[1].strip()
                break
        
        if dependencia not in grupos:
            grupos[dependencia] = []
        grupos[dependencia].append(chunk)
    
    # Crear chunks por dependencia
    for dependencia, chunks_grupo in grupos.items():
        if len(chunks_grupo) >= 1:
            contenido = f"DEPENDENCIA SICT: {dependencia}\n"
            contenido += f"Total de registros: {len(chunks_grupo)}\n\n"
            
            for i, c in enumerate(chunks_grupo[:15]):  # Limitar a 15
                contenido += f"Registro {i+1}:\n{c['content']}\n\n"
            
            chunks.append({
                "content": contenido,
                "metadata": {
                    "source": filename,
                    "sheet": sheet_name,
                    "dependencia": dependencia,
                    "format": "Excel",
                    "type": "agrupacion_sict",
                    "total_registros": len(chunks_grupo)
                }
            })
    
    return chunks

def _crear_resumen_ejecutivo_sict(self, df, headers, filename, sheet_name, documento_tipo):
    """Crea un resumen ejecutivo del documento SICT"""
    try:
        total_filas = len(df)
        total_columnas = len(headers)
        
        resumen = f"RESUMEN EJECUTIVO SICT\n"
        resumen += f"Documento: {filename}\n"
        resumen += f"Tipo: {documento_tipo}\n"
        resumen += f"Hoja: {sheet_name}\n"
        resumen += f"Total registros: {total_filas}\n"
        resumen += f"Total columnas: {total_columnas}\n\n"
        
        resumen += "ESTRUCTURA DE DATOS:\n"
        for i, header in enumerate(headers[:10]):  # Primeras 10 columnas
            # Muestrear valores
            valores = []
            for j in range(min(5, len(df))):
                if j < len(df) and i < len(df.columns):
                    val = df.iloc[j, i]
                    if pd.notna(val) and str(val).strip():
                        valores.append(str(val).strip())
            
            if valores:
                resumen += f"• {header}: {', '.join(valores[:3])}\n"
        
        return {
            "content": resumen,
            "metadata": {
                "source": filename,
                "sheet": sheet_name,
                "format": "Excel",
                "type": "resumen_ejecutivo_sict",
                "documento_tipo": documento_tipo,
                "total_registros": total_filas
            }
        }
    except:
        return None

def _crear_chunk_metadatos_sict(self, filename, sheet_name, documento_tipo, df, headers):
    """Crea chunk con metadatos del documento SICT"""
    return {
        "content": f"METADATOS DOCUMENTO SICT\n"
                   f"Archivo: {filename}\n"
                   f"Hoja: {sheet_name}\n"
                   f"Tipo documento: {documento_tipo}\n"
                   f"Fecha procesamiento: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
                   f"Filas: {len(df)}\n"
                   f"Columnas: {len(headers)}\n"
                   f"Encabezados: {', '.join(headers[:15])}",
        "metadata": {
            "source": filename,
            "sheet": sheet_name,
            "format": "Excel",
            "type": "metadatos_sict",
            "documento_tipo": documento_tipo
        }
    }

def _crear_chunk_control_sict(self, filename, total_chunks):
    """Chunk de control para auditoría"""
    return {
        "content": f"CONTROL DE PROCESAMIENTO SICT\n"
                   f"Archivo: {filename}\n"
                   f"Total chunks generados: {total_chunks}\n"
                   f"Timestamp: {datetime.now().isoformat()}",
        "metadata": {
            "source": filename,
            "format": "Excel",
            "type": "control_sict",
            "timestamp": datetime.now().isoformat()
        }
    }

def _crear_chunk_error_sict(self, filename, error):
    """Chunk de error para debugging"""
    return {
        "content": f"ERROR EN PROCESAMIENTO SICT\n"
                   f"Archivo: {filename}\n"
                   f"Error: {error}\n"
                   f"Timestamp: {datetime.now().isoformat()}",
        "metadata": {
            "source": filename,
            "format": "Excel",
            "type": "error_sict",
            "error": error
        }
    }

    def process_txt(self, file_path: str):
        all_chunks = []

        try:
            filename = os.path.basename(file_path)

            with open(file_path, "r", encoding="utf-8") as f:
                text = self._normalize_text(f.read())

            if text:
                metadata = {
                    "source": filename,
                    "format": "TXT"
                }

                all_chunks.extend(self._generate_chunks(text, metadata))

        except Exception as e:
            logger.exception(f"Error TXT: {e}")

        return all_chunks

    def process_file(self, file_path: str):

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