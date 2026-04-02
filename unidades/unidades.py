# =========================================================
# IMPORTACIONES
# =========================================================

import os
import json
import shutil

import psycopg
from psycopg_pool import ConnectionPool

from fastapi import FastAPI, APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from passlib.context import CryptContext
from dotenv import load_dotenv

from auth.dependencies import verificar_token


# =========================================================
# VARIABLES ENTORNO
# =========================================================

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")


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


# =========================================================
# CREAR UNIDAD
# =========================================================
@router.post("/api/unidades")
async def crear_unidad(
    payload: dict = Depends(verificar_token),
    sigla: str = Form(...),
    nombre: str = Form(...)
    ):

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                INSERT INTO unidades (sigla, nombre)
                VALUES (%s, %s)
                ON CONFLICT (sigla) DO NOTHING
                RETURNING id
                """, (sigla.upper(), nombre))

                row = cur.fetchone()

                if not row:
                    raise HTTPException(status_code=400, detail="Unidad ya existe")

                unidad_id = row[0]

            conn.commit()

        return {
            "mensaje": "Unidad creada",
            "id": unidad_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# LISTAR UNIDADES
# =========================================================
@router.get("/api/unidades")
async def listar_unidades(payload: dict = Depends(verificar_token)):

    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
            SELECT id, sigla, nombre
            FROM unidades
            ORDER BY id DESC
            """)

            rows = cur.fetchall()

    return [
        {
            "id": r[0],
            "sigla": r[1],
            "nombre": r[2]
        }
        for r in rows
    ]


# =========================================================
# EDITAR UNIDAD
# =========================================================
@router.put("/api/unidades/{unidad_id}")
async def editar_unidad(
    unidad_id: int,
    payload: dict = Depends(verificar_token),
    sigla: str = Form(...),
    nombre: str = Form(...)
    ):

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                UPDATE unidades
                SET sigla=%s, nombre=%s
                WHERE id=%s
                """, (sigla.upper(), nombre, unidad_id))

            conn.commit()

        return {"mensaje": "Unidad actualizada"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# ELIMINAR UNIDAD
# =========================================================
@router.delete("/api/unidades/{unidad_id}")
async def eliminar_unidad(
    unidad_id: int,
    payload: dict = Depends(verificar_token)
    ):

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                DELETE FROM unidades
                WHERE id=%s
                """, (unidad_id,))

            conn.commit()

        return {"mensaje": "Unidad eliminada"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
