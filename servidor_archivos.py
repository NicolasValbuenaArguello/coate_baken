import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Servidor Archivos")

# carpeta donde está este archivo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# carpeta uploads del proyecto
UPLOADS = os.path.join(BASE_DIR, "uploads")

print("CARPETA SERVIDA:", UPLOADS)

# crear carpeta si no existe
os.makedirs(UPLOADS, exist_ok=True)

# servir archivos
app.mount(
    "/files",
    StaticFiles(directory=UPLOADS),
    name="files"
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