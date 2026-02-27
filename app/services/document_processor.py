import os
import re
import unicodedata
import pandas as pd
from pypdf import PdfReader
from docx import Document
from typing import List, Dict, Any
import logging

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
    def process_excel(self, file_path: str):
        all_chunks = []

        try:
            filename = os.path.basename(file_path)

            sheets = pd.read_excel(
                file_path,
                sheet_name=None,
                engine="openpyxl",
                header=None
            )

            for sheet_name, df in sheets.items():
                df = df.dropna(axis=1, how="all")
                df = df.dropna(axis=0, how="all")
                if df.empty:
                    continue
                df = df.astype(str)
                for idx, row in df.iterrows():
                    row_content = " | ".join(
                        str(val).strip()
                        for val in row
                        if val.strip().lower() != "nan"
                    )
                    if row_content:
                        metadata = {
                            "source": filename,
                            "sheet": sheet_name,
                            "row": int(idx) + 1,
                            "format": "Excel"
                        }

                        all_chunks.append({
                            "content": row_content,
                            "metadata": metadata
                        })

        except Exception as e:
            logger.exception(f"Error Excel: {e}")

        return all_chunks

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