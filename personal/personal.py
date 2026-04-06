# =========================================================
# IMPORTACIONES
# =========================================================

import json
import os
import uuid

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from psycopg_pool import ConnectionPool

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv

from auth.dependencies import verificar_token


# =========================================================
# VARIABLES DE ENTORNO
# =========================================================

load_dotenv()

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "1234")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "test")
FILES_BASE_URL = os.getenv("FILES_BASE_URL", "http://localhost:9000/files").rstrip("/")
FILES_MATRIZ_BASE_URL = os.getenv("FILES_MATRIZ_BASE_URL", "http://localhost:9000/files-matriz").rstrip("/")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATRIZ_DIR = os.path.join(PROJECT_ROOT, "carpeta_matriz_documentos")
UPLOAD_DIR = os.path.join(MATRIZ_DIR, "fotos_personal")

os.makedirs(UPLOAD_DIR, exist_ok=True)


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
# OPCIONES DE FORMULARIO
# =========================================================

RELACION_MANDO_OPCIONES = [
    "TITULAR",
    "AGREGADO",
    "COMISION",
    "VACACIONES",
    "LICENCIA",
    "INCAPACIDAD",
    "OTRO",
]

SEXO_OPCIONES = ["MASCULINO", "FEMENINO", "OTRO"]

RH_OPCIONES = [
    "O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"
]

ESTADO_CIVIL_OPCIONES = [
    "SOLTERO(A)",
    "CASADO(A)",
    "UNION LIBRE",
    "DIVORCIADO(A)",
    "VIUDO(A)",
]

ESCOLARIDAD_OPCIONES = [
    "PRIMARIA",
    "BACHILLERATO",
    "TECNICO",
    "TECNOLOGO",
    "PROFESIONAL",
    "ESPECIALIZACION",
    "MAESTRIA",
    "DOCTORADO",
]

ACTITUD_OPCIONES = [
    "APTO",
    "NO APTO",
    "APTO CON RESTRICCION",
    "EN VALORACION",
]

ESTADISTICAS_CAMPOS = [
    ("SEXO", "sexo"),
    ("RELACION", "relacion_mando"),
    ("CICLO", "ciclo"),
    ("ACTIVIDAD", "actividad"),
    ("UBICACION", "ubicacion"),
    ("CARGO", "cargo_especialidad"),
    ("ESTADO CIVIL", "estado_civil"),
    ("ESCOLARIDAD", "escolaridad"),
    ("ACTITUD", "actitud_psicofisica"),
]


# =========================================================
# UTILIDADES
# =========================================================

def normalize_text(value):
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    return text


def parse_optional_int(value, field_name):
    value = normalize_text(value)

    if value is None:
        return None

    # Permite entradas con separadores comunes: 1.234.567 o 1,234,567
    sanitized = "".join(ch for ch in value if ch.isdigit())
    if sanitized:
        value = sanitized

    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} debe ser numérico") from exc


def parse_optional_decimal(value, field_name):
    value = normalize_text(value)

    if value is None:
        return None

    # Compatibilidad con decimal en formato ES: 12,5
    value = value.replace(",", ".")

    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} debe ser decimal") from exc


def parse_optional_date(value, field_name):
    value = normalize_text(value)

    if value is None:
        return None

    # Compatibilidad con fecha tipo ISO datetime: 2026-04-03T10:20:30Z
    if "T" in value:
        value = value.split("T", 1)[0]

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} debe tener formato YYYY-MM-DD") from exc


def try_parse_optional_int(value):
    try:
        return parse_optional_int(value, "valor")
    except HTTPException:
        return None


def try_parse_optional_date(value):
    try:
        return parse_optional_date(value, "fecha")
    except HTTPException:
        return None


def try_parse_optional_decimal(value):
    try:
        return parse_optional_decimal(value, "decimal")
    except HTTPException:
        return None


def parse_json_list(primary_value, fallback_value, field_name):
    raw_value = normalize_text(primary_value) or normalize_text(fallback_value)

    if raw_value is None:
        return []

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        # Compatibilidad con FormData que envian "1,2,3" en lugar de JSON.
        if "," in raw_value:
            return [item.strip() for item in raw_value.split(",") if item.strip()]

        # Si llega un valor unico, se procesa como lista de un elemento.
        return [raw_value]

    if parsed is None:
        return []

    if not isinstance(parsed, list):
        return [parsed]

    return parsed


def construir_url_archivo(ruta):
    if not ruta:
        return None

    ruta_normalizada = ruta.replace("\\", "/").strip()

    if ruta_normalizada.startswith("http://") or ruta_normalizada.startswith("https://"):
        return ruta_normalizada

    if "/carpeta_matriz_documentos/" in ruta_normalizada:
        ruta_normalizada = ruta_normalizada.split("/carpeta_matriz_documentos/", 1)[1]
        return f"{FILES_MATRIZ_BASE_URL}/{ruta_normalizada.lstrip('/')}"
    if ruta_normalizada.startswith("carpeta_matriz_documentos/"):
        ruta_normalizada = ruta_normalizada[len("carpeta_matriz_documentos/"):]
        return f"{FILES_MATRIZ_BASE_URL}/{ruta_normalizada.lstrip('/')}"

    if "/uploads/" in ruta_normalizada:
        ruta_normalizada = ruta_normalizada.split("/uploads/", 1)[1]
    elif ruta_normalizada.startswith("uploads/"):
        ruta_normalizada = ruta_normalizada[len("uploads/"):]

    return f"{FILES_BASE_URL}/{ruta_normalizada.lstrip('/')}"


def obtener_contexto_usuario(payload):
    usuario = normalize_text(payload.get("sub") or payload.get("usuario"))
    user_id = payload.get("user_id")

    nivel_unidad = normalize_text(payload.get("nivel_unidad"))
    unidad_usuario = normalize_text(payload.get("unidad_usuario"))

    if usuario and nivel_unidad and unidad_usuario:
        return usuario, nivel_unidad, unidad_usuario

    with get_conn() as conn:
        with conn.cursor() as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT u.usuario, pn.nivel_unidad, pn.unidad_usuario
                    FROM usuarios u
                    LEFT JOIN personal_novedades pn
                      ON pn.id = u.id_personal_novedad
                    WHERE u.id = %s
                    """,
                    (user_id,)
                )
            else:
                cur.execute(
                    """
                    SELECT u.usuario, pn.nivel_unidad, pn.unidad_usuario
                    FROM usuarios u
                    LEFT JOIN personal_novedades pn
                      ON pn.id = u.id_personal_novedad
                    WHERE u.usuario = %s
                    """,
                    (usuario,)
                )

            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return row[0], normalize_text(row[1]), normalize_text(row[2])


async def guardar_foto(upload):
    if upload is None:
        return None

    if not normalize_text(upload.filename):
        return None

    if upload.content_type and not upload.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos de imagen")

    extension = os.path.splitext(upload.filename or "")[1].lower()
    nombre_archivo = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex}{extension}"
    ruta_absoluta = os.path.join(UPLOAD_DIR, nombre_archivo)
    ruta_relativa = os.path.join("carpeta_matriz_documentos", "fotos_personal", nombre_archivo).replace("\\", "/")

    contenido = await upload.read()

    if not contenido:
        return None

    with open(ruta_absoluta, "wb") as file_handle:
        file_handle.write(contenido)

    return ruta_relativa


def validar_grado(cur, grado_id):
    if grado_id is None:
        return

    cur.execute("SELECT 1 FROM grados WHERE id = %s", (grado_id,))

    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="El grado seleccionado no existe")


def formatear_fecha(value):
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


# =========================================================
# HEALTH
# =========================================================

@router.get("/")
def home():
    return {"status": "ok"}


# =========================================================
# GRADOS
# =========================================================

@router.get("/api/grados")
async def listar_grados():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nombre, abreviatura, nivel
                FROM grados
                ORDER BY nivel ASC, nombre ASC
                """
            )

            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "nombre": row[1],
            "abreviatura": row[2],
            "nivel": row[3],
        }
        for row in rows
    ]


@router.post("/api/grados")
async def crear_grado(
    payload: dict = Depends(verificar_token),
    nombre: str = Form(...),
    abreviatura: str = Form(None),
    nivel: int = Form(...),
):
    nombre = normalize_text(nombre)

    if nombre is None:
        raise HTTPException(status_code=400, detail="El nombre del grado es obligatorio")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO grados (nombre, abreviatura, nivel)
                VALUES (%s, %s, %s)
                ON CONFLICT (nombre) DO NOTHING
                RETURNING id, nombre, abreviatura, nivel
                """,
                (nombre, normalize_text(abreviatura), nivel),
            )

            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=400, detail="El grado ya existe")

        conn.commit()

    return {
        "mensaje": "Grado creado",
        "grado": {
            "id": row[0],
            "nombre": row[1],
            "abreviatura": row[2],
            "nivel": row[3],
        },
    }


# =========================================================
# UNIDADES
# =========================================================

@router.get("/api/unidades")
async def listar_unidades():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nivel, sigla, nombre
                FROM unidades
                ORDER BY nivel ASC, sigla ASC
                """
            )

            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "nivel": row[1],
            "sigla": row[2],
            "nombre": row[3],
        }
        for row in rows
    ]


# =========================================================
# CURSOS
# =========================================================

@router.get("/api/personal/cursos")
@router.get("/api/cursos-combate")
async def listar_cursos():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nombre, descripcion
                FROM cursos_combate
                ORDER BY nombre ASC
                """
            )

            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "nombre": row[1],
            "descripcion": row[2],
        }
        for row in rows
    ]


@router.post("/api/personal/cursos")
@router.post("/api/cursos-combate")
async def crear_curso_catalogo(
    payload: dict = Depends(verificar_token),
    nombre: str = Form(...),
    descripcion: str = Form(None),
):
    nombre = normalize_text(nombre)

    if nombre is None:
        raise HTTPException(status_code=400, detail="El nombre del curso es obligatorio")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cursos_combate (nombre, descripcion)
                VALUES (%s, %s)
                ON CONFLICT (nombre) DO NOTHING
                RETURNING id, nombre, descripcion
                """,
                (nombre, normalize_text(descripcion)),
            )

            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=400, detail="El curso ya existe")

        conn.commit()

    return {
        "mensaje": "Curso creado",
        "curso": {
            "id": row[0],
            "nombre": row[1],
            "descripcion": row[2],
        },
    }


# =========================================================
# CATALOGOS DEL FORMULARIO
# =========================================================

@router.get("/api/personal/catalogos")
async def obtener_catalogos_personal():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nombre, abreviatura, nivel
                FROM grados
                ORDER BY nivel ASC, nombre ASC
                """
            )
            grados = cur.fetchall()

            cur.execute(
                """
                SELECT id, nombre, descripcion
                FROM cursos_combate
                ORDER BY nombre ASC
                """
            )
            cursos = cur.fetchall()

    return {
        "grados": [
            {
                "id": row[0],
                "nombre": row[1],
                "abreviatura": row[2],
                "nivel": row[3],
            }
            for row in grados
        ],
        "cursos": [
            {
                "id": row[0],
                "nombre": row[1],
                "descripcion": row[2],
            }
            for row in cursos
        ],
        "opciones": {
            "relacion_mando": RELACION_MANDO_OPCIONES,
            "sexo": SEXO_OPCIONES,
            "rh": RH_OPCIONES,
            "estado_civil": ESTADO_CIVIL_OPCIONES,
            "escolaridad": ESCOLARIDAD_OPCIONES,
            "actitud_psicofisica": ACTITUD_OPCIONES,
        },
    }


# =========================================================
# GUARDAR PERSONAL DESDE FORMULARIO
# =========================================================

@router.post("/api/personal")
@router.post("/api/personal/guardar")
@router.post("/api/excel/guardar")
async def guardar_personal(
    payload: dict = Depends(verificar_token),
    id_grado: str = Form(None),
    apellidos_nombres: str = Form(...),
    cc: str = Form(None),
    relacion_mando: str = Form(None),
    ciclo: str = Form(None),
    actividad: str = Form(None),
    ubicacion: str = Form(None),
    cargo_especialidad: str = Form(None),
    sexo: str = Form(None),
    telefono: str = Form(None),
    rh: str = Form(None),
    contacto_emergencia: str = Form(None),
    telefono_emergencia: str = Form(None),
    parentesco: str = Form(None),
    fecha_inicio_novedad: str = Form(None),
    fecha_termino_novedad: str = Form(None),
    estado_civil: str = Form(None),
    escolaridad: str = Form(None),
    correo_personal: str = Form(None),
    correo_institucional: str = Form(None),
    actitud_psicofisica: str = Form(None),
    porcentaje_discapacidad: str = Form(None),
    hijos: str = Form(None),
    hijos_json: str = Form(None),
    cursos: str = Form(None),
    cursos_json: str = Form(None),
    fotos: list[UploadFile] = File(None),
):
    nombre = normalize_text(apellidos_nombres)

    if nombre is None:
        raise HTTPException(status_code=400, detail="Apellidos y nombres es obligatorio")

    usuario, nivel_unidad, unidad_usuario = obtener_contexto_usuario(payload)
    grado_id = try_parse_optional_int(id_grado)
    hijos_items = parse_json_list(hijos, hijos_json, "hijos")
    cursos_items = parse_json_list(cursos, cursos_json, "cursos")
    saved_files = []

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                validar_grado(cur, grado_id)

                cur.execute(
                    """
                    INSERT INTO personal_novedades (
                        id_grado,
                        apellidos_nombres,
                        cc,
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
                        estado_civil,
                        escolaridad,
                        correo_personal,
                        correo_institucional,
                        actitud_psicofisica,
                        porcentaje_discapacidad,
                        usuario_ingreso,
                        nivel_unidad,
                        unidad_usuario
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    RETURNING id, fecha_creacion
                    """,
                    (
                        grado_id,
                        nombre,
                        try_parse_optional_int(cc),
                        normalize_text(relacion_mando),
                        normalize_text(ciclo),
                        normalize_text(actividad),
                        normalize_text(ubicacion),
                        normalize_text(cargo_especialidad),
                        normalize_text(sexo),
                        try_parse_optional_int(telefono),
                        normalize_text(rh),
                        normalize_text(contacto_emergencia),
                        try_parse_optional_int(telefono_emergencia),
                        normalize_text(parentesco),
                        try_parse_optional_date(fecha_inicio_novedad),
                        try_parse_optional_date(fecha_termino_novedad),
                        normalize_text(estado_civil),
                        normalize_text(escolaridad),
                        normalize_text(correo_personal),
                        normalize_text(correo_institucional),
                        normalize_text(actitud_psicofisica),
                        try_parse_optional_decimal(porcentaje_discapacidad),
                        usuario,
                        nivel_unidad,
                        unidad_usuario,
                    ),
                )

                personal_id, fecha_creacion_db = cur.fetchone()

                for hijo in hijos_items:
                    if not isinstance(hijo, dict):
                        continue

                    nombre_hijo = normalize_text(
                        hijo.get("nombre_completo")
                        or hijo.get("nombreCompleto")
                        or hijo.get("nombre")
                    )

                    if nombre_hijo is None:
                        continue

                    fecha_nacimiento_hijo = try_parse_optional_date(
                        hijo.get("fecha_nacimiento")
                        or hijo.get("fechaNacimiento")
                        or hijo.get("fecha")
                    )

                    if fecha_nacimiento_hijo is None:
                        continue

                    cur.execute(
                        """
                        INSERT INTO hijos_personal (
                            id_personal_novedad,
                            nombre_completo,
                            fecha_nacimiento,
                            grado_estudio
                        ) VALUES (%s, %s, %s, %s)
                        """,
                        (
                            personal_id,
                            nombre_hijo,
                            fecha_nacimiento_hijo,
                            normalize_text(hijo.get("grado_estudio")),
                        ),
                    )

                for curso in cursos_items:
                    if isinstance(curso, dict):
                        curso_id = try_parse_optional_int(
                            curso.get("id")
                            or curso.get("curso_id")
                            or curso.get("cursoId")
                        )
                        fecha_inicio_curso = try_parse_optional_date(
                            curso.get("fecha_inicio")
                            or curso.get("fechaInicio")
                        )
                        fecha_fin_curso = try_parse_optional_date(
                            curso.get("fecha_fin")
                            or curso.get("fechaFin")
                        )
                    else:
                        curso_id = try_parse_optional_int(curso)
                        fecha_inicio_curso = None
                        fecha_fin_curso = None

                    if curso_id is None:
                        continue

                    cur.execute(
                        """
                        INSERT INTO personal_curso (
                            id_personal_novedad,
                            curso_id,
                            fecha_inicio,
                            fecha_fin
                        ) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (id_personal_novedad, curso_id)
                        DO UPDATE SET
                            fecha_inicio = EXCLUDED.fecha_inicio,
                            fecha_fin = EXCLUDED.fecha_fin
                        """,
                        (
                            personal_id,
                            curso_id,
                            fecha_inicio_curso,
                            fecha_fin_curso,
                        ),
                    )

                for foto in fotos or []:
                    ruta_foto = await guardar_foto(foto)

                    if not ruta_foto:
                        continue

                    saved_files.append(os.path.join(PROJECT_ROOT, ruta_foto.replace("/", os.sep)))

                    cur.execute(
                        """
                        INSERT INTO fotos_personal (id_personal_novedad, ruta_foto)
                        VALUES (%s, %s)
                        """,
                        (personal_id, ruta_foto),
                    )

            conn.commit()

        except HTTPException:
            conn.rollback()

            for file_path in saved_files:
                if os.path.exists(file_path):
                    os.remove(file_path)

            raise
        except Exception as exc:
            conn.rollback()

            for file_path in saved_files:
                if os.path.exists(file_path):
                    os.remove(file_path)

            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "mensaje": "Registro de personal guardado correctamente",
        "id": personal_id,
        "fecha_creacion": formatear_fecha(fecha_creacion_db),
        "usuario_ingreso": usuario,
        "nivel_unidad": nivel_unidad,
        "unidad_usuario": unidad_usuario,
        "totales": {
            "hijos": len(hijos_items),
            "cursos": len(cursos_items),
            "fotos": len(fotos or []),
        },
    }


# =========================================================
# CONSULTAS DE PERSONAL
# =========================================================

@router.get("/api/personal/registros")
async def obtener_registros_personal(payload: dict = Depends(verificar_token)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pn.id,
                    g.id,
                    g.nombre,
                    g.abreviatura,
                    pn.apellidos_nombres,
                    pn.cc,
                    pn.relacion_mando,
                    pn.ciclo,
                    pn.actividad,
                    pn.ubicacion,
                    pn.cargo_especialidad,
                    pn.nivel_unidad,
                    pn.unidad_usuario,
                    pn.fecha_inicio_novedad,
                    pn.fecha_termino_novedad,
                    pn.fecha_creacion,
                    COALESCE(h.total_hijos, 0) AS total_hijos,
                    COALESCE(c.total_cursos, 0) AS total_cursos,
                    COALESCE(f.total_fotos, 0) AS total_fotos
                FROM personal_novedades pn
                LEFT JOIN grados g
                  ON g.id = pn.id_grado
                LEFT JOIN (
                    SELECT id_personal_novedad, COUNT(*) AS total_hijos
                    FROM hijos_personal
                    GROUP BY id_personal_novedad
                ) h
                  ON h.id_personal_novedad = pn.id
                LEFT JOIN (
                    SELECT id_personal_novedad, COUNT(*) AS total_cursos
                    FROM personal_curso
                    GROUP BY id_personal_novedad
                ) c
                  ON c.id_personal_novedad = pn.id
                LEFT JOIN (
                    SELECT id_personal_novedad, COUNT(*) AS total_fotos
                    FROM fotos_personal
                    GROUP BY id_personal_novedad
                ) f
                  ON f.id_personal_novedad = pn.id
                ORDER BY pn.fecha_creacion DESC, pn.id DESC
                """
            )

            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "id_grado": row[1],
            "grado": row[2],
            "abreviatura_grado": row[3],
            "apellidos_nombres": row[4],
            "cc": row[5],
            "relacion_mando": row[6],
            "ciclo": row[7],
            "actividad": row[8],
            "ubicacion": row[9],
            "cargo_especialidad": row[10],
            "nivel_unidad": row[11],
            "unidad_usuario": row[12],
            "fecha_inicio_novedad": formatear_fecha(row[13]),
            "fecha_termino_novedad": formatear_fecha(row[14]),
            "fecha_creacion": formatear_fecha(row[15]),
            "total_hijos": row[16],
            "total_cursos": row[17],
            "total_fotos": row[18],
        }
        for row in rows
    ]


@router.get("/api/personal/registros/{registro_id}")
async def obtener_registro_personal_detalle(registro_id: int, payload: dict = Depends(verificar_token)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pn.id,
                    pn.id_grado,
                    g.nombre,
                    g.abreviatura,
                    pn.apellidos_nombres,
                    pn.cc,
                    pn.relacion_mando,
                    pn.ciclo,
                    pn.actividad,
                    pn.ubicacion,
                    pn.cargo_especialidad,
                    pn.sexo,
                    pn.telefono,
                    pn.rh,
                    pn.contacto_emergencia,
                    pn.telefono_emergencia,
                    pn.parentesco,
                    pn.fecha_inicio_novedad,
                    pn.fecha_termino_novedad,
                    pn.estado_civil,
                    pn.escolaridad,
                    pn.correo_personal,
                    pn.correo_institucional,
                    pn.actitud_psicofisica,
                    pn.porcentaje_discapacidad,
                    pn.usuario_ingreso,
                    pn.nivel_unidad,
                    pn.unidad_usuario,
                    pn.fecha_creacion
                FROM personal_novedades pn
                LEFT JOIN grados g
                  ON g.id = pn.id_grado
                WHERE pn.id = %s
                """,
                (registro_id,),
            )

            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Registro de personal no encontrado")

            cur.execute(
                """
                SELECT
                    id,
                    nombre_completo,
                    fecha_nacimiento,
                    grado_estudio,
                    edad,
                    creado_en
                FROM hijos_personal
                WHERE id_personal_novedad = %s
                ORDER BY id ASC
                """,
                (registro_id,),
            )
            hijos_rows = cur.fetchall()

            cur.execute(
                """
                SELECT
                    c.id,
                    c.nombre,
                    c.descripcion,
                    pc.fecha_inicio,
                    pc.fecha_fin
                FROM personal_curso pc
                JOIN cursos_combate c
                  ON c.id = pc.curso_id
                WHERE pc.id_personal_novedad = %s
                ORDER BY c.nombre ASC
                """,
                (registro_id,),
            )
            cursos_rows = cur.fetchall()

            cur.execute(
                """
                SELECT
                    id,
                    ruta_foto,
                    fecha_subida
                FROM fotos_personal
                WHERE id_personal_novedad = %s
                ORDER BY fecha_subida DESC, id DESC
                """,
                (registro_id,),
            )
            fotos_rows = cur.fetchall()

    return {
        "id": row[0],
        "id_grado": row[1],
        "grado": row[2],
        "abreviatura_grado": row[3],
        "apellidos_nombres": row[4],
        "cc": row[5],
        "relacion_mando": row[6],
        "ciclo": row[7],
        "actividad": row[8],
        "ubicacion": row[9],
        "cargo_especialidad": row[10],
        "sexo": row[11],
        "telefono": row[12],
        "rh": row[13],
        "contacto_emergencia": row[14],
        "telefono_emergencia": row[15],
        "parentesco": row[16],
        "fecha_inicio_novedad": formatear_fecha(row[17]),
        "fecha_termino_novedad": formatear_fecha(row[18]),
        "estado_civil": row[19],
        "escolaridad": row[20],
        "correo_personal": row[21],
        "correo_institucional": row[22],
        "actitud_psicofisica": row[23],
        "porcentaje_discapacidad": float(row[24]) if row[24] is not None else None,
        "usuario_ingreso": row[25],
        "nivel_unidad": row[26],
        "unidad_usuario": row[27],
        "fecha_creacion": formatear_fecha(row[28]),
        "hijos": [
            {
                "id": hijo[0],
                "nombre_completo": hijo[1],
                "fecha_nacimiento": formatear_fecha(hijo[2]),
                "grado_estudio": hijo[3],
                "edad": hijo[4],
                "creado_en": formatear_fecha(hijo[5]),
            }
            for hijo in hijos_rows
        ],
        "cursos": [
            {
                "id": curso[0],
                "nombre": curso[1],
                "descripcion": curso[2],
                "fecha_inicio": formatear_fecha(curso[3]),
                "fecha_fin": formatear_fecha(curso[4]),
            }
            for curso in cursos_rows
        ],
        "fotos": [
            {
                "id_foto": foto[0],
                "foto_path": foto[1],
                "foto": construir_url_archivo(foto[1]),
                "fecha_subida": formatear_fecha(foto[2]),
            }
            for foto in fotos_rows
        ],
        "totales": {
            "hijos": len(hijos_rows),
            "cursos": len(cursos_rows),
            "fotos": len(fotos_rows),
        },
    }


@router.get("/api/personal/cargas")
async def obtener_cargas(payload: dict = Depends(verificar_token)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    usuario_ingreso,
                    nivel_unidad,
                    unidad_usuario,
                    fecha_creacion,
                    COUNT(*) AS total_registros
                FROM personal_novedades
                GROUP BY usuario_ingreso, nivel_unidad, unidad_usuario, fecha_creacion
                ORDER BY fecha_creacion DESC, usuario_ingreso ASC
                """
            )

            rows = cur.fetchall()

    return [
        {
            "usuario_ingreso": row[0],
            "nivel_unidad": row[1],
            "unidad_usuario": row[2],
            "fecha_creacion": formatear_fecha(row[3]),
            "total_registros": row[4],
        }
        for row in rows
    ]


@router.get("/api/personal/carrusel")
async def obtener_carrusel_personal():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
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
                """
            )

            rows = cur.fetchall()

    return [
        {
            "id_foto": row[0],
            "foto": construir_url_archivo(row[1]),
            "foto_path": row[1],
            "fecha_subida": formatear_fecha(row[2]),
            "id_personal_novedad": row[3],
            "nombre": row[4],
            "cargo_especialidad": row[5],
            "unidad_usuario": row[6],
        }
        for row in rows
    ]


@router.get("/api/personal/estadisticas")
async def matriz_personal(payload: dict = Depends(verificar_token)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT
                    COALESCE(g.nombre, 'Sin grado') AS grado,
                    COALESCE(g.nivel, 999) AS nivel
                FROM personal_novedades pn
                LEFT JOIN grados g
                  ON g.id = pn.id_grado
                ORDER BY nivel ASC, grado ASC
                """
            )
            grados_rows = cur.fetchall()
            grados = [row[0] for row in grados_rows]

            data = []

            for nombre_categoria, campo in ESTADISTICAS_CAMPOS:
                cur.execute(
                    f"""
                    SELECT
                        COALESCE(g.nombre, 'Sin grado') AS grado,
                        {campo} AS categoria,
                        COUNT(*) AS total
                    FROM personal_novedades pn
                    LEFT JOIN grados g
                      ON g.id = pn.id_grado
                    WHERE {campo} IS NOT NULL
                      AND TRIM({campo}) <> ''
                    GROUP BY COALESCE(g.nombre, 'Sin grado'), {campo}
                    ORDER BY categoria ASC
                    """
                )

                resultados = {}

                for grado, categoria, total in cur.fetchall():
                    if categoria not in resultados:
                        resultados[categoria] = {item: 0 for item in grados}

                    resultados[categoria][grado] = total

                for categoria, valores in resultados.items():
                    fila = {"categoria": f"{nombre_categoria} - {categoria}"}
                    fila.update(valores)
                    data.append(fila)

    return {
        "grados": grados,
        "data": data,
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
