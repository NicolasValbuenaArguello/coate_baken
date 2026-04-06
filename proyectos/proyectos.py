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
    # Normaliza el nombre para usarlo de forma segura en rutas.
    nombre_limpio = re.sub(r"[^a-z0-9_-]", "_", nombre.strip().lower())
    nombre_limpio = re.sub(r"_+", "_", nombre_limpio).strip("_")
    return nombre_limpio


def construir_ruta_carpeta(nombre_limpio: str) -> tuple[str, str]:
    # Calcula la ruta relativa guardada en BD y la ruta absoluta en disco.
    ruta_relativa = f"carpeta_matriz_documentos/{nombre_limpio}"
    ruta_fisica = os.path.abspath(os.path.join(CARPETA_MATRIZ_BASE_DIR, nombre_limpio))

    # Evita que una ruta manipulada salga del directorio base permitido.
    if os.path.commonpath([CARPETA_MATRIZ_BASE_DIR, ruta_fisica]) != CARPETA_MATRIZ_BASE_DIR:
        raise HTTPException(status_code=400, detail="Ruta de carpeta invalida")

    return ruta_relativa, ruta_fisica


def tabla_tiene_columna(cur, tabla: str, columna: str) -> bool:
    # Permite mantener compatibilidad entre esquemas distintos de BD.
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


def ruta_relativa_a_fisica(ruta_relativa: str) -> str:
    ruta_normalizada = ruta_relativa.replace("\\", "/").strip().lstrip("/")
    prefijo = "carpeta_matriz_documentos/"

    if ruta_normalizada.startswith(prefijo):
        ruta_normalizada = ruta_normalizada[len(prefijo):]

    ruta_fisica = os.path.abspath(os.path.join(CARPETA_MATRIZ_BASE_DIR, ruta_normalizada))

    if os.path.commonpath([CARPETA_MATRIZ_BASE_DIR, ruta_fisica]) != CARPETA_MATRIZ_BASE_DIR:
        raise HTTPException(status_code=400, detail="Ruta de carpeta invalida")

    return ruta_fisica


def obtener_usuario_logueado(payload: dict) -> str:
    usuario = (payload.get("sub") or payload.get("usuario") or "").strip()
    user_id = payload.get("user_id")

    if usuario:
        return usuario

    if user_id is None:
        raise HTTPException(status_code=401, detail="No fue posible identificar el usuario autenticado")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT usuario
                FROM usuarios
                WHERE id = %s
                LIMIT 1
                """,
                (user_id,)
            )
            row = cur.fetchone()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Usuario autenticado no encontrado")

    return row[0]


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


import re
from fastapi import Form, Depends, HTTPException

def limpiar_nombre(nombre: str):
    # Version simplificada usada por el flujo de proyectos.
    nombre = nombre.lower()
    nombre = re.sub(r'[^a-z0-9_]', '_', nombre)
    return nombre


@router.post("/api/proyectos")
async def crear_proyecto(

    payload: dict = Depends(verificar_token),

    unidad: str = Form(...),
    numero_matricula: str = Form(...),
    titulo: str = Form(...),
    titulo_corto: str = Form(...),

    fecha_inicio: str = Form(None),
    objetivo_general: str = Form(None),

    id_area: int = Form(None),
    id_subarea: int = Form(None),

    enfoque_investigativo: str = Form(None),
    responsable_seguimiento: str = Form(None),

    proyeto_matriculado: bool = Form(False),
    proyecto_fase_formulacion: bool = Form(False),
    otras_iniciativas: bool = Form(False),

    trl: int = Form(None),
    tipo_proyecto: str = Form(None),

    resumen: str = Form(None),
    tiempo_ejecucion_meses: int = Form(None),
    presupuesto: float = Form(None),

    identificacion_necesidad: str = Form(None),
    identificacion_usuario_final: str = Form(None),

    otro: str = Form(None),
    unidad_usuario_final: str = Form(None)
 ):

    # Usuario autenticado para traza operativa sin depender de un claim extra.
    usuario_creacion = obtener_usuario_logueado(payload)

    # Nombre base del arbol documental del proyecto.
    nombre_carpeta = limpiar_nombre(titulo_corto or titulo)
    ruta_base = None

    subcarpetas = ["presupuesto_proyecto", "acta_cierre_proyecto", "informe_final_proyecto", "procediemientos_corrspondientes", "manual_ensamblador", "manual_usuario_final", "encuesta_unidad_usuario_final", "capacitacion_usuario_final", "paquete_tecnico_proyecto", "documento_entrega_proyecto", "compromiso_confidencialidad_proyecto", "cesion_derechos_proyecto", "seguimiento_proyecto_mensual", "control_cambios_proyecto", "elaboracion_formato_leciones_aprendidas", "pruebas_entorno_real_trl6", "pruebas_entorno_cercano_real_trl5", "pruebas_entorno_controlado_trl5", "pruebas_laboratorio_componetes_trl4", "pruebas_laboratorio_informe_analisis_trl3", "definicion_tecnica_solucion_trl2", "acta_validacion_proyecto", "acta_inicio_proyecto", "formato_formulacion_proyecto", "actividades_proyecto", "tabla_trl"]



    carpeta_principal_fisica = None

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                tiene_estado = tabla_tiene_columna(cur, "carperta_documentos_matriz", "estado")

                if not tiene_estado:
                    raise HTTPException(
                        status_code=400,
                        detail="Primero se debe crear carpeta matriz activa"
                    )

                cur.execute("""
                SELECT id, nombre, ruta
                FROM carperta_documentos_matriz
                WHERE estado = TRUE
                ORDER BY creado_en DESC, id DESC
                LIMIT 1
                """)

                carpeta_activa = cur.fetchone()
                if not carpeta_activa:
                    raise HTTPException(
                        status_code=400,
                        detail="Primero se debe crear carpeta matriz activa"
                    )

                carpeta_matriz_id = carpeta_activa[0]
                ruta_matriz_activa = carpeta_activa[2].replace("\\", "/").strip().rstrip("/")
                ruta_base = f"{ruta_matriz_activa}/{nombre_carpeta}"
                carpeta_principal_fisica = ruta_relativa_a_fisica(ruta_base)

                if os.path.exists(carpeta_principal_fisica):
                    raise HTTPException(
                        status_code=400,
                        detail="Ya existe la carpeta fisica para este proyecto"
                    )

                # =========================
                # VALIDAR MATRICULA
                # =========================
                # Impide duplicar proyectos por numero de matricula.
                cur.execute("""
                SELECT id FROM proyectos
                WHERE numero_matricula=%s
                """,(numero_matricula,))

                if cur.fetchone():
                    raise HTTPException(
                        status_code=400,
                        detail="Ya existe un proyecto con esa matrícula"
                    )

                cur.execute("""
                SELECT id
                FROM documento_carpeta_proyecto
                WHERE carpeta_id = %s
                  AND (
                    LOWER(nombre) = LOWER(%s)
                    OR LOWER(ruta) = LOWER(%s)
                  )
                LIMIT 1
                """, (carpeta_matriz_id, titulo_corto, ruta_base))

                if cur.fetchone():
                    raise HTTPException(
                        status_code=400,
                        detail="Ya existe la carpeta del proyecto en la carpeta activa"
                    )

                # =========================
                # 📁 CREAR CARPETA DEL PROYECTO EN MATRIZ ACTIVA
                # =========================
                cur.execute("""
                INSERT INTO documento_carpeta_proyecto
                (carpeta_id, nombre, ruta, descripcion)
                VALUES (%s,%s,%s,%s)
                RETURNING id
                """,(
                    carpeta_matriz_id,
                    titulo_corto,
                    ruta_base,
                    f"Carpeta del proyecto {titulo_corto}"
                ))

                carpeta_id = cur.fetchone()[0]

                os.makedirs(carpeta_principal_fisica, exist_ok=False)

                # =========================
                # 📂 CREAR SUBCARPETAS
                # =========================
                # Crea subcarpetas estandar del flujo documental del proyecto.
                for sub in subcarpetas:

                    ruta_sub = f"{ruta_base}/{sub}"
                    ruta_sub_fisica = ruta_relativa_a_fisica(ruta_sub)

                    cur.execute("""
                    INSERT INTO carpeta_documentos_proyecto
                    (carpeta_id,nombre,ruta)
                    VALUES (%s,%s,%s)
                    """,(carpeta_id, sub, ruta_sub))

                    os.makedirs(ruta_sub_fisica, exist_ok=False)

                # =========================
                # 🧾 INSERTAR PROYECTO
                # =========================
                # Inserta el registro principal del proyecto con metadatos operativos.
                cur.execute("""
                INSERT INTO proyectos
                (
                    unidad,
                    numero_matricula,
                    titulo,
                    titulo_corto,
                    investigador_principal,
                    fecha_inicio,
                    objetivo_general,
                    id_area,
                    id_subarea,
                    enfoque_investigativo,
                    responsable_seguimiento,
                    proyeto_matriculado,
                    proyecto_fase_formulacion,
                    otras_iniciativas,
                    trl,
                    tipo_proyecto,
                    resumen,
                    tiempo_ejecucion_meses,
                    presupuesto,
                    identificacion_necesidad,
                    identificacion_usuario_final,
                    otro,
                    usuario_creacion,
                    unidad_usuario_final
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,(
                    unidad,
                    numero_matricula,
                    titulo,
                    titulo_corto,
                    usuario_creacion,  # investigador_principal
                    fecha_inicio,
                    objetivo_general,
                    id_area,
                    id_subarea,
                    enfoque_investigativo,
                    responsable_seguimiento,
                    proyeto_matriculado,
                    proyecto_fase_formulacion,
                    otras_iniciativas,
                    trl,
                    tipo_proyecto,
                    resumen,
                    tiempo_ejecucion_meses,
                    presupuesto,
                    identificacion_necesidad,
                    identificacion_usuario_final,
                    otro,
                    usuario_creacion,  # usuario_creacion
                    unidad_usuario_final
                ))

                proyecto_id = cur.fetchone()[0]

            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        if carpeta_principal_fisica and os.path.exists(carpeta_principal_fisica):
            shutil.rmtree(carpeta_principal_fisica, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Error creando proyecto: {str(e)}")

    return {
        "mensaje": "Proyecto creado correctamente",
        "proyecto_id": proyecto_id,
        "carpeta_matriz_id": carpeta_matriz_id,
        "carpeta_id": carpeta_id,
        "ruta": ruta_base
    }


@router.put("/api/proyectos/{proyecto_id}")
async def actualizar_proyecto(
    proyecto_id: int,
    payload: dict = Depends(verificar_token),
    unidad: str | None = Form(None),
    numero_matricula: str | None = Form(None),
    titulo: str | None = Form(None),
    titulo_corto: str | None = Form(None),
    fecha_inicio: str | None = Form(None),
    objetivo_general: str | None = Form(None),
    id_area: int | None = Form(None),
    id_subarea: int | None = Form(None),
    enfoque_investigativo: str | None = Form(None),
    responsable_seguimiento: str | None = Form(None),
    proyeto_matriculado: bool | None = Form(None),
    proyecto_fase_formulacion: bool | None = Form(None),
    otras_iniciativas: bool | None = Form(None),
    trl: int | None = Form(None),
    tipo_proyecto: str | None = Form(None),
    resumen: str | None = Form(None),
    tiempo_ejecucion_meses: int | None = Form(None),
    presupuesto: float | None = Form(None),
    identificacion_necesidad: str | None = Form(None),
    identificacion_usuario_final: str | None = Form(None),
    otro: str | None = Form(None),
    unidad_usuario_final: str | None = Form(None)
):
    usuario_logueado = obtener_usuario_logueado(payload)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, numero_matricula
                FROM proyectos
                WHERE id = %s
                LIMIT 1
                """,
                (proyecto_id,)
            )
            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Proyecto no existe")

            if numero_matricula is not None:
                cur.execute(
                    """
                    SELECT id
                    FROM proyectos
                    WHERE numero_matricula = %s
                      AND id <> %s
                    LIMIT 1
                    """,
                    (numero_matricula, proyecto_id)
                )

                if cur.fetchone():
                    raise HTTPException(
                        status_code=400,
                        detail="Ya existe un proyecto con esa matrícula"
                    )

            campos = []
            valores = []

            def agregar(nombre_columna, valor):
                if valor is not None:
                    campos.append(f"{nombre_columna}=%s")
                    valores.append(valor)

            agregar("unidad", unidad)
            agregar("numero_matricula", numero_matricula)
            agregar("titulo", titulo)
            agregar("titulo_corto", titulo_corto)
            agregar("fecha_inicio", fecha_inicio)
            agregar("objetivo_general", objetivo_general)
            agregar("id_area", id_area)
            agregar("id_subarea", id_subarea)
            agregar("enfoque_investigativo", enfoque_investigativo)
            agregar("responsable_seguimiento", responsable_seguimiento)
            agregar("proyeto_matriculado", proyeto_matriculado)
            agregar("proyecto_fase_formulacion", proyecto_fase_formulacion)
            agregar("otras_iniciativas", otras_iniciativas)
            agregar("trl", trl)
            agregar("tipo_proyecto", tipo_proyecto)
            agregar("resumen", resumen)
            agregar("tiempo_ejecucion_meses", tiempo_ejecucion_meses)
            agregar("presupuesto", presupuesto)
            agregar("identificacion_necesidad", identificacion_necesidad)
            agregar("identificacion_usuario_final", identificacion_usuario_final)
            agregar("otro", otro)
            agregar("unidad_usuario_final", unidad_usuario_final)

            if not campos:
                raise HTTPException(status_code=400, detail="No se enviaron campos para actualizar")

            # Mantiene trazabilidad del ultimo usuario que edita.
            campos.append("usuario_creacion=%s")
            valores.append(usuario_logueado)

            valores.append(proyecto_id)

            cur.execute(
                f"UPDATE proyectos SET {', '.join(campos)} WHERE id=%s",
                tuple(valores)
            )

        conn.commit()

    return {
        "mensaje": "Proyecto actualizado correctamente",
        "proyecto_id": proyecto_id
    }


@router.get("/api/proyectos/{proyecto_id}")
async def obtener_proyecto(
    proyecto_id: int,
    payload: dict = Depends(verificar_token)
 ):
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Consulta principal del proyecto con nombres de area/subarea.
            cur.execute("""
            SELECT
                p.id,
                p.unidad,
                p.numero_matricula,
                p.titulo,
                p.titulo_corto,
                p.investigador_principal,
                p.fecha_inicio,
                p.objetivo_general,
                p.id_area,
                a.nombre AS area,
                p.id_subarea,
                s.nombre AS subarea,
                p.enfoque_investigativo,
                p.responsable_seguimiento,
                p.proyeto_matriculado,
                p.proyecto_fase_formulacion,
                p.otras_iniciativas,
                p.trl,
                p.tipo_proyecto,
                p.resumen,
                p.tiempo_ejecucion_meses,
                p.presupuesto,
                p.identificacion_necesidad,
                p.identificacion_usuario_final,
                p.otro,
                p.usuario_creacion,
                p.unidad_usuario_final,
                p.creado_en
            FROM proyectos p
            LEFT JOIN areas a ON a.id = p.id_area
            LEFT JOIN subareas s ON s.id = p.id_subarea
            WHERE p.id = %s
            LIMIT 1
            """, (proyecto_id,))

            proyecto_row = cur.fetchone()
            if not proyecto_row:
                raise HTTPException(status_code=404, detail="Proyecto no existe")

            ruta_slug = limpiar_nombre(proyecto_row[4] or proyecto_row[3])
            ruta_base_legacy = f"proyectos/{ruta_slug}"

            cur.execute("""
            SELECT d.id, d.carpeta_id, d.nombre, d.ruta, d.descripcion,
                   c.id, c.nombre, c.ruta, c.descripcion
            FROM documento_carpeta_proyecto d
            JOIN carperta_documentos_matriz c
              ON c.id = d.carpeta_id
            WHERE d.ruta = %s
               OR d.ruta LIKE %s
            ORDER BY d.creado_en DESC, d.id DESC
            LIMIT 1
            """, (ruta_base_legacy, f"%/{ruta_slug}"))

            carpeta_proyecto = cur.fetchone()

            carpetas_proyecto = []
            carpeta_matriz = None
            if carpeta_proyecto:
                carpeta_proyecto_id = carpeta_proyecto[0]
                carpeta_matriz = (
                    carpeta_proyecto[5],
                    carpeta_proyecto[6],
                    carpeta_proyecto[7],
                    carpeta_proyecto[8],
                )

                cur.execute("""
                SELECT id, nombre, ruta, descripcion
                FROM carpeta_documentos_proyecto
                WHERE carpeta_id = %s
                ORDER BY id
                """, (carpeta_proyecto_id,))

                subcarpetas_rows = cur.fetchall()

                carpetas_proyecto.append({
                    "id": carpeta_proyecto[0],
                    "nombre": carpeta_proyecto[2],
                    "ruta": carpeta_proyecto[3],
                    "descripcion": carpeta_proyecto[4],
                    "subcarpetas": [
                        {
                            "id": s[0],
                            "nombre": s[1],
                            "ruta": s[2],
                            "descripcion": s[3]
                        }
                        for s in subcarpetas_rows
                    ]
                })

            return {
                "id": proyecto_row[0],
                "unidad": proyecto_row[1],
                "numero_matricula": proyecto_row[2],
                "titulo": proyecto_row[3],
                "titulo_corto": proyecto_row[4],
                "investigador_principal": proyecto_row[5],
                "fecha_inicio": proyecto_row[6],
                "objetivo_general": proyecto_row[7],
                "id_area": proyecto_row[8],
                "area": proyecto_row[9],
                "id_subarea": proyecto_row[10],
                "subarea": proyecto_row[11],
                "enfoque_investigativo": proyecto_row[12],
                "responsable_seguimiento": proyecto_row[13],
                "proyeto_matriculado": proyecto_row[14],
                "proyecto_fase_formulacion": proyecto_row[15],
                "otras_iniciativas": proyecto_row[16],
                "trl": proyecto_row[17],
                "tipo_proyecto": proyecto_row[18],
                "resumen": proyecto_row[19],
                "tiempo_ejecucion_meses": proyecto_row[20],
                "presupuesto": proyecto_row[21],
                "identificacion_necesidad": proyecto_row[22],
                "identificacion_usuario_final": proyecto_row[23],
                "otro": proyecto_row[24],
                "usuario_creacion": proyecto_row[25],
                "unidad_usuario_final": proyecto_row[26],
                "creado_en": proyecto_row[27],
                "carpeta_matriz": {
                    "id": carpeta_matriz[0],
                    "nombre": carpeta_matriz[1],
                    "ruta": carpeta_matriz[2],
                    "descripcion": carpeta_matriz[3]
                } if carpeta_matriz else None,
                "carpetas_proyecto": carpetas_proyecto
            }


@router.get("/api/proyectos")
async def listar_proyectos(
    numero_matricula: str | None = None,
    titulo: str | None = None,
    id_area: int | None = None,
    id_subarea: int | None = None,
    fecha_inicio_desde: str | None = None,
    fecha_inicio_hasta: str | None = None,
    payload: dict = Depends(verificar_token)
 ):
    where = []
    params = []

    if numero_matricula:
        where.append("p.numero_matricula ILIKE %s")
        params.append(f"%{numero_matricula}%")

    if titulo:
        where.append("(p.titulo ILIKE %s OR p.titulo_corto ILIKE %s)")
        params.extend([f"%{titulo}%", f"%{titulo}%"])

    if id_area is not None:
        where.append("p.id_area = %s")
        params.append(id_area)

    if id_subarea is not None:
        where.append("p.id_subarea = %s")
        params.append(id_subarea)

    if fecha_inicio_desde:
        where.append("p.fecha_inicio >= %s")
        params.append(fecha_inicio_desde)

    if fecha_inicio_hasta:
        where.append("p.fecha_inicio <= %s")
        params.append(fecha_inicio_hasta)

    where_sql = ""
    if where:
        where_sql = "WHERE " + " AND ".join(where)

    query = f"""
    SELECT
        p.id,
        p.unidad,
        p.numero_matricula,
        p.titulo,
        p.titulo_corto,
        p.investigador_principal,
        p.fecha_inicio,
        p.id_area,
        a.nombre AS area,
        p.id_subarea,
        s.nombre AS subarea,
        p.trl,
        p.tipo_proyecto,
        p.presupuesto,
        p.usuario_creacion,
        p.unidad_usuario_final,
        p.creado_en
    FROM proyectos p
    LEFT JOIN areas a ON a.id = p.id_area
    LEFT JOIN subareas s ON s.id = p.id_subarea
    {where_sql}
    ORDER BY p.creado_en DESC, p.id DESC
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

    return [
        {
            "id": r[0],
            "unidad": r[1],
            "numero_matricula": r[2],
            "titulo": r[3],
            "titulo_corto": r[4],
            "investigador_principal": r[5],
            "fecha_inicio": r[6],
            "id_area": r[7],
            "area": r[8],
            "id_subarea": r[9],
            "subarea": r[10],
            "trl": r[11],
            "tipo_proyecto": r[12],
            "presupuesto": r[13],
            "usuario_creacion": r[14],
            "unidad_usuario_final": r[15],
            "creado_en": r[16]
        }
        for r in rows
    ]




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
