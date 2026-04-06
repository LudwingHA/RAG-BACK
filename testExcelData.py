import logger
def diagnosticar_excel(self, file_path: str):
    """Diagnostica cómo se está procesando el Excel"""
    logger.info(f"🔍 Diagnosticando: {file_path}")
    
    excel_file = pd.ExcelFile(file_path)
    
    for sheet_name in excel_file.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        logger.info(f"\n📄 Hoja: {sheet_name}")
        logger.info(f"   Filas: {len(df)}, Columnas: {len(df.columns)}")
        logger.info(f"   Columnas: {list(df.columns)[:10]}")
        
        # Buscar columna de tipo
        tipo_col = None
        for col in df.columns:
            if 'TIPO' in str(col).upper():
                tipo_col = col
                break
        
        if tipo_col:
            tipos = df[tipo_col].value_counts()
            logger.info(f"   Tipos encontrados en columna '{tipo_col}':")
            for tipo, count in tipos.items():
                logger.info(f"      - {tipo}: {count}")
        else:
            logger.info(f"   ⚠️ No se encontró columna de TIPO")
        
        # Mostrar primeras filas
        logger.info(f"   Primeras 3 filas:")
        for idx in range(min(3, len(df))):
            logger.info(f"      Fila {idx}: {df.iloc[idx].to_dict()}")