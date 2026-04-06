# =========================================================
# IMPORTACIONES
# =========================================================

import os
import shutil

from psycopg_pool import ConnectionPool

from fastapi import FastAPI, APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from passlib.context import CryptContext
from dotenv import load_dotenv

from auth.dependencies import verificar_token
import re


# =========================================================
# VARIABLES ENTORNO
# =========================================================

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
FILES_BASE_URL = os.getenv("FILES_BASE_URL", "http://localhost:9000/files").rstrip("/")
CARPETA_MATRIZ_BASE_DIR = os.path.abspath(
    os.getenv(
        "CARPETA_MATRIZ_BASE_DIR",
        r"D:\mando_control_coate\bakeng\carpeta_matriz_documentos"
    )
)


# =========================================================
# CONEXION POSTGRES
# =========================================================

DATABASE_URL = f"""
dbname={DB_NAME}
user={DB_USER}
password={DB_PASSWORD}
host={DB_HOST}
port={DB_PORT}
"""

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=5,
    max_size=20
)


def get_conn():
    return pool.connection()


def limpiar_nombre(nombre: str) -> str:
    nombre_limpio = re.sub(r"[^a-z0-9_-]", "_", nombre.strip().lower())
    nombre_limpio = re.sub(r"_+", "_", nombre_limpio).strip("_")
    return nombre_limpio


def construir_ruta_carpeta(nombre_limpio: str) -> tuple[str, str]:
    ruta_relativa = f"carpeta_matriz_documentos/{nombre_limpio}"
    ruta_fisica = os.path.abspath(os.path.join(CARPETA_MATRIZ_BASE_DIR, nombre_limpio))

    if os.path.commonpath([CARPETA_MATRIZ_BASE_DIR, ruta_fisica]) != CARPETA_MATRIZ_BASE_DIR:
        raise HTTPException(status_code=400, detail="Ruta de carpeta invalida")

    return ruta_relativa, ruta_fisica


def ruta_relativa_a_fisica(ruta_relativa: str) -> str:
    ruta_normalizada = ruta_relativa.replace("\\", "/").strip().lstrip("/")
    prefijo = "carpeta_matriz_documentos/"

    if ruta_normalizada.startswith(prefijo):
        ruta_normalizada = ruta_normalizada[len(prefijo):]

    ruta_fisica = os.path.abspath(os.path.join(CARPETA_MATRIZ_BASE_DIR, ruta_normalizada))

    if os.path.commonpath([CARPETA_MATRIZ_BASE_DIR, ruta_fisica]) != CARPETA_MATRIZ_BASE_DIR:
        raise HTTPException(status_code=400, detail="Ruta de carpeta invalida")

    return ruta_fisica


def tabla_tiene_columna(cur, tabla: str, columna: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (tabla, columna)
    )
    return cur.fetchone() is not None


def obtener_carpeta_matriz_activa(cur):
    tiene_estado = tabla_tiene_columna(cur, "carperta_documentos_matriz", "estado")

    if tiene_estado:
        cur.execute("""
        SELECT id, nombre, ruta
        FROM carperta_documentos_matriz
        WHERE estado = TRUE
        ORDER BY creado_en DESC, id DESC
        LIMIT 1
        """)
    else:
        cur.execute("""
        SELECT id, nombre, ruta
        FROM carperta_documentos_matriz
        ORDER BY creado_en DESC, id DESC
        LIMIT 1
        """)

    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="No existe carpeta matriz activa")

    return row


# =========================================================
# HASH PASSWORD
# =========================================================

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto"
)


# =========================================================
# APP
# =========================================================

app = FastAPI()
router = APIRouter()


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@router.post("/api/carpetas")
async def crear_carpeta(
    nombre: str = Form(...),
    descripcion: str = Form(None),
    estado: bool = Form(True),
    payload: dict = Depends(verificar_token)
):
    nombre_limpio = limpiar_nombre(nombre)
    if not nombre_limpio:
        raise HTTPException(status_code=400, detail="Nombre de carpeta invalido")

    ruta, ruta_fisica = construir_ruta_carpeta(nombre_limpio)
    carpeta_creada_en_disco = False

    os.makedirs(CARPETA_MATRIZ_BASE_DIR, exist_ok=True)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                tiene_estado = tabla_tiene_columna(cur, "carperta_documentos_matriz", "estado")

                cur.execute("""
                SELECT id FROM carperta_documentos_matriz
                WHERE LOWER(nombre)=LOWER(%s)
                   OR LOWER(ruta)=LOWER(%s)
                """, (nombre, ruta))

                if cur.fetchone():
                    raise HTTPException(
                        status_code=400,
                        detail="La carpeta ya existe"
                    )

                if os.path.exists(ruta_fisica):
                    raise HTTPException(
                        status_code=400,
                        detail="La carpeta ya existe en disco"
                    )

                if tiene_estado and estado:
                    cur.execute("""
                    UPDATE carperta_documentos_matriz
                    SET estado = FALSE
                    WHERE estado = TRUE
                    """)

                if tiene_estado:
                    cur.execute("""
                    INSERT INTO carperta_documentos_matriz
                    (nombre, ruta, descripcion, estado)
                    VALUES (%s,%s,%s,%s)
                    RETURNING id
                    """, (nombre, ruta, descripcion, estado))
                else:
                    cur.execute("""
                    INSERT INTO carperta_documentos_matriz
                    (nombre, ruta, descripcion)
                    VALUES (%s,%s,%s)
                    RETURNING id
                    """, (nombre, ruta, descripcion))

                carpeta_id = cur.fetchone()[0]

                os.makedirs(ruta_fisica, exist_ok=False)
                carpeta_creada_en_disco = True

            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        if carpeta_creada_en_disco and os.path.exists(ruta_fisica):
            shutil.rmtree(ruta_fisica, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Error creando carpeta: {str(e)}")

    return {
        "mensaje":"carpeta creada",
        "id": carpeta_id,
        "estado": estado,
        "ruta": ruta,
        "ruta_fisica": ruta_fisica
    }


@router.get("/api/carpetas")
async def listar_carpetas(
    payload: dict = Depends(verificar_token)
):

    with get_conn() as conn:
        with conn.cursor() as cur:
            tiene_estado = tabla_tiene_columna(cur, "carperta_documentos_matriz", "estado")

            if tiene_estado:
                cur.execute("""
                SELECT
                    id,
                    nombre,
                    ruta,
                    descripcion,
                    estado,
                    creado_en
                FROM carperta_documentos_matriz
                WHERE estado = TRUE
                ORDER BY creado_en DESC
                """)
            else:
                cur.execute("""
                SELECT
                    id,
                    nombre,
                    ruta,
                    descripcion,
                    creado_en
                FROM carperta_documentos_matriz
                ORDER BY creado_en DESC
                """)

            rows = cur.fetchall()

    if tiene_estado:
        return [
            {
                "id": r[0],
                "nombre": r[1],
                "ruta": r[2],
                "descripcion": r[3],
                "estado": r[4],
                "creado_en": r[5],
                "subcarpetas": [],
                "documentos": []
            }
            for r in rows
        ]

    return [
        {
            "id": r[0],
            "nombre": r[1],
            "ruta": r[2],
            "descripcion": r[3],
            "estado": True,
            "creado_en": r[4],
            "subcarpetas": [],
            "documentos": []
        }
        for r in rows
    ]

@router.get("/api/carpetas/arbol")
async def arbol_carpetas(
    payload: dict = Depends(verificar_token)
):

    with get_conn() as conn:
        with conn.cursor() as cur:
            tiene_estado = tabla_tiene_columna(cur, "carperta_documentos_matriz", "estado")

            # 🔹 CARPETAS PRINCIPALES
            if tiene_estado:
                cur.execute("""
                SELECT id,nombre,ruta,descripcion,estado
                FROM carperta_documentos_matriz
                WHERE estado = TRUE
                """)
            else:
                cur.execute("""
                SELECT id,nombre,ruta,descripcion
                FROM carperta_documentos_matriz
                """)
            carpetas = cur.fetchall()

            resultado = []

            for c in carpetas:

                carpeta_id = c[0]

                # 🔹 DOCUMENTOS (nivel 1)
                cur.execute("""
                SELECT id,nombre,ruta
                FROM documento_carpeta_proyecto
                WHERE carpeta_id=%s
                """,(carpeta_id,))
                documentos = cur.fetchall()

                documentos_list = []

                for d in documentos:

                    doc_id = d[0]

                    # 🔹 SUBCARPETAS (nivel 2)
                    cur.execute("""
                    SELECT id,nombre,ruta
                    FROM carpeta_documentos_proyecto
                    WHERE carpeta_id=%s
                    """,(doc_id,))
                    subcarpetas = cur.fetchall()

                    documentos_list.append({
                        "id": d[0],
                        "nombre": d[1],
                        "ruta": d[2],
                        "subcarpetas": [
                            {
                                "id": s[0],
                                "nombre": s[1],
                                "ruta": s[2]
                            } for s in subcarpetas
                        ]
                    })

                if tiene_estado:
                    resultado.append({
                        "id": c[0],
                        "nombre": c[1],
                        "ruta": c[2],
                        "descripcion": c[3],
                        "estado": c[4],
                        "documentos": documentos_list
                    })
                else:
                    resultado.append({
                        "id": c[0],
                        "nombre": c[1],
                        "ruta": c[2],
                        "descripcion": c[3],
                        "estado": True,
                        "documentos": documentos_list
                    })

    return resultado


@router.post("/api/carpetas/proyectos")
async def crear_carpeta_proyecto(
    nombre: str = Form(...),
    descripcion: str = Form(None),
    payload: dict = Depends(verificar_token)
):
    nombre_limpio = limpiar_nombre(nombre)
    if not nombre_limpio:
        raise HTTPException(status_code=400, detail="Nombre de carpeta de proyecto invalido")

    carpeta_creada_en_disco = False
    ruta_fisica = None

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                carpeta_activa = obtener_carpeta_matriz_activa(cur)
                carpeta_matriz_id = carpeta_activa[0]
                ruta_base_matriz = carpeta_activa[2].replace("\\", "/").rstrip("/")

                ruta_relativa = f"{ruta_base_matriz}/{nombre_limpio}"
                ruta_fisica = ruta_relativa_a_fisica(ruta_relativa)

                cur.execute("""
                SELECT id
                FROM documento_carpeta_proyecto
                WHERE carpeta_id = %s
                  AND (
                    LOWER(nombre) = LOWER(%s)
                    OR LOWER(ruta) = LOWER(%s)
                  )
                LIMIT 1
                """, (carpeta_matriz_id, nombre, ruta_relativa))

                if cur.fetchone():
                    raise HTTPException(status_code=400, detail="La carpeta del proyecto ya existe")

                if os.path.exists(ruta_fisica):
                    raise HTTPException(status_code=400, detail="La carpeta del proyecto ya existe en disco")

                cur.execute("""
                INSERT INTO documento_carpeta_proyecto
                (carpeta_id, nombre, ruta, descripcion)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """, (carpeta_matriz_id, nombre, ruta_relativa, descripcion))

                carpeta_proyecto_id = cur.fetchone()[0]

                os.makedirs(ruta_fisica, exist_ok=False)
                carpeta_creada_en_disco = True

            conn.commit()

    except HTTPException:
        raise
    except Exception as e:
        if carpeta_creada_en_disco and ruta_fisica and os.path.exists(ruta_fisica):
            shutil.rmtree(ruta_fisica, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Error creando carpeta de proyecto: {str(e)}")

    return {
        "mensaje": "carpeta de proyecto creada",
        "id": carpeta_proyecto_id,
        "carpeta_matriz_id": carpeta_matriz_id,
        "ruta": ruta_relativa,
        "ruta_fisica": ruta_fisica
    }


@router.post("/api/carpetas/proyectos/{proyecto_id}/subcarpetas")
async def crear_subcarpeta_proyecto(
    proyecto_id: int,
    nombre: str = Form(...),
    descripcion: str = Form(None),
    payload: dict = Depends(verificar_token)
):
    nombre_limpio = limpiar_nombre(nombre)
    if not nombre_limpio:
        raise HTTPException(status_code=400, detail="Nombre de subcarpeta invalido")

    carpeta_creada_en_disco = False
    ruta_fisica = None

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                SELECT id, carpeta_id, ruta
                FROM documento_carpeta_proyecto
                WHERE id = %s
                LIMIT 1
                """, (proyecto_id,))

                row_proyecto = cur.fetchone()
                if not row_proyecto:
                    raise HTTPException(status_code=404, detail="Carpeta de proyecto no existe")

                ruta_base_proyecto = row_proyecto[2].replace("\\", "/").rstrip("/")
                ruta_relativa = f"{ruta_base_proyecto}/{nombre_limpio}"
                ruta_fisica = ruta_relativa_a_fisica(ruta_relativa)

                cur.execute("""
                SELECT id
                FROM carpeta_documentos_proyecto
                WHERE carpeta_id = %s
                  AND (
                    LOWER(nombre) = LOWER(%s)
                    OR LOWER(ruta) = LOWER(%s)
                  )
                LIMIT 1
                """, (proyecto_id, nombre, ruta_relativa))

                if cur.fetchone():
                    raise HTTPException(status_code=400, detail="La subcarpeta ya existe")

                if os.path.exists(ruta_fisica):
                    raise HTTPException(status_code=400, detail="La subcarpeta ya existe en disco")

                cur.execute("""
                INSERT INTO carpeta_documentos_proyecto
                (carpeta_id, nombre, ruta, descripcion)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """, (proyecto_id, nombre, ruta_relativa, descripcion))

                subcarpeta_id = cur.fetchone()[0]

                os.makedirs(ruta_fisica, exist_ok=False)
                carpeta_creada_en_disco = True

            conn.commit()

    except HTTPException:
        raise
    except Exception as e:
        if carpeta_creada_en_disco and ruta_fisica and os.path.exists(ruta_fisica):
            shutil.rmtree(ruta_fisica, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Error creando subcarpeta: {str(e)}")

    return {
        "mensaje": "subcarpeta creada",
        "id": subcarpeta_id,
        "proyecto_id": proyecto_id,
        "ruta": ruta_relativa,
        "ruta_fisica": ruta_fisica
    }

# =========================================================
# REGISTRAR ROUTER
# =========================================================

app.include_router(router)


# =========================================================
# CERRAR POOL
# =========================================================

@app.on_event("shutdown")
def shutdown():
    pool.close()
