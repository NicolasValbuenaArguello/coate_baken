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
FILES_BASE_URL = os.getenv("FILES_BASE_URL", "http://localhost:9000/files").rstrip("/")


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
# CARPETA FOTOS
# =========================================================

UPLOAD_DIR = "uploads/usuarios"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def construir_url_archivo(ruta: str | None):
    if not ruta:
        return None

    ruta_normalizada = ruta.replace("\\", "/").strip()

    if ruta_normalizada.startswith("http://") or ruta_normalizada.startswith("https://"):
        return ruta_normalizada

    if "/uploads/" in ruta_normalizada:
        ruta_normalizada = ruta_normalizada.split("/uploads/", 1)[1]
    elif ruta_normalizada.startswith("uploads/"):
        ruta_normalizada = ruta_normalizada[len("uploads/"):]

    return f"{FILES_BASE_URL}/{ruta_normalizada.lstrip('/')}"


def obtener_grado_id_desde_nombre(cur, grado_nombre: str | None):
    if not grado_nombre:
        return None

    cur.execute("""
    SELECT id
    FROM grados
    WHERE LOWER(nombre) = LOWER(%s)
       OR LOWER(abreviatura) = LOWER(%s)
    LIMIT 1
    """, (grado_nombre, grado_nombre))

    row = cur.fetchone()
    return row[0] if row else None


def obtener_o_crear_unidad(cur, nivel_unidad: str | None, unidad_usuario: str | None):
    if not nivel_unidad or not unidad_usuario:
        return None

    cur.execute("""
    SELECT id
    FROM unidades
    WHERE UPPER(sigla) = UPPER(%s)
    LIMIT 1
    """, (unidad_usuario,))

    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute("""
    INSERT INTO unidades (nivel, sigla, nombre)
    VALUES (%s, %s, %s)
    RETURNING id
    """, (nivel_unidad, unidad_usuario, unidad_usuario))

    return cur.fetchone()[0]


def obtener_datos_personal(cur, cc: int):
    cur.execute("""
    SELECT
        pn.apellidos_nombres,
        COALESCE(pn.correo_institucional, pn.correo_personal) AS correo,
        pn.grado,
        pn.nivel_unidad,
        pn.unidad_usuario
    FROM personal_novedades pn
    WHERE pn.cc = %s
    ORDER BY pn.fecha_creacion DESC, pn.id DESC
    LIMIT 1
    """, (cc,))

    row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="No existe informacion en personal_novedades para la cedula enviada"
        )

    return {
        "nombre_completo": row[0],
        "correo": row[1],
        "grado": row[2],
        "nivel_unidad": row[3],
        "unidad_usuario": row[4]
    }


# =========================================================
# CREAR USUARIO
# =========================================================
@router.post("/api/usuarios")
async def crear_usuario(

    payload: dict = Depends(verificar_token),

    cc: int | None = Form(None),
    nombre_completo: str | None = Form(None),
    correo: str | None = Form(None),
    usuario: str = Form(...),
    password: str = Form(...),

    grado_id: int | None = Form(None),
    nivel_unidad: str | None = Form(None),
    unidad_usuario: str | None = Form(None),
    activo: bool = Form(True),

    rol_id: int = Form(...),
    permisos: str = Form(...),

    foto: UploadFile = File(None)
):

    permisos = json.loads(permisos)
    password_hash = pwd_context.hash(password)

    with get_conn() as conn:

        with conn.cursor() as cur:
            rol_asignado_por_funcion = False

            if cc is not None:
                cur.execute("""
                SELECT crear_usuario_desde_personal(%s, %s, %s, %s, %s)
                """, (
                    cc,
                    usuario,
                    password_hash,
                    rol_id,
                    activo
                ))

                usuario_id = cur.fetchone()[0]
                rol_asignado_por_funcion = True

            else:
                if not nombre_completo:
                    raise HTTPException(status_code=400, detail="nombre_completo es requerido")

                if not correo:
                    raise HTTPException(status_code=400, detail="correo es requerido")

                if grado_id is None:
                    raise HTTPException(
                        status_code=400,
                        detail="grado_id es requerido cuando no se envia cc"
                    )

                unidad_id = obtener_o_crear_unidad(cur, nivel_unidad, unidad_usuario)

                # =========================
                # CREAR USUARIO
                # =========================

                cur.execute("""
                INSERT INTO usuarios
                (
                    nombre_completo,
                    correo,
                    usuario,
                    password_hash,
                    grado_id,
                    id_unidad,
                    activo
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,(
                    nombre_completo,
                    correo,
                    usuario,
                    password_hash,
                    grado_id,
                    unidad_id,
                    activo
                ))

                usuario_id = cur.fetchone()[0]

            # =========================
            # FOTO
            # =========================

            if foto:

                ext = foto.filename.split(".")[-1]
                ruta = f"{UPLOAD_DIR}/{usuario_id}.{ext}"

                with open(ruta,"wb") as buffer:
                    shutil.copyfileobj(foto.file,buffer)

                cur.execute("""
                UPDATE usuarios
                SET foto=%s
                WHERE id=%s
                """,(ruta,usuario_id))

            # =========================
            # ROL
            # =========================

            if not rol_asignado_por_funcion:
                cur.execute("""
                INSERT INTO usuario_rol(usuario_id,rol_id)
                VALUES (%s,%s)
                """,(usuario_id,rol_id))

            # =========================
            # PERMISOS
            # =========================

            for p in permisos:

                cur.execute("""
                INSERT INTO usuario_pagina
                (
                    usuario_id,
                    pagina_id,
                    tiene_permiso,
                    puede_ver,
                    puede_crear,
                    puede_editar,
                    puede_eliminar
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,(
                    usuario_id,
                    p["id"],
                    p.get("tiene_permiso",False),
                    p.get("ver",False),
                    p.get("crear",False),
                    p.get("editar",False),
                    p.get("eliminar",False)
                ))

        conn.commit()

    return {"mensaje":"usuario creado"}


# =========================================================
# LISTAR USUARIOS
# =========================================================

@router.get("/api/usuarios")
async def usuarios(payload: dict = Depends(verificar_token)):

    with get_conn() as conn:

        with conn.cursor() as cur:

            cur.execute("""
            SELECT
                u.id,
                u.nombre_completo,
                u.usuario,
                u.correo,
                u.foto,
                g.nombre,
                un.nivel,
                un.sigla,
                u.activo
            FROM usuarios u
            LEFT JOIN grados g ON g.id = u.grado_id
            LEFT JOIN unidades un ON un.id = u.id_unidad
            """)

            rows = cur.fetchall()

    return [
        {
            "id":r[0],
            "nombre":r[1],
            "usuario":r[2],
            "correo":r[3],
            "foto":construir_url_archivo(r[4]),
            "foto_path":r[4],
            "grado":r[5],
            "nivel_unidad":r[6],
            "unidad_usuario":r[7],
            "activo":r[8]
        }
        for r in rows
    ]


# =========================================================
# USUARIOS + PERMISOS
# =========================================================
@router.get("/api/usuarios/permisos")
async def usuarios_permisos(payload: dict = Depends(verificar_token)):

    with get_conn() as conn:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    u.id,
                    u.nombre_completo,
                    u.usuario,
                    u.correo,
                    u.foto,

                    u.grado_id,
                    un.nivel,
                    un.sigla,
                    u.activo,

                    g.nombre,

                    r.id,
                    r.nombre,

                    p.nombre,

                    up.tiene_permiso,
                    up.puede_ver,
                    up.puede_crear,
                    up.puede_editar,
                    up.puede_eliminar

                FROM usuarios u

                LEFT JOIN grados g
                ON g.id = u.grado_id

                LEFT JOIN unidades un
                ON un.id = u.id_unidad

                LEFT JOIN usuario_rol ur
                ON ur.usuario_id = u.id

                LEFT JOIN roles r
                ON r.id = ur.rol_id

                LEFT JOIN usuario_pagina up
                ON up.usuario_id = u.id

                LEFT JOIN paginas p
                ON p.id = up.pagina_id

                ORDER BY u.id
            """)

            rows = cur.fetchall()

    usuarios = {}

    for r in rows:

        uid = r[0]

        if uid not in usuarios:

            usuarios[uid] = {

                "id": r[0],
                "nombre": r[1],
                "usuario": r[2],
                "correo": r[3],
                "foto": construir_url_archivo(r[4]),
                "foto_path": r[4],

                "grado_id": r[5],
                "nivel_unidad": r[6],
                "unidad_usuario": r[7],
                "activo": r[8],

                "grado": r[9],

                "rol_id": r[10],
                "rol": r[11],

                "permisos": []
            }

        # PAGINAS / PERMISOS
        if r[12]:

            usuarios[uid]["permisos"].append({

                "pagina": r[12],
                "tiene_permiso": r[13],
                "ver": r[14],
                "crear": r[15],
                "editar": r[16],
                "eliminar": r[17]

            })

    return list(usuarios.values())


# =========================================================
# GRADOS
# =========================================================

@router.get("/api/grados")
async def grados():

    with get_conn() as conn:

        with conn.cursor() as cur:

            cur.execute("SELECT id,nombre FROM grados ORDER BY nivel")

            rows = cur.fetchall()

    return [{"id":r[0],"nombre":r[1]} for r in rows]


# =========================================================
# ROLES
# =========================================================

@router.get("/api/roles")
async def roles():

    with get_conn() as conn:

        with conn.cursor() as cur:

            cur.execute("SELECT id,nombre FROM roles")

            rows = cur.fetchall()

    return [{"id":r[0],"nombre":r[1]} for r in rows]


# =========================================================
# PAGINAS
# =========================================================

@router.get("/api/paginas")
async def paginas():

    with get_conn() as conn:

        with conn.cursor() as cur:

            cur.execute("""
            SELECT id,nombre,ruta
            FROM paginas
            WHERE activa=TRUE
            """)

            rows = cur.fetchall()

    return [{"id":r[0],"nombre":r[1],"ruta":r[2]} for r in rows]


# =========================================================
# DIVISIONES
# =========================================================

@router.get("/api/divisiones")
async def divisiones():

    with get_conn() as conn:

        with conn.cursor() as cur:

            cur.execute("SELECT id,codigo FROM divisiones")

            rows = cur.fetchall()

    return [{"id":r[0],"codigo":r[1]} for r in rows]


# =========================================================
# BRIGADAS
# =========================================================

@router.get("/api/brigadas/{division_id}")
async def brigadas(division_id:int):

    try:

        with get_conn() as conn:

            with conn.cursor() as cur:

                cur.execute("""
                SELECT id,codigo
                FROM brigadas
                WHERE division_id=%s
                """,(division_id,))

                rows = cur.fetchall()

        return [{"id":r[0],"codigo":r[1]} for r in rows]

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Error consultando brigadas: {str(e)}"
        )

# =========================================================
# BATALLONES
# =========================================================

@router.get("/api/batallones/{brigada_id}")
async def batallones(brigada_id:int):

    with get_conn() as conn:

        with conn.cursor() as cur:

            cur.execute("""
            SELECT id,codigo
            FROM batallones
            WHERE brigada_id=%s
            """,(brigada_id,))

            rows = cur.fetchall()

    return [{"id":r[0],"codigo":r[1]} for r in rows]

# =========================================================
# ELIMINAR USUARIO
# =========================================================

@router.delete("/api/usuarios/{usuario_id}")
async def eliminar_usuario(
    usuario_id: int,
    payload: dict = Depends(verificar_token)
):

    if payload["rol"] != "SUPER":
        raise HTTPException(status_code=403, detail="No autorizado")

    with get_conn() as conn:

        with conn.cursor() as cur:

            # obtener foto
            cur.execute("""
            SELECT foto
            FROM usuarios
            WHERE id=%s
            """,(usuario_id,))

            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Usuario no existe")

            foto = row[0]

            # eliminar permisos
            cur.execute("""
            DELETE FROM usuario_pagina
            WHERE usuario_id=%s
            """,(usuario_id,))

            # eliminar roles
            cur.execute("""
            DELETE FROM usuario_rol
            WHERE usuario_id=%s
            """,(usuario_id,))

            # eliminar usuario
            cur.execute("""
            DELETE FROM usuarios
            WHERE id=%s
            """,(usuario_id,))

        conn.commit()

    # eliminar foto del disco
    if foto and os.path.exists(foto):
        os.remove(foto)

    return {"mensaje":"usuario eliminado"}

# =========================================================
# ACTUALIZAR USUARIO
# =========================================================
@router.put("/api/usuarios/{usuario_id}")
async def actualizar_usuario(

    usuario_id:int,
    payload: dict = Depends(verificar_token),

    nombre_completo: str = Form(...),
    correo: str = Form(...),
    usuario: str = Form(...),

    password: str = Form(None),

    grado_id: int = Form(...),
    nivel_unidad: str = Form(...),
    unidad_usuario: str = Form(...),
    activo: bool | None = Form(None),

    rol_id: int = Form(...),
    permisos: str = Form(...),

    foto: UploadFile = File(None)

):

    permisos = json.loads(permisos)

    with get_conn() as conn:

        with conn.cursor() as cur:
            unidad_id = obtener_o_crear_unidad(cur, nivel_unidad, unidad_usuario)

            # =========================
            # ACTUALIZAR USUARIO
            # =========================

            if password:

                password_hash = pwd_context.hash(password)

                cur.execute("""
                UPDATE usuarios
                SET
                    nombre_completo=%s,
                    correo=%s,
                    usuario=%s,
                    password_hash=%s,
                    grado_id=%s,
                    id_unidad=%s,
                    activo=COALESCE(%s,activo)
                WHERE id=%s
                """,(
                    nombre_completo,
                    correo,
                    usuario,
                    password_hash,
                    grado_id,
                    unidad_id,
                    activo,
                    usuario_id
                ))

            else:

                cur.execute("""
                UPDATE usuarios
                SET
                    nombre_completo=%s,
                    correo=%s,
                    usuario=%s,
                    grado_id=%s,
                    id_unidad=%s,
                    activo=COALESCE(%s,activo)
                WHERE id=%s
                """,(
                    nombre_completo,
                    correo,
                    usuario,
                    grado_id,
                    unidad_id,
                    activo,
                    usuario_id
                ))

            # =========================
            # FOTO
            # =========================

            if foto:

                ext = foto.filename.split(".")[-1]
                ruta = f"{UPLOAD_DIR}/{usuario_id}.{ext}"

                with open(ruta,"wb") as buffer:
                    shutil.copyfileobj(foto.file,buffer)

                cur.execute("""
                UPDATE usuarios
                SET foto=%s
                WHERE id=%s
                """,(ruta,usuario_id))

            # =========================
            # ACTUALIZAR ROL
            # =========================

            cur.execute("""
            DELETE FROM usuario_rol
            WHERE usuario_id=%s
            """,(usuario_id,))

            cur.execute("""
            INSERT INTO usuario_rol(usuario_id,rol_id)
            VALUES (%s,%s)
            """,(usuario_id,rol_id))

            # =========================
            # ACTUALIZAR PERMISOS
            # =========================

            cur.execute("""
            DELETE FROM usuario_pagina
            WHERE usuario_id=%s
            """,(usuario_id,))

            for p in permisos:

                cur.execute("""
                INSERT INTO usuario_pagina
                (
                    usuario_id,
                    pagina_id,
                    tiene_permiso,
                    puede_ver,
                    puede_crear,
                    puede_editar,
                    puede_eliminar
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,(
                    usuario_id,
                    p["id"],
                    p.get("tiene_permiso",False),
                    p.get("ver",False),
                    p.get("crear",False),
                    p.get("editar",False),
                    p.get("eliminar",False)
                ))

        conn.commit()

    return {"mensaje":"usuario actualizado"}

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
