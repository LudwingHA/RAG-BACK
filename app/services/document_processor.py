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
    
    def process_excel(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Procesador DEFINITIVO para Excel SICT.
        Limpia y estructura datos de:
        - Personal/RH
        - Obras e infraestructura
        - Baches y mantenimiento
        - Presupuestos
        - Contratos
        - Inventarios
        - Normativas
        """
        all_chunks = []
        start_time = time.time()
        
        try:
            filename = os.path.basename(file_path)
            logger.info(f"📊 Procesando Excel SICT: {filename}")
            
            tipo_documento = self._detectar_tipo_documento_sict(filename)
            logger.info(f"📋 Tipo detectado: {tipo_documento}")
            
            excel_file = self._leer_excel_robusto(file_path)
            if not excel_file:
                raise Exception("No se pudo leer el Excel")
            
            for sheet_name in excel_file.sheet_names:
                try:
                    logger.info(f"  Procesando hoja: {sheet_name}")
                    
                    df = self._leer_hoja_inteligente(excel_file, sheet_name)
                    if df is None or df.empty:
                        continue
                    
                    df = self._limpiar_dataframe(df)
                    
                    headers, header_row_idx = self._detectar_encabezados(df)
                    
                    columnas_por_tipo = self._clasificar_columnas(headers, df, header_row_idx)
                    
                    chunks_hoja = self._procesar_por_tipo(
                        df, headers, header_row_idx, filename, sheet_name,
                        tipo_documento, columnas_por_tipo
                    )
                    
                    all_chunks.extend(chunks_hoja)
                    
                    resumen = self._crear_resumen_tipo(
                        chunks_hoja, filename, sheet_name, tipo_documento
                    )
                    if resumen:
                        all_chunks.append(resumen)
                    
                except Exception as e:
                    logger.error(f"Error en hoja {sheet_name}: {e}")
                    continue
            
            all_chunks.append(self._crear_metadatos(filename, tipo_documento, len(all_chunks)))
            
            elapsed = time.time() - start_time
            logger.info(f"Excel procesado: {len(all_chunks)} chunks en {elapsed:.2f}s")
            
        except Exception as e:
            logger.exception(f"[Error crítico]: {e}")
            all_chunks.append(self._crear_chunk_error(filename, str(e)))
        
        return all_chunks

    def _leer_excel_robusto(self, file_path: str):
        """Intenta leer Excel con diferentes motores"""
        for engine in ['openpyxl', 'xlrd']:
            try:
                return pd.ExcelFile(file_path, engine=engine)
            except:
                continue
        return None

    def _leer_hoja_inteligente(self, excel_file, sheet_name: str):
        """Múltiples estrategias de lectura para una hoja"""
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

    def _limpiar_dataframe(self, df):
        """Limpieza general del DataFrame"""
        df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
        
        mask = df.apply(lambda row: row.astype(str).str.contains('^-+$|^=+$|^_+$').any(), axis=1)
        df = df[~mask]
        
        return df.reset_index(drop=True)

    def _detectar_encabezados(self, df):
        """Detecta la fila de encabezados"""
        for idx in range(min(10, len(df))):
            row = df.iloc[idx]
            row_text = ' '.join([str(x).upper() for x in row if pd.notna(x)])
            
            matches = sum(1 for palabra in self.ignorar_global if palabra in row_text)
            
            if matches >= 2:
                headers = [str(col).strip() if pd.notna(col) else f'COL_{j+1}' 
                          for j, col in enumerate(row)]
                logger.info(f"  Encabezados detectados en fila {idx+1}")
                return headers, idx
        
        return [f'COL_{j+1}' for j in range(len(df.columns))], -1

    def _clasificar_columnas(self, headers, df, header_row_idx):
        """Clasifica columnas por tipo de contenido"""
        tipos = {
            'nombre': [],
            'fecha': [],
            'monto': [],
            'ubicacion': [],
            'descripcion': [],
            'cantidad': [],
            'otros': []
        }
        
        for j, header in enumerate(headers):
            header_upper = header.upper()
            
            if any(p in header_upper for p in ['NOMBRE', 'APELLIDO', 'EMPLEADO']):
                tipos['nombre'].append(j)
            elif any(p in header_upper for p in ['FECHA', 'PERIODO', 'EJERCICIO']):
                tipos['fecha'].append(j)
            elif any(p in header_upper for p in ['MONTO', 'PRECIO', 'COSTO', 'IMPORTE']):
                tipos['monto'].append(j)
            elif any(p in header_upper for p in ['UBICACIÓN', 'DIRECCIÓN', 'DOMICILIO']):
                tipos['ubicacion'].append(j)
            elif any(p in header_upper for p in ['DESCRIPCIÓN', 'CONCEPTO', 'OBSERVACIONES']):
                tipos['descripcion'].append(j)
            elif any(p in header_upper for p in ['CANTIDAD', 'NÚMERO', 'TOTAL']):
                tipos['cantidad'].append(j)
            else:
                tipos['otros'].append(j)
        
        return tipos

    def _detectar_tipo_documento_sict(self, filename: str) -> str:
        """Detecta tipo de documento por nombre de archivo"""
        filename_upper = filename.upper()
        
        for tipo, patrones in self.patrones_tipos.items():
            if any(patron.upper() in filename_upper for patron in patrones):
                return tipo
        
        return 'GENERAL'

    def _procesar_por_tipo(self, df, headers, header_row_idx, filename, sheet_name, 
                          tipo_documento, columnas_por_tipo):
        """
        Procesa según el tipo de documento detectado
        """
        chunks = []
        data_start = header_row_idx + 1 if header_row_idx >= 0 else 0
        
        registros_validos = []
        
        for idx in range(data_start, len(df)):
            row = df.iloc[idx]
            

            if row.isna().all():
                continue
            

            if tipo_documento == 'PERSONAL':
                chunk = self._procesar_fila_personal(row, headers, idx, filename, sheet_name)
            elif tipo_documento == 'OBRAS':
                chunk = self._procesar_fila_obras(row, headers, idx, filename, sheet_name)
            elif tipo_documento == 'BACHES':
                chunk = self._procesar_fila_baches(row, headers, idx, filename, sheet_name)
            elif tipo_documento == 'PRESUPUESTO':
                chunk = self._procesar_fila_presupuesto(row, headers, idx, filename, sheet_name)
            elif tipo_documento == 'CONTRATOS':
                chunk = self._procesar_fila_contratos(row, headers, idx, filename, sheet_name)
            elif tipo_documento == 'INVENTARIO':
                chunk = self._procesar_fila_inventario(row, headers, idx, filename, sheet_name)
            else:
                chunk = self._procesar_fila_generica(row, headers, idx, filename, sheet_name)
            
            if chunk:
                chunks.append(chunk)
                registros_validos.append(chunk)
        
        logger.info(f"  {len(chunks)} registros válidos procesados")
        return chunks

    def _procesar_fila_personal(self, row, headers, idx, filename, sheet_name):
        """Procesa fila de personal/RH"""
        registro = []
        nombre = ""
        apellido = ""
        
        for j, header in enumerate(headers):
            if j >= len(row):
                continue
            
            valor = self._limpiar_valor(row.iloc[j], header)
            if not valor:
                continue
            
            header_upper = header.upper()
            
            # Capturar nombre y apellido para metadata
            if 'NOMBRE' in header_upper:
                nombre = valor
            elif 'APELLIDO' in header_upper:
                apellido = valor
            
            registro.append(f"{header}: {valor}")
        
        if registro and (nombre or apellido):
            return {
                "content": " | ".join(registro),
                "metadata": {
                    "source": filename,
                    "sheet": sheet_name,
                    "row": idx + 2,
                    "format": "Excel",
                    "tipo_documento": "PERSONAL",
                    "tipo_contenido": "registro_personal",
                    "nombre": nombre,
                    "apellido": apellido
                }
            }
        return None

    def _procesar_fila_obras(self, row, headers, idx, filename, sheet_name):
        """Procesa fila de obras/infraestructura"""
        registro = []
        ubicacion = ""
        monto = ""
        
        for j, header in enumerate(headers):
            if j >= len(row):
                continue
            
            valor = self._limpiar_valor(row.iloc[j], header)
            if not valor:
                continue
            
            header_upper = header.upper()
            
            if 'UBICACIÓN' in header_upper or 'DIRECCIÓN' in header_upper:
                ubicacion = valor
            elif 'MONTO' in header_upper or 'PRESUPUESTO' in header_upper:
                monto = valor
            
            registro.append(f"{header}: {valor}")
        
        if registro:
            return {
                "content": " | ".join(registro),
                "metadata": {
                    "source": filename,
                    "sheet": sheet_name,
                    "row": idx + 2,
                    "format": "Excel",
                    "tipo_documento": "OBRAS",
                    "tipo_contenido": "registro_obra",
                    "ubicacion": ubicacion,
                    "monto": monto
                }
            }
        return None

    def _procesar_fila_baches(self, row, headers, idx, filename, sheet_name):
        """Procesa fila de baches/mantenimiento"""
        registro = []
        ubicacion = ""
        severidad = ""
        
        for j, header in enumerate(headers):
            if j >= len(row):
                continue
            
            valor = self._limpiar_valor(row.iloc[j], header)
            if not valor:
                continue
            
            header_upper = header.upper()
            
            if 'UBICACIÓN' in header_upper or 'DIRECCIÓN' in header_upper:
                ubicacion = valor
            elif 'SEVERIDAD' in header_upper or 'GRAVEDAD' in header_upper:
                severidad = valor
            
            registro.append(f"{header}: {valor}")
        
        if registro:
            return {
                "content": " | ".join(registro),
                "metadata": {
                    "source": filename,
                    "sheet": sheet_name,
                    "row": idx + 2,
                    "format": "Excel",
                    "tipo_documento": "BACHES",
                    "tipo_contenido": "reporte_bache",
                    "ubicacion": ubicacion,
                    "severidad": severidad
                }
            }
        return None

    def _procesar_fila_presupuesto(self, row, headers, idx, filename, sheet_name):
        """Procesa fila de presupuesto/finanzas"""
        registro = []
        monto_total = 0
        concepto = ""
        
        for j, header in enumerate(headers):
            if j >= len(row):
                continue
            
            valor = self._limpiar_valor(row.iloc[j], header)
            if not valor:
                continue
            
            header_upper = header.upper()
            
            if 'CONCEPTO' in header_upper or 'DESCRIPCIÓN' in header_upper:
                concepto = valor
            elif 'MONTO' in header_upper or 'IMPORTE' in header_upper or 'TOTAL' in header_upper:
                try:
                    monto_total = float(re.sub(r'[^\d.-]', '', valor))
                except:
                    pass
            
            registro.append(f"{header}: {valor}")
        
        if registro:
            return {
                "content": " | ".join(registro),
                "metadata": {
                    "source": filename,
                    "sheet": sheet_name,
                    "row": idx + 2,
                    "format": "Excel",
                    "tipo_documento": "PRESUPUESTO",
                    "tipo_contenido": "partida_presupuestal",
                    "concepto": concepto,
                    "monto": monto_total
                }
            }
        return None

    def _procesar_fila_contratos(self, row, headers, idx, filename, sheet_name):
        """Procesa fila de contratos/licitaciones"""
        registro = []
        numero_contrato = ""
        proveedor = ""
        
        for j, header in enumerate(headers):
            if j >= len(row):
                continue
            
            valor = self._limpiar_valor(row.iloc[j], header)
            if not valor:
                continue
            
            header_upper = header.upper()
            
            if 'CONTRATO' in header_upper or 'LICITACIÓN' in header_upper:
                numero_contrato = valor
            elif 'PROVEEDOR' in header_upper or 'CONTRATISTA' in header_upper:
                proveedor = valor
            
            registro.append(f"{header}: {valor}")
        
        if registro:
            return {
                "content": " | ".join(registro),
                "metadata": {
                    "source": filename,
                    "sheet": sheet_name,
                    "row": idx + 2,
                    "format": "Excel",
                    "tipo_documento": "CONTRATOS",
                    "tipo_contenido": "registro_contrato",
                    "numero_contrato": numero_contrato,
                    "proveedor": proveedor
                }
            }
        return None

    def _procesar_fila_inventario(self, row, headers, idx, filename, sheet_name):
        """Procesa fila de inventario/activos"""
        registro = []
        codigo = ""
        descripcion = ""
        
        for j, header in enumerate(headers):
            if j >= len(row):
                continue
            
            valor = self._limpiar_valor(row.iloc[j], header)
            if not valor:
                continue
            
            header_upper = header.upper()
            
            if 'CÓDIGO' in header_upper or 'CLAVE' in header_upper or 'ID' in header_upper:
                codigo = valor
            elif 'DESCRIPCIÓN' in header_upper or 'CONCEPTO' in header_upper:
                descripcion = valor
            
            registro.append(f"{header}: {valor}")
        
        if registro:
            return {
                "content": " | ".join(registro),
                "metadata": {
                    "source": filename,
                    "sheet": sheet_name,
                    "row": idx + 2,
                    "format": "Excel",
                    "tipo_documento": "INVENTARIO",
                    "tipo_contenido": "item_inventario",
                    "codigo": codigo,
                    "descripcion": descripcion
                }
            }
        return None

    def _procesar_fila_generica(self, row, headers, idx, filename, sheet_name):
        """Procesa fila genérica para otros tipos"""
        registro = []
        
        for j, header in enumerate(headers):
            if j >= len(row):
                continue
            
            valor = self._limpiar_valor(row.iloc[j], header)
            if valor:
                registro.append(f"{header}: {valor}")
        
        if registro:
            return {
                "content": " | ".join(registro),
                "metadata": {
                    "source": filename,
                    "sheet": sheet_name,
                    "row": idx + 2,
                    "format": "Excel",
                    "tipo_documento": "GENERAL",
                    "tipo_contenido": "registro_general"
                }
            }
        return None

    def _crear_resumen_tipo(self, chunks, filename, sheet_name, tipo_documento):
        """
        Crea un resumen especializado según el tipo de documento
        """
        if not chunks:
            return None
        
        if tipo_documento == 'PERSONAL':
            return self._crear_resumen_personal(chunks, filename, sheet_name)
        elif tipo_documento == 'OBRAS':
            return self._crear_resumen_obras(chunks, filename, sheet_name)
        elif tipo_documento == 'BACHES':
            return self._crear_resumen_baches(chunks, filename, sheet_name)
        elif tipo_documento == 'PRESUPUESTO':
            return self._crear_resumen_presupuesto(chunks, filename, sheet_name)
        elif tipo_documento == 'CONTRATOS':
            return self._crear_resumen_contratos(chunks, filename, sheet_name)
        elif tipo_documento == 'INVENTARIO':
            return self._crear_resumen_inventario(chunks, filename, sheet_name)
        
        return None

    def _crear_resumen_personal(self, chunks, filename, sheet_name):
        """Resumen para documentos de personal"""
        personas = set()
        
        for chunk in chunks:
            nombre = chunk['metadata'].get('nombre', '')
            apellido = chunk['metadata'].get('apellido', '')
            
            if nombre and len(nombre) > 2:
                nombre_completo = f"{nombre} {apellido}".strip()
                if len(nombre_completo) > 3:
                    personas.add(nombre_completo)
        
        if personas:
            contenido = [
                f"RESUMEN DE PERSONAL - {filename}",
                f"Total de personas: {len(personas)}",
                "",
                "LISTA DE PERSONAL:"
            ]
            for persona in sorted(personas):
                contenido.append(f"• {persona}")
            
            return {
                "content": "\n".join(contenido),
                "metadata": {
                    "source": filename,
                    "sheet": sheet_name,
                    "format": "Excel",
                    "tipo_documento": "PERSONAL",
                    "tipo_contenido": "resumen_personal",
                    "total_registros": len(personas)
                }
            }
        return None

    def _crear_resumen_obras(self, chunks, filename, sheet_name):
        """Resumen para documentos de obras"""
        obras = []
        montos = []
        
        for chunk in chunks:
            metadata = chunk['metadata']
            if metadata.get('ubicacion'):
                obras.append(metadata['ubicacion'])
            if metadata.get('monto'):
                try:
                    montos.append(float(metadata['monto']))
                except:
                    pass
        
        contenido = [
            f"RESUMEN DE OBRAS - {filename}",
            f"Total de registros: {len(chunks)}",
            f"Ubicaciones identificadas: {len(set(obras))}"
        ]
        
        if montos:
            contenido.append(f"Presupuesto total: ${sum(montos):,.2f}")
        
        return {
            "content": "\n".join(contenido),
            "metadata": {
                "source": filename,
                "sheet": sheet_name,
                "format": "Excel",
                "tipo_documento": "OBRAS",
                "tipo_contenido": "resumen_obras",
                "total_registros": len(chunks)
            }
        }

    def _crear_resumen_baches(self, chunks, filename, sheet_name):
        """Resumen para documentos de baches"""
        ubicaciones = set()
        
        for chunk in chunks:
            if chunk['metadata'].get('ubicacion'):
                ubicaciones.add(chunk['metadata']['ubicacion'])
        
        contenido = [
            f"RESUMEN DE BACHES - {filename}",
            f"Total de reportes: {len(chunks)}",
            f"Ubicaciones afectadas: {len(ubicaciones)}"
        ]
        
        return {
            "content": "\n".join(contenido),
            "metadata": {
                "source": filename,
                "sheet": sheet_name,
                "format": "Excel",
                "tipo_documento": "BACHES",
                "tipo_contenido": "resumen_baches",
                "total_registros": len(chunks)
            }
        }

    def _crear_resumen_presupuesto(self, chunks, filename, sheet_name):
        """Resumen para documentos de presupuesto"""
        total = 0
        conceptos = set()
        
        for chunk in chunks:
            if chunk['metadata'].get('monto'):
                total += chunk['metadata']['monto']
            if chunk['metadata'].get('concepto'):
                conceptos.add(chunk['metadata']['concepto'])
        
        contenido = [
            f"RESUMEN PRESUPUESTAL - {filename}",
            f"Total de partidas: {len(chunks)}",
            f"Monto total: ${total:,.2f}",
            f"Conceptos distintos: {len(conceptos)}"
        ]
        
        return {
            "content": "\n".join(contenido),
            "metadata": {
                "source": filename,
                "sheet": sheet_name,
                "format": "Excel",
                "tipo_documento": "PRESUPUESTO",
                "tipo_contenido": "resumen_presupuesto",
                "total_registros": len(chunks),
                "monto_total": total
            }
        }

    def _crear_resumen_contratos(self, chunks, filename, sheet_name):
        """Resumen para documentos de contratos"""
        contratos = set()
        proveedores = set()
        
        for chunk in chunks:
            if chunk['metadata'].get('numero_contrato'):
                contratos.add(chunk['metadata']['numero_contrato'])
            if chunk['metadata'].get('proveedor'):
                proveedores.add(chunk['metadata']['proveedor'])
        
        contenido = [
            f"RESUMEN DE CONTRATOS - {filename}",
            f"Total de registros: {len(chunks)}",
            f"Contratos identificados: {len(contratos)}",
            f"Proveedores: {len(proveedores)}"
        ]
        
        return {
            "content": "\n".join(contenido),
            "metadata": {
                "source": filename,
                "sheet": sheet_name,
                "format": "Excel",
                "tipo_documento": "CONTRATOS",
                "tipo_contenido": "resumen_contratos",
                "total_registros": len(chunks)
            }
        }

    def _crear_resumen_inventario(self, chunks, filename, sheet_name):
        """Resumen para documentos de inventario"""
        items = set()
        
        for chunk in chunks:
            if chunk['metadata'].get('descripcion'):
                items.add(chunk['metadata']['descripcion'])
            elif chunk['metadata'].get('codigo'):
                items.add(chunk['metadata']['codigo'])
        
        contenido = [
            f"RESUMEN DE INVENTARIO - {filename}",
            f"Total de items: {len(chunks)}",
            f"Items distintos: {len(items)}"
        ]
        
        return {
            "content": "\n".join(contenido),
            "metadata": {
                "source": filename,
                "sheet": sheet_name,
                "format": "Excel",
                "tipo_documento": "INVENTARIO",
                "tipo_contenido": "resumen_inventario",
                "total_registros": len(chunks)
            }
        }

    def _crear_metadatos(self, filename, tipo_documento, total_chunks):
        """Crea chunk de metadatos"""
        contenido = [
            f"METADATOS DEL DOCUMENTO",
            f"Archivo: {filename}",
            f"Tipo documento: {tipo_documento}",
            f"Fecha procesamiento: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            f"Total chunks generados: {total_chunks}"
        ]
        
        return {
            "content": "\n".join(contenido),
            "metadata": {
                "source": filename,
                "format": "Excel",
                "tipo_documento": tipo_documento,
                "tipo_contenido": "metadatos",
                "total_chunks": total_chunks
            }
        }

    def _crear_chunk_error(self, filename, error):
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