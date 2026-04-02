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
# AREAS Y SUBAREAS
# =========================================================

# =========================================================
# CREAR AREA
# =========================================================
@router.post("/api/areas")
async def crear_area(
    payload: dict = Depends(verificar_token),
    nombre: str = Form(...),
    descripcion: str | None = Form(None)
):

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                INSERT INTO areas (nombre, descripcion)
                VALUES (%s, %s)
                RETURNING id
                """,(nombre, descripcion))

                area_id = cur.fetchone()[0]

            conn.commit()

        return {
            "mensaje": "Área creada",
            "id": area_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# LISTAR AREAS
# =========================================================
@router.get("/api/areas")
async def listar_areas(payload: dict = Depends(verificar_token)):

    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
            SELECT id, nombre, descripcion
            FROM areas
            ORDER BY id DESC
            """)

            rows = cur.fetchall()

    return [{"id": r[0], "nombre": r[1], "descripcion": r[2]} for r in rows]


# =========================================================
# EDITAR AREA
# =========================================================
@router.put("/api/areas/{area_id}")
async def editar_area(
    area_id: int,
    payload: dict = Depends(verificar_token),
    nombre: str = Form(...),
    descripcion: str | None = Form(None)
):

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                UPDATE areas
                SET nombre=%s, descripcion=%s
                WHERE id=%s
                """,(nombre, descripcion, area_id))

            conn.commit()

        return {"mensaje":"Área actualizada"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# ELIMINAR AREA
# =========================================================
@router.delete("/api/areas/{area_id}")
async def eliminar_area(
    area_id: int,
    payload: dict = Depends(verificar_token)
):

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                # eliminar subareas primero
                cur.execute("""
                DELETE FROM subareas
                WHERE area_id=%s
                """,(area_id,))

                # eliminar area
                cur.execute("""
                DELETE FROM areas
                WHERE id=%s
                """,(area_id,))

            conn.commit()

        return {"mensaje":"Área eliminada"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# CREAR SUBAREA
# =========================================================
@router.post("/api/subareas")
async def crear_subarea(
    payload: dict = Depends(verificar_token),
    nombre: str = Form(...),
    descripcion: str | None = Form(None),
    area_id: int = Form(...)
):

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                # validar area
                cur.execute("SELECT id FROM areas WHERE id=%s",(area_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="Área no existe")

                cur.execute("""
                INSERT INTO subareas (nombre, descripcion, area_id)
                VALUES (%s,%s,%s)
                RETURNING id
                """,(nombre, descripcion, area_id))

                sub_id = cur.fetchone()[0]

            conn.commit()

        return {
            "mensaje": "Subárea creada",
            "id": sub_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# LISTAR SUBAREAS (TODAS)
# =========================================================
@router.get("/api/subareas")
async def listar_subareas(payload: dict = Depends(verificar_token)):

    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
            SELECT s.id, s.nombre, s.descripcion, s.area_id, a.nombre
            FROM subareas s
            LEFT JOIN areas a ON a.id = s.area_id
            ORDER BY s.id DESC
            """)

            rows = cur.fetchall()

    return [
        {
            "id": r[0],
            "nombre": r[1],
            "descripcion": r[2],
            "area_id": r[3],
            "area": r[4]
        }
        for r in rows
    ]


# =========================================================
# LISTAR SUBAREAS POR AREA (🔥 IMPORTANTE PARA TU UI)
# =========================================================
@router.get("/api/subareas/{area_id}")
async def subareas_por_area(
    area_id:int,
    payload: dict = Depends(verificar_token)
    ):

    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
            SELECT id, nombre, descripcion
            FROM subareas
            WHERE area_id=%s
            ORDER BY id DESC
            """,(area_id,))

            rows = cur.fetchall()

    return [{"id": r[0], "nombre": r[1], "descripcion": r[2]} for r in rows]


# =========================================================
# EDITAR SUBAREA
# =========================================================
@router.put("/api/subareas/{sub_id}")
async def editar_subarea(
    sub_id:int,
    payload: dict = Depends(verificar_token),
    nombre: str = Form(...),
    descripcion: str | None = Form(None),
    area_id: int = Form(...)
    ):

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                UPDATE subareas
                SET nombre=%s, descripcion=%s, area_id=%s
                WHERE id=%s
                """,(nombre, descripcion, area_id, sub_id))

            conn.commit()

        return {"mensaje":"Subárea actualizada"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# ELIMINAR SUBAREA
# =========================================================
@router.delete("/api/subareas/{sub_id}")
async def eliminar_subarea(
    sub_id:int,
    payload: dict = Depends(verificar_token)
    ):

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                DELETE FROM subareas
                WHERE id=%s
                """,(sub_id,))

            conn.commit()

        return {"mensaje":"Subárea eliminada"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
# UNIDADES (REEMPLAZA AREAS Y SUBAREAS)
# =========================================================

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
