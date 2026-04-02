# ==========================================================
# IMPORTACIONES
# ==========================================================

import os
import psycopg

from psycopg_pool import ConnectionPool

from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from passlib.context import CryptContext
from dotenv import load_dotenv

from auth.jwt_manager import crear_token


# ==========================================================
# HASH PASSWORD
# ==========================================================

pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto"
)


# ==========================================================
# VARIABLES DE ENTORNO
# ==========================================================

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")


# ==========================================================
# CONEXION POSTGRES
# ==========================================================

DATABASE_URL = f"""
dbname={DB_NAME}
user={DB_USER}
password={DB_PASSWORD}
host={DB_HOST}
port={DB_PORT}
"""


# ==========================================================
# POOL DE CONEXIONES
# ==========================================================

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=2,
    max_size=20
)


# ==========================================================
# FASTAPI
# ==========================================================

app = FastAPI()


@app.on_event("shutdown")
def shutdown():
    pool.close()


# ==========================================================
# CORS
# ==========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================================
# LOGIN
# ==========================================================

@app.post("/api/login")
async def login(
    usuario: str = Form(...),
    password: str = Form(...)
):

    try:

        with pool.connection() as conn:

            with conn.cursor() as cur:

                # ==================================================
                # OBTENER USUARIO
                # ==================================================

                cur.execute("""
                    SELECT
                        u.id,
                        u.usuario,
                        u.password_hash,
                        pn.nivel_unidad,
                        pn.unidad_usuario
                    FROM usuarios u
                    LEFT JOIN personal_novedades pn
                    ON pn.id = u.id_personal_novedad
                    WHERE u.usuario = %s
                    AND u.activo = TRUE
                """,(usuario,))

                user = cur.fetchone()

                if not user:
                    raise HTTPException(
                        status_code=401,
                        detail="Usuario no existe"
                    )

                user_id = user[0]
                user_usuario = user[1]
                user_password = user[2]
                user_nivel_unidad = user[3]
                user_unidad_usuario = user[4]


                # ==================================================
                # VALIDAR PASSWORD
                # ==================================================

                if not pwd_context.verify(password, user_password):

                    raise HTTPException(
                        status_code=401,
                        detail="Password incorrecto"
                    )


                # ==================================================
                # OBTENER ROL
                # ==================================================

                cur.execute("""
                    SELECT r.nombre, r.id
                    FROM usuario_rol ur
                    JOIN roles r ON r.id = ur.rol_id
                    WHERE ur.usuario_id = %s
                """,(user_id,))

                rol = cur.fetchone()

                rol_usuario = rol[0] if rol else "USUARIO"
                rol_id = rol[1] if rol else None


                # ==================================================
                # OBTENER PAGINAS (ROL + OVERRIDE USUARIO)
                # ==================================================

                cur.execute("""

                SELECT

                p.ruta,

                CASE
                    WHEN up.tiene_permiso IS NOT NULL
                    THEN up.tiene_permiso
                    ELSE rp.tiene_permiso
                END as permiso,

                CASE
                    WHEN up.puede_ver IS NOT NULL
                    THEN up.puede_ver
                    ELSE rp.puede_ver
                END as ver,

                CASE
                    WHEN up.puede_crear IS NOT NULL
                    THEN up.puede_crear
                    ELSE rp.puede_crear
                END as crear,

                CASE
                    WHEN up.puede_editar IS NOT NULL
                    THEN up.puede_editar
                    ELSE rp.puede_editar
                END as editar,

                CASE
                    WHEN up.puede_eliminar IS NOT NULL
                    THEN up.puede_eliminar
                    ELSE rp.puede_eliminar
                END as eliminar

                FROM paginas p

                LEFT JOIN rol_pagina rp
                ON rp.pagina_id = p.id
                AND rp.rol_id = %s

                LEFT JOIN usuario_pagina up
                ON up.usuario_id = %s
                AND up.pagina_id = p.id

                """,(rol_id,user_id))


                paginas = []

                for row in cur.fetchall():
                    print(row)
                    paginas.append({
                        "ruta": row[0],
                        "permiso": row[1],
                        "ver": row[2],
                        "crear": row[3],
                        "editar": row[4],
                        "eliminar": row[5]
                    })


                # ==================================================
                # CREAR TOKEN
                # ==================================================

                token = crear_token({

                    "sub": user_usuario,
                    "user_id": user_id,
                    "rol": rol_usuario,
                    "nivel_unidad": user_nivel_unidad,
                    "unidad_usuario": user_unidad_usuario

                })


                # ==================================================
                # RESPUESTA
                # ==================================================

                return {

                    "access_token": token,
                    "token_type": "bearer",
                    "usuario": user_usuario,
                    "rol": rol_usuario,
                    "nivel_unidad": user_nivel_unidad,
                    "unidad_usuario": user_unidad_usuario,
                    "paginas": paginas

                }

    except HTTPException:
        raise
    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
