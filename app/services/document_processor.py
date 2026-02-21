import os
import pandas as pd
from pypdf import PdfReader
from docx import Document
class DocumentProcessor:
    @staticmethod
    def process_pdf(file_path: str) -> str:
        reader = PdfReader(file_path)
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        return " ".join(text_parts) # Corregido: fuera del loop
    @staticmethod
    def process_word(file_path: str) -> str:
        doc = Document(file_path)
        text = "\n".join([para.text for  para in doc.paragraphs])
        return text
    @staticmethod
    def process_excel(file_path: str) -> str:
        df = pd.read_excel(file_path) 
        rows_as_text = []
        for _, row in df.iterrows():
            # Convertimos cada fila en una cadena de texto
            row_str = ", ".join([f"{col}: {val}" for col, val in row.items()])
            print(row_str)
            rows_as_text.append(row_str)
        return "\n".join(rows_as_text)
    @staticmethod
    def process_file(file_path: str) -> str:
        extension = os.path.splitext(file_path)[1].lower()

        if extension == ".pdf":
            return DocumentProcessor.process_pdf(file_path)

        elif extension in [".docx"]:
            return DocumentProcessor.process_word(file_path)

        elif extension in [".xlsx", ".xls"]:
            return DocumentProcessor.process_excel(file_path)

        else:
            raise ValueError(f"Tipo de archivo no soportado: {extension}")
