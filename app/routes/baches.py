
from fastapi import File, UploadFile, HTTPException, APIRouter
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List
BASE_DIR = Path("/Applications/XAMPP/xamppfiles/htdocs/01-bache")
RESULTADOS_DIR = BASE_DIR / "resultados"
RESULTADOS_DIR.mkdir(exist_ok=True)

router = APIRouter()

@router.get("/api/baches/carpetas")
async def listar_carpetas():
    carpetas = []
    
    for dir_path in RESULTADOS_DIR.glob("resultados_*"):
        if dir_path.is_dir():
            json_files = list(dir_path.glob("*.json"))
            if json_files:
                # Obtener fecha del nombre de la carpeta
                fecha_str = dir_path.name.replace("resultados_", "")
                try:
                    fecha = datetime.strptime(fecha_str, "%Y%m%d_%H%M%S")
                    fecha_formateada = fecha.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    fecha_formateada = datetime.fromtimestamp(dir_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                
                carpetas.append({
                    "name": dir_path.name,
                    "path": str(dir_path.relative_to(BASE_DIR)),
                    "date": fecha_formateada,
                    "json_files": [f.name for f in json_files]
                })
    

    carpetas.sort(key=lambda x: x["date"], reverse=True)
    return carpetas

@router.get("/api/baches/json-files")
async def listar_json_files(folder: str):

    folder_path = BASE_DIR / folder
    
    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")
    
    json_files = list(folder_path.glob("*.json"))
    return [f.name for f in json_files]

@router.get("/api/baches/detecciones")
async def obtener_detecciones(folder: str, file: str):

    file_path = BASE_DIR / folder / file
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        

        if "detecciones" in data:
            for deteccion in data["detecciones"]:

                if "segundo" in deteccion:
                    minutos = int(deteccion["segundo"] // 60)
                    segundos = int(deteccion["segundo"] % 60)
                    deteccion["tiempo_formato"] = f"{minutos}:{segundos:02d}"
                

                if "captura" in deteccion and deteccion["captura"]:
                    deteccion["ruta_imagen"] = f"{deteccion['captura']}"
                
                if "latitud" in deteccion and "longitud" in deteccion:
                    deteccion["google_maps"] = f"https://www.google.com/maps?q={deteccion['latitud']},{deteccion['longitud']}"
        
        return data
    
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Error al leer el archivo JSON")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/baches/subir")
async def subir_archivos(folder_name: str = None, files: List[UploadFile] = File(...)):

    if not folder_name:
        folder_name = f"resultados_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    folder_path = RESULTADOS_DIR / folder_name
    folder_path.mkdir(exist_ok=True)
    
    resultados = []
    
    for file in files:
        file_path = folder_path / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        resultados.append(file.filename)
    
    return {
        "message": "Archivos subidos exitosamente",
        "folder": folder_name,
        "files": resultados
    }

@router.delete("/api/baches/carpeta/{folder_name}")
async def eliminar_carpeta(folder_name: str):

    folder_path = RESULTADOS_DIR / folder_name
    
    if not folder_path.exists():
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")
    
    shutil.rmtree(folder_path)
    return {"message": f"Carpeta {folder_name} eliminada exitosamente"}