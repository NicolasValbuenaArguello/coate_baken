import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Servidor Archivos")

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
    return {"servidor": "archivos activo"}

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "servidor_archivos:app",
        host="0.0.0.0",
        port=9000,
        reload=True
    )