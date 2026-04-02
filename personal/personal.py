# =========================================================
# IMPORTACIONES
# =========================================================

import os
import traceback
from io import BytesIO

import pandas as pd

from psycopg_pool import ConnectionPool

from fastapi import FastAPI, APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv
from auth.dependencies import verificar_token


# =========================================================
# VARIABLES ENTORNO
# =========================================================

load_dotenv()

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "1234")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "test")
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
    min_size=2,
    max_size=10
)

def get_conn():
    return pool.connection()


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
# FUNCIONES SEGURAS
# =========================================================

def safe_int(value):
    try:
        if value is None:
            return None
        if str(value).lower() == "nan":
            return None
        return int(float(value))
    except:
        return None

def safe_float(value):
    try:
        if value is None:
            return None
        if str(value).lower() == "nan":
            return None
        return float(value)
    except:
        return None

def safe_str(value):
    if value is None:
        return None

    val = str(value).strip()

    if val.lower() in ["nan", "none", ""]:
        return None

    return val


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


# =========================================================
# HEALTH
# =========================================================

@router.get("/")
def home():
    return {"status": "ok"}


# =========================================================
# GUARDAR EXCEL
# =========================================================

@router.post("/api/excel/guardar")
async def guardar_excel(
    payload: dict = Depends(verificar_token),
    archivo: UploadFile = File(...)
):

    if not archivo.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Archivo no válido")

    try:
        usuario = payload.get("sub") or payload.get("usuario")
        user_id = payload.get("user_id")

        if not usuario and not user_id:
            raise HTTPException(status_code=401, detail="Token sin usuario válido")

        nivel_unidad = payload.get("nivel_unidad")
        unidad_usuario = payload.get("unidad_usuario")

        if not nivel_unidad or not unidad_usuario:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    if user_id:
                        cur.execute("""
                        SELECT u.usuario, un.nivel, un.sigla
                        FROM usuarios u
                        LEFT JOIN unidades un
                        ON un.id = u.id_unidad
                        WHERE u.id = %s
                        """, (user_id,))
                    else:
                        cur.execute("""
                        SELECT u.usuario, un.nivel, un.sigla
                        FROM usuarios u
                        LEFT JOIN unidades un
                        ON un.id = u.id_unidad
                        WHERE u.usuario = %s
                        """, (usuario,))

                    user_row = cur.fetchone()

            if not user_row:
                raise HTTPException(status_code=404, detail="Usuario no encontrado")

            usuario = user_row[0]
            nivel_unidad = user_row[1]
            unidad_usuario = user_row[2]

        contenido = await archivo.read()

        # 📊 Leer Excel
        df = pd.read_excel(BytesIO(contenido), header=0)

        # 🔥 Convertir NaN → None
        df = df.where(pd.notnull(df), None)

        registros = []

        for _, row in df.iterrows():

            registros.append((
                safe_str(row.iloc[0]),
                safe_str(row.iloc[1]),
                safe_int(row.iloc[2]),

                safe_str(row.iloc[3]),
                safe_str(row.iloc[4]),
                safe_str(row.iloc[5]),
                safe_str(row.iloc[6]),
                safe_int(row.iloc[7]),

                safe_str(row.iloc[8]),

                safe_str(row.iloc[9]),
                safe_str(row.iloc[10]),

                safe_str(row.iloc[11]),
                safe_str(row.iloc[12]),

                safe_str(row.iloc[13]),
                safe_int(row.iloc[14]),
                safe_str(row.iloc[15]),

                safe_str(row.iloc[16]),
                safe_int(row.iloc[17]),
                safe_str(row.iloc[18]),

                None,
                None,

                safe_int(row.iloc[21]),
                safe_str(row.iloc[22]),
                safe_str(row.iloc[23]),

                safe_str(row.iloc[24]),
                safe_str(row.iloc[25]),

                safe_str(row.iloc[26]),

                safe_str(row.iloc[27]),
                safe_float(row.iloc[28]),

                usuario,
                nivel_unidad,
                unidad_usuario
            ))

        with get_conn() as conn:
            with conn.cursor() as cur:

                # 🔥 ELIMINAR SOLO POR USUARIO Y FECHA
                cur.execute("""
                DELETE FROM personal_novedades
                WHERE fecha_creacion = CURRENT_DATE
                AND usuario_ingreso = %s
                """, (usuario,))

                print("🗑 Registros eliminados:", cur.rowcount)

                # 🔥 INSERTAR NUEVOS
                cur.executemany("""
                INSERT INTO personal_novedades (
                    grado,
                    apellidos_nombres,
                    cc,
                    division,
                    brigada,
                    batallon,
                    compania,
                    peloton,
                    relacion_mando,
                    ciclo,
                    actividad,
                    ubicacion,
                    cargo_especialidad,
                    sexo,
                    telefono,
                    rh,
                    contacto_emergencia,
                    telefono_emergencia,
                    parentesco,
                    fecha_inicio_novedad,
                    fecha_termino_novedad,
                    hijos,
                    estado_civil,
                    escolaridad,
                    correo_personal,
                    correo_institucional,
                    cursos_combte,
                    actitud_psicofisica,
                    porcentaje_discapacidad,
                    usuario_ingreso,
                    nivel_unidad,
                    unidad_usuario
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s
                )
                """, registros)

            conn.commit()

        return {
            "mensaje": "Datos insertados correctamente",
            "total": len(registros),
            "usuario": usuario,
            "nivel_unidad": nivel_unidad,
            "unidad_usuario": unidad_usuario
        }

    except Exception as e:
        print(traceback.format_exc())

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.get("/api/personal/cargas")
async def obtener_cargas(payload: dict = Depends(verificar_token)):

    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                        SELECT
                            usuario_ingreso,
                            nivel_unidad,
                            unidad_usuario,
                            fecha_creacion,
                            COUNT(*) as total_registros
                        FROM personal_novedades
                        GROUP BY
                            usuario_ingreso,
                            nivel_unidad,
                            unidad_usuario,
                            fecha_creacion
                        ORDER BY fecha_creacion DESC
                        """)

            rows = cur.fetchall()

    return [
        {
            "usuario_ingreso": r[0],
            "nivel_unidad": r[1],
            "unidad_usuario": r[2],
            "fecha_creacion": str(r[3]),
            "total_registros": r[4]
        }
        for r in rows
    ]


@router.get("/api/personal/carrusel")
async def obtener_carrusel_personal():

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            SELECT
                fp.id,
                fp.ruta_foto,
                fp.fecha_subida,
                pn.id,
                pn.apellidos_nombres,
                pn.cargo_especialidad,
                pn.unidad_usuario
            FROM fotos_personal fp
            JOIN personal_novedades pn
              ON pn.id = fp.id_personal_novedad
            WHERE fp.ruta_foto IS NOT NULL
              AND TRIM(fp.ruta_foto) <> ''
            ORDER BY fp.fecha_subida DESC, fp.id DESC
            LIMIT 20
            """)

            rows = cur.fetchall()

    return [
        {
            "id_foto": r[0],
            "foto": construir_url_archivo(r[1]),
            "foto_path": r[1],
            "fecha_subida": r[2].isoformat() if r[2] else None,
            "id_personal_novedad": r[3],
            "nombre": r[4],
            "cargo_especialidad": r[5],
            "unidad_usuario": r[6]
        }
        for r in rows
    ]


@router.get("/api/personal/estadisticas")
async def matriz_personal(payload: dict = Depends(verificar_token)):

    with get_conn() as conn:
        with conn.cursor() as cur:

            # 🔥 TODOS LOS GRADOS EXISTENTES
            cur.execute("""
            SELECT DISTINCT grado
            FROM personal_novedades
            ORDER BY grado
            """)
            grados = [r[0] for r in cur.fetchall()]

            # =========================================================
            # 🧠 FUNCIÓN PARA ARMAR MATRIZ
            # =========================================================
            def construir_categoria(nombre, campo):

                cur.execute(f"""
                SELECT grado, {campo}, COUNT(*)
                FROM personal_novedades
                GROUP BY grado, {campo}
                """)

                rows = cur.fetchall()

                resultado = {}

                for grado, categoria, total in rows:
                    if categoria is None:
                        continue

                    if categoria not in resultado:
                        resultado[categoria] = {g: 0 for g in grados}

                    resultado[categoria][grado] = total

                # 🔥 convertir a filas tipo tabla
                filas = []
                for cat, valores in resultado.items():
                    fila = {"categoria": f"{nombre} - {cat}"}
                    fila.update(valores)
                    filas.append(fila)

                return filas

            # =========================================================
            # 🔥 ARMAR TODO
            # =========================================================

            data = []

            data += construir_categoria("SEXO", "sexo")
            data += construir_categoria("RELACION", "relacion_mando")
            data += construir_categoria("CICLO", "ciclo")
            data += construir_categoria("ACTIVIDAD", "actividad")
            data += construir_categoria("UBICACION", "ubicacion")
            data += construir_categoria("CARGO", "cargo_especialidad")
            data += construir_categoria("COMPANIA", "compania")
    print("Grados:", grados)   
    print("Data:", data)
    return {
        "grados": grados,
        "data": data
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
