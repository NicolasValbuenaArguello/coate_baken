import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Servidor Archivos")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# carpeta donde está este archivo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# carpetas base del proyecto
UPLOADS = os.getenv("UPLOADS_DIR", os.path.join(BASE_DIR, "uploads"))
MATRIZ = os.getenv("MATRIZ_DIR", os.path.join(BASE_DIR, "carpeta_matriz_documentos"))

print("CARPETA SERVIDA:", UPLOADS)
print("CARPETA MATRIZ SERVIDA:", MATRIZ)

# crear carpeta si no existe
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(MATRIZ, exist_ok=True)


def construir_url_archivo(base_url: str, ruta_relativa: str) -> str:
    ruta_normalizada = ruta_relativa.replace("\\", "/").lstrip("/")
    return f"{base_url}/{ruta_normalizada}"


def resolver_ruta_segura(base_dir: str, ruta_relativa: str = "") -> str:
    ruta_actual = os.path.abspath(os.path.join(base_dir, ruta_relativa))

    if os.path.commonpath([base_dir, ruta_actual]) != base_dir:
        raise HTTPException(status_code=400, detail="Ruta invalida")

    return ruta_actual


def listar_directorio(base_dir: str, base_url: str, ruta_relativa: str = "") -> dict[str, Any]:
    ruta_actual = resolver_ruta_segura(base_dir, ruta_relativa)

    if not os.path.exists(ruta_actual):
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    if not os.path.isdir(ruta_actual):
        raise HTTPException(status_code=400, detail="La ruta indicada no es una carpeta")

    carpetas = []
    archivos = []

    for nombre in sorted(os.listdir(ruta_actual), key=str.lower):
        ruta_hija = os.path.join(ruta_actual, nombre)
        ruta_hija_relativa = os.path.join(ruta_relativa, nombre).replace("\\", "/").strip("/")

        if os.path.isdir(ruta_hija):
            carpetas.append(listar_directorio(base_dir, base_url, ruta_hija_relativa))
            continue

        archivos.append({
            "nombre": nombre,
            "ruta_relativa": ruta_hija_relativa,
            "url": construir_url_archivo(base_url, ruta_hija_relativa),
            "tamano_bytes": os.path.getsize(ruta_hija),
        })

    return {
        "nombre": os.path.basename(ruta_actual) if ruta_relativa else os.path.basename(base_dir),
        "ruta_relativa": ruta_relativa.replace("\\", "/").strip("/"),
        "carpetas": carpetas,
        "archivos": archivos,
    }


def listar_archivos_planos(base_dir: str, base_url: str, ruta_relativa: str = "") -> list[dict[str, Any]]:
    ruta_actual = resolver_ruta_segura(base_dir, ruta_relativa)

    if not os.path.exists(ruta_actual):
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    if not os.path.isdir(ruta_actual):
        raise HTTPException(status_code=400, detail="La ruta indicada no es una carpeta")

    archivos = []

    for ruta_walk, directorios, nombres_archivo in os.walk(ruta_actual):
        directorios.sort(key=str.lower)
        nombres_archivo.sort(key=str.lower)

        for nombre in nombres_archivo:
            ruta_archivo = os.path.join(ruta_walk, nombre)
            ruta_relativa_archivo = os.path.relpath(ruta_archivo, base_dir).replace("\\", "/")

            archivos.append({
                "nombre": nombre,
                "ruta_relativa": ruta_relativa_archivo,
                "url": construir_url_archivo(base_url, ruta_relativa_archivo),
                "tamano_bytes": os.path.getsize(ruta_archivo),
            })

    return archivos


def listar_carpetas_planas(base_dir: str) -> list[dict[str, str]]:
    carpetas = []

    for ruta_actual, directorios, _ in os.walk(base_dir):
        directorios.sort(key=str.lower)
        ruta_relativa = os.path.relpath(ruta_actual, base_dir).replace("\\", "/")

        carpetas.append({
            "nombre": os.path.basename(ruta_actual),
            "ruta_relativa": "" if ruta_relativa == "." else ruta_relativa,
        })

    return carpetas


def describir_base(nombre: str, base_dir: str, base_url: str) -> dict[str, Any]:
    return {
        "base": nombre,
        "ruta_fisica": base_dir,
        "url_base": base_url,
        "arbol": listar_directorio(base_dir, base_url),
        "total_carpetas": len(listar_carpetas_planas(base_dir)),
        "total_archivos": len(listar_archivos_planos(base_dir, base_url)),
    }

# compatibilidad con rutas antiguas que apuntan a /files/carpeta_matriz_documentos/...
app.mount(
    "/files/carpeta_matriz_documentos",
    StaticFiles(directory=MATRIZ),
    name="files-carpeta-matriz-documentos"
)

# servir archivos
app.mount(
    "/files",
    StaticFiles(directory=UPLOADS),
    name="files"
)

# esta ruta sirve TODAS las subcarpetas dentro de carpeta_matriz_documentos
app.mount(
    "/files-matriz",
    StaticFiles(directory=MATRIZ),
    name="files-matriz"
)

# alias para consumo de otros modulos/documentos futuros
app.mount(
    "/files-documentos",
    StaticFiles(directory=MATRIZ),
    name="files-documentos"
)

@app.get("/")
def home():
    return {
        "servidor": "archivos activo",
        "endpoints": {
            "uploads": "/files",
            "matriz": "/files-matriz",
            "documentos": "/files-documentos",
            "listar_matriz": "/api/matriz/contenido",
            "listar_uploads": "/api/uploads/contenido",
            "listar_matriz_archivos": "/api/matriz/archivos",
            "listar_uploads_archivos": "/api/uploads/archivos",
            "listar_todas_las_carpetas": "/api/matriz/carpetas",
            "explorar_todo": "/api/explorador/todo",
            "catalogo_completo": "/api/explorador/catalogo",
        },
    }


@app.get("/api/matriz/contenido")
def obtener_contenido_matriz(ruta: str = Query(default="")):
    return listar_directorio(MATRIZ, "/files-matriz", ruta)


@app.get("/api/uploads/contenido")
def obtener_contenido_uploads(ruta: str = Query(default="")):
    return listar_directorio(UPLOADS, "/files", ruta)


@app.get("/api/matriz/carpetas")
def obtener_todas_las_carpetas_matriz():
    return {
        "base": "carpeta_matriz_documentos",
        "total": len(listar_carpetas_planas(MATRIZ)),
        "carpetas": listar_carpetas_planas(MATRIZ),
    }


@app.get("/api/matriz/archivos")
def obtener_todos_los_archivos_matriz(ruta: str = Query(default="")):
    archivos = listar_archivos_planos(MATRIZ, "/files-matriz", ruta)
    return {
        "base": "carpeta_matriz_documentos",
        "ruta_relativa": ruta.replace("\\", "/").strip("/"),
        "total": len(archivos),
        "archivos": archivos,
    }


@app.get("/api/uploads/archivos")
def obtener_todos_los_archivos_uploads(ruta: str = Query(default="")):
    archivos = listar_archivos_planos(UPLOADS, "/files", ruta)
    return {
        "base": "uploads",
        "ruta_relativa": ruta.replace("\\", "/").strip("/"),
        "total": len(archivos),
        "archivos": archivos,
    }


@app.get("/api/explorador/todo")
def obtener_explorador_completo():
    return {
        "bases": [
            describir_base("uploads", UPLOADS, "/files"),
            describir_base("carpeta_matriz_documentos", MATRIZ, "/files-matriz"),
        ]
    }


@app.get("/api/explorador/catalogo")
def obtener_catalogo_completo():
    carpetas_uploads = listar_carpetas_planas(UPLOADS)
    carpetas_matriz = listar_carpetas_planas(MATRIZ)
    archivos_uploads = listar_archivos_planos(UPLOADS, "/files")
    archivos_matriz = listar_archivos_planos(MATRIZ, "/files-matriz")

    return {
        "total_carpetas": len(carpetas_uploads) + len(carpetas_matriz),
        "total_archivos": len(archivos_uploads) + len(archivos_matriz),
        "bases": {
            "uploads": {
                "total_carpetas": len(carpetas_uploads),
                "total_archivos": len(archivos_uploads),
                "carpetas": carpetas_uploads,
                "archivos": archivos_uploads,
            },
            "carpeta_matriz_documentos": {
                "total_carpetas": len(carpetas_matriz),
                "total_archivos": len(archivos_matriz),
                "carpetas": carpetas_matriz,
                "archivos": archivos_matriz,
            },
        },
    }

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "servidor_archivos:app",
        host="0.0.0.0",
        port=9000,
        reload=True
    )