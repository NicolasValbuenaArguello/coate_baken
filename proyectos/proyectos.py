"""Modulo de gestion de proyectos y su matriz documental.

Este archivo concentra dos responsabilidades principales:

1. CRUD base de proyectos.
2. CRUD documental asociado a cada proyecto dentro de la carpeta matriz activa.

El diseno actual trabaja con una carpeta matriz marcada como activa en base de
datos. Cada proyecto tiene una carpeta propia dentro de esa matriz y, dentro de
ella, un conjunto fijo de subcarpetas que representan cada tipo de documento.
Las tablas SQL documentales guardan la metadata, mientras que los archivos se
persisten fisicamente dentro del arbol de carpetas.
"""

# =========================================================
# IMPORTACIONES
# =========================================================

import os
import json
import shutil
from datetime import datetime

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

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
FILES_BASE_URL = os.getenv("FILES_BASE_URL", "http://localhost:9000/files").rstrip("/")
FILES_MATRIZ_BASE_URL = os.getenv("FILES_MATRIZ_BASE_URL", "http://localhost:9000/files-matriz").rstrip("/")
CARPETA_MATRIZ_BASE_DIR = os.path.abspath(
    os.getenv(
        "CARPETA_MATRIZ_BASE_DIR",
        os.path.join(PROJECT_ROOT, "carpeta_matriz_documentos")
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
    """Entrega una conexion del pool de PostgreSQL."""
    return pool.connection()


def limpiar_nombre(nombre: str) -> str:
    """Normaliza un nombre para poder usarlo como slug de carpeta."""
    nombre_limpio = re.sub(r"[^a-z0-9_-]", "_", nombre.strip().lower())
    nombre_limpio = re.sub(r"_+", "_", nombre_limpio).strip("_")
    return nombre_limpio


def construir_ruta_carpeta(nombre_limpio: str) -> tuple[str, str]:
    """Construye la ruta relativa y fisica de una carpeta dentro de la matriz."""
    ruta_relativa = f"carpeta_matriz_documentos/{nombre_limpio}"
    ruta_fisica = os.path.abspath(os.path.join(CARPETA_MATRIZ_BASE_DIR, nombre_limpio))

    if os.path.commonpath([CARPETA_MATRIZ_BASE_DIR, ruta_fisica]) != CARPETA_MATRIZ_BASE_DIR:
        raise HTTPException(status_code=400, detail="Ruta de carpeta invalida")

    return ruta_relativa, ruta_fisica


def tabla_tiene_columna(cur, tabla: str, columna: str) -> bool:
    """Valida si una tabla tiene una columna para soportar esquemas variables."""
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
    """Convierte una ruta relativa almacenada en BD en una ruta fisica segura."""
    ruta_normalizada = ruta_relativa.replace("\\", "/").strip().lstrip("/")
    prefijo = "carpeta_matriz_documentos/"

    if ruta_normalizada.startswith(prefijo):
        ruta_normalizada = ruta_normalizada[len(prefijo):]

    ruta_fisica = os.path.abspath(os.path.join(CARPETA_MATRIZ_BASE_DIR, ruta_normalizada))

    if os.path.commonpath([CARPETA_MATRIZ_BASE_DIR, ruta_fisica]) != CARPETA_MATRIZ_BASE_DIR:
        raise HTTPException(status_code=400, detail="Ruta de carpeta invalida")

    return ruta_fisica


def construir_url_archivo(ruta_relativa: str | None) -> str | None:
    """Genera la URL publica de un archivo guardado en uploads o matriz."""
    if not ruta_relativa:
        return None

    ruta_normalizada = ruta_relativa.replace("\\", "/").strip().lstrip("/")

    if "/carpeta_matriz_documentos/" in ruta_normalizada:
        ruta_normalizada = ruta_normalizada.split("/carpeta_matriz_documentos/", 1)[1]
        return f"{FILES_MATRIZ_BASE_URL}/{ruta_normalizada.lstrip('/')}"

    if ruta_normalizada.startswith("carpeta_matriz_documentos/"):
        ruta_normalizada = ruta_normalizada[len("carpeta_matriz_documentos/"):]
        return f"{FILES_MATRIZ_BASE_URL}/{ruta_normalizada.lstrip('/')}"

    return f"{FILES_BASE_URL}/{ruta_normalizada}"


def listar_archivos_directos(ruta_relativa: str) -> list[dict]:
    """Lista solo los archivos directos contenidos en una carpeta relativa."""
    ruta_fisica = ruta_relativa_a_fisica(ruta_relativa)

    if not os.path.isdir(ruta_fisica):
        return []

    archivos = []

    for nombre in sorted(os.listdir(ruta_fisica), key=str.lower):
        ruta_archivo_fisica = os.path.join(ruta_fisica, nombre)

        if not os.path.isfile(ruta_archivo_fisica):
            continue

        ruta_archivo_relativa = f"{ruta_relativa.rstrip('/')}/{nombre}".replace("\\", "/")
        archivos.append({
            "nombre": nombre,
            "ruta": ruta_archivo_relativa,
            "url": construir_url_archivo(ruta_archivo_relativa),
            "tamano_bytes": os.path.getsize(ruta_archivo_fisica),
        })

    return archivos


# Mapa central que traduce cada tabla documental a su subcarpeta y columnas.
DOCUMENTOS_CONFIG = {
    "presupuesto_proyecto": {"subcarpeta": "presupuesto_proyecto", "bool_col": None, "fecha_col": "fecha_presupuesto", "documento_col": "documento_presupuesto", "estado_col": "estado_documento_presupuesto"},
    "acta_cierre_proyecto": {"subcarpeta": "acta_cierre_proyecto", "bool_col": "acta_cierre", "fecha_col": "fecha_cierre", "documento_col": "documento_acta_cierre", "estado_col": "estado_documento_acta_cierre"},
    "informe_final_proyecto": {"subcarpeta": "informe_final_proyecto", "bool_col": "informe_final", "fecha_col": "fecha_informe", "documento_col": "documento_informe", "estado_col": "estado_documento_informe"},
    "procediemientos_corrspondientes": {"subcarpeta": "procediemientos_corrspondientes", "bool_col": "procediemientos_corrspondientes", "fecha_col": "fecha_procedimientos", "documento_col": "documento_procedimientos", "estado_col": "estado_documento_procedimientos"},
    "manual_ensamblador": {"subcarpeta": "manual_ensamblador", "bool_col": "manual_ensamblador", "fecha_col": "fecha_manual", "documento_col": "documento_manual", "estado_col": "estado_documento_manual"},
    "manual_usuario_final": {"subcarpeta": "manual_usuario_final", "bool_col": "manual_usuario_final", "fecha_col": "fecha_manual", "documento_col": "documento_manual", "estado_col": "estado_documento_manual"},
    "encuesta_unidad_usuario_final": {"subcarpeta": "encuesta_unidad_usuario_final", "bool_col": "encuesta_unidad_usuario_final", "fecha_col": "fecha_encuesta", "documento_col": "documento_encuesta", "estado_col": "estado_documento_encuesta"},
    "capacitacion_usuario_final": {"subcarpeta": "capacitacion_usuario_final", "bool_col": "capacitacion_usuario_final", "fecha_col": "fecha_capacitacion", "documento_col": "documento_capacitacion", "estado_col": "estado_documento_capacitacion"},
    "paquete_tecnico_proyecto": {"subcarpeta": "paquete_tecnico_proyecto", "bool_col": "paquete_tecnico", "fecha_col": "fecha_entrega", "documento_col": "documento_paquete_tecnico", "estado_col": "estado_documento_paquete_tecnico"},
    "documento_entrega_proyecto": {"subcarpeta": "documento_entrega_proyecto", "bool_col": None, "fecha_col": "fecha_entrega", "documento_col": "documento_entrega", "estado_col": "estado_documento_entrega"},
    "compromiso_confidencialidad_proyecto": {"subcarpeta": "compromiso_confidencialidad_proyecto", "bool_col": "compromiso_confidencialidad", "fecha_col": "fecha_compromiso", "documento_col": "documento_compromiso", "estado_col": "estado_documento_compromiso"},
    "cesion_derechos_proyecto": {"subcarpeta": "cesion_derechos_proyecto", "bool_col": "cesion_derechos", "fecha_col": "fecha_cesion", "documento_col": "documento_cesion", "estado_col": "estado_documento_cesion"},
    "seguimiento_proyecto_mensual": {"subcarpeta": "seguimiento_proyecto_mensual", "bool_col": "seguimiento", "fecha_col": "fecha_seguimiento", "documento_col": "documento_seguimiento", "estado_col": "estado_documento_seguimiento"},
    "control_cambios_proyecto": {"subcarpeta": "control_cambios_proyecto", "bool_col": "control_cambios", "fecha_col": "fecha_control_cambios", "documento_col": "documento_control_cambios", "estado_col": "estado_documento_control_cambios"},
    "elaboracion_formato_leciones_aprendidas": {"subcarpeta": "elaboracion_formato_leciones_aprendidas", "bool_col": "formato_lecciones_aprendidas", "fecha_col": "fecha_formato_lecciones_aprendidas", "documento_col": "documento_formato_lecciones_aprendidas", "estado_col": "estado_documento_formato_lecciones_aprendidas"},
    "pruebas_entorno_real_trl6": {"subcarpeta": "pruebas_entorno_real_trl6", "bool_col": "pruebas_entorno_real", "fecha_col": "fecha_pruebas_entorno_real", "documento_col": "documento_pruebas_entorno_real", "estado_col": "estado_documento_pruebas_entorno_real"},
    "pruebas_entorno_cercano_real_trl5": {"subcarpeta": "pruebas_entorno_cercano_real_trl5", "bool_col": "pruebas_entorno_cercano_real", "fecha_col": "fecha_pruebas_entorno_cercano_real", "documento_col": "documento_pruebas_entorno_cercano_real", "estado_col": "estado_documento_pruebas_entorno_cercano_real"},
    "pruebas_entorno_controlado_trl5": {"subcarpeta": "pruebas_entorno_controlado_trl5", "bool_col": "pruebas_entorno_controlado", "fecha_col": "fecha_pruebas_entorno_controlado", "documento_col": "documento_pruebas_entorno_controlado", "estado_col": "estado_documento_pruebas_entorno_controlado"},
    "pruebas_laboratorio_componetes_trl4": {"subcarpeta": "pruebas_laboratorio_componetes_trl4", "bool_col": "pruebas_laboratorio", "fecha_col": "fecha_pruebas_laboratorio", "documento_col": "documento_pruebas_laboratorio", "estado_col": "estado_documento_pruebas_laboratorio"},
    "pruebas_laboratorio_informe_analisis_trl3": {"subcarpeta": "pruebas_laboratorio_informe_analisis_trl3", "bool_col": "pruebas_laboratorio", "fecha_col": "fecha_pruebas_laboratorio", "documento_col": "documento_pruebas_laboratorio", "estado_col": "estado_documento_pruebas_laboratorio"},
    "definicion_tecnica_solucion_trl2": {"subcarpeta": "definicion_tecnica_solucion_trl2", "bool_col": "definicion_tecnica", "fecha_col": "fecha_definicion", "documento_col": "documento_definicion", "estado_col": "estado_documento_definicion"},
    "acta_validacion_proyecto": {"subcarpeta": "acta_validacion_proyecto", "bool_col": "acta_validacion", "fecha_col": "fecha_validacion", "documento_col": "documento_acta_validacion", "estado_col": "estado_documento_acta_validacion"},
    "acta_inicio_proyecto": {"subcarpeta": "acta_inicio_proyecto", "bool_col": "acta_inicio", "fecha_col": "fecha_inicio", "documento_col": "documento_acta_inicio", "estado_col": "estado_documento_acta_inicio"},
    "formato_formulacion_proyecto": {"subcarpeta": "formato_formulacion_proyecto", "bool_col": "formato_entregado", "fecha_col": "fecha_entrega", "documento_col": "documento_formato", "estado_col": "estado_documento_formato"},
}


def normalizar_tipo_documento(tipo_documento: str) -> str:
    """Normaliza el identificador del tipo documental recibido por la API."""
    tipo_normalizado = re.sub(r"[^a-z0-9_]+", "_", (tipo_documento or "").strip().lower())
    return re.sub(r"_+", "_", tipo_normalizado).strip("_")


def construir_aliases_documentales() -> dict[str, str]:
    """Construye alias flexibles para aceptar nombres cortos o legacy."""
    alias_map = {}

    for tabla, config in DOCUMENTOS_CONFIG.items():
        candidatos = {tabla, config["subcarpeta"]}

        if config["bool_col"]:
            candidatos.add(config["bool_col"])

        for candidato in list(candidatos):
            if candidato.endswith("_proyecto"):
                candidatos.add(candidato[:-9])

        for candidato in candidatos:
            alias_map[normalizar_tipo_documento(candidato)] = tabla

    return alias_map


DOCUMENTOS_ALIAS = construir_aliases_documentales()


def resolver_tipo_documento(tipo_documento: str) -> str:
    """Resuelve un alias recibido por la API al nombre canonico de la tabla."""
    tipo_normalizado = normalizar_tipo_documento(tipo_documento)
    tipo_resuelto = DOCUMENTOS_ALIAS.get(tipo_normalizado)

    if not tipo_resuelto:
        raise HTTPException(status_code=404, detail="Tipo de documento no soportado")

    return tipo_resuelto


def obtener_carpeta_matriz_activa(cur):
    """Retorna la carpeta matriz marcada como activa en base de datos."""
    tiene_estado = tabla_tiene_columna(cur, "carperta_documentos_matriz", "estado")

    if not tiene_estado:
        raise HTTPException(status_code=400, detail="Primero se debe crear carpeta matriz activa")

    cur.execute(
        """
        SELECT id, nombre, ruta
        FROM carperta_documentos_matriz
        WHERE estado = TRUE
        ORDER BY creado_en DESC, id DESC
        LIMIT 1
        """
    )
    carpeta_activa = cur.fetchone()

    if not carpeta_activa:
        raise HTTPException(status_code=400, detail="Primero se debe crear carpeta matriz activa")

    return carpeta_activa


def obtener_carpetas_matriz_disponibles(cur) -> list[tuple]:
    """Retorna todas las carpetas matriz registradas, priorizando la activa si existe."""
    tiene_estado = tabla_tiene_columna(cur, "carperta_documentos_matriz", "estado")

    if tiene_estado:
        cur.execute(
            """
            SELECT id, nombre, ruta, descripcion, estado
            FROM carperta_documentos_matriz
            ORDER BY estado DESC, creado_en DESC, id DESC
            """
        )
    else:
        cur.execute(
            """
            SELECT id, nombre, ruta, descripcion, TRUE AS estado
            FROM carperta_documentos_matriz
            ORDER BY creado_en DESC, id DESC
            """
        )

    return cur.fetchall()


def obtener_config_documento(tipo_documento: str) -> dict:
    """Recupera la configuracion declarativa de un tipo documental."""
    tipo_documento = resolver_tipo_documento(tipo_documento)
    config = DOCUMENTOS_CONFIG.get(tipo_documento)

    if not config:
        raise HTTPException(status_code=404, detail="Tipo de documento no soportado")

    return config


def obtener_proyecto_base(cur, proyecto_id: int):
    """Obtiene los datos minimos del proyecto requeridos por el flujo documental."""
    cur.execute(
        """
        SELECT id, titulo, titulo_corto, unidad_usuario_final, numero_matricula
        FROM proyectos
        WHERE id = %s
        LIMIT 1
        """,
        (proyecto_id,)
    )
    proyecto = cur.fetchone()

    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no existe")

    return proyecto


def construir_candidatos_nombre_proyecto(proyecto) -> list[str]:
    """Genera nombres candidatos para localizar la carpeta del proyecto."""
    candidatos = []

    for valor in [proyecto[2], proyecto[1], proyecto[4]]:
        texto = str(valor or "").strip()
        if not texto:
            continue

        for candidato in [texto, limpiar_nombre(texto), normalizar_tipo_documento(texto)]:
            if candidato and candidato not in candidatos:
                candidatos.append(candidato)

    return candidatos


def buscar_directorio_por_candidatos(ruta_relativa_padre: str, candidatos: list[str]) -> tuple[str, str] | None:
    """Busca un directorio hijo por nombre exacto o por nombre normalizado."""
    ruta_padre_fisica = ruta_relativa_a_fisica(ruta_relativa_padre)

    if not os.path.isdir(ruta_padre_fisica):
        return None

    directorios = []
    for nombre in os.listdir(ruta_padre_fisica):
        ruta_hija = os.path.join(ruta_padre_fisica, nombre)
        if os.path.isdir(ruta_hija):
            directorios.append(nombre)

    for candidato in candidatos:
        candidato_limpio = str(candidato or "").strip()
        if not candidato_limpio:
            continue

        candidato_normalizado = normalizar_tipo_documento(candidato_limpio)
        candidato_slug = limpiar_nombre(candidato_limpio)

        for nombre_directorio in directorios:
            nombre_normalizado = normalizar_tipo_documento(nombre_directorio)
            nombre_slug = limpiar_nombre(nombre_directorio)

            if (
                nombre_directorio.lower() == candidato_limpio.lower()
                or nombre_normalizado == candidato_normalizado
                or nombre_slug == candidato_slug
            ):
                ruta_relativa = f"{ruta_relativa_padre.rstrip('/')}/{nombre_directorio}".replace("\\", "/")
                return nombre_directorio, ruta_relativa

    return None


def buscar_directorio_en_arbol(candidatos: list[str], subcarpeta_requerida: str | None = None) -> tuple[str, str] | None:
    """Busca un directorio en todo el arbol documental sin depender de registros en BD."""
    for ruta_actual, directorios, _ in os.walk(CARPETA_MATRIZ_BASE_DIR):
        directorios.sort(key=str.lower)

        for nombre_directorio in directorios:
            ruta_directorio = os.path.join(ruta_actual, nombre_directorio)

            if subcarpeta_requerida:
                ruta_subcarpeta = os.path.join(ruta_directorio, subcarpeta_requerida)
                if not os.path.isdir(ruta_subcarpeta):
                    continue

            for candidato in candidatos:
                candidato_limpio = str(candidato or "").strip()
                if not candidato_limpio:
                    continue

                if (
                    nombre_directorio.lower() == candidato_limpio.lower()
                    or normalizar_tipo_documento(nombre_directorio) == normalizar_tipo_documento(candidato_limpio)
                    or limpiar_nombre(nombre_directorio) == limpiar_nombre(candidato_limpio)
                ):
                    ruta_relativa = os.path.relpath(ruta_directorio, CARPETA_MATRIZ_BASE_DIR).replace("\\", "/")
                    return nombre_directorio, f"carpeta_matriz_documentos/{ruta_relativa}"

    return None


def asegurar_directorio_relativo(ruta_relativa: str) -> str:
    """Crea en disco un directorio relativo si no existe y devuelve su ruta."""
    ruta_fisica = ruta_relativa_a_fisica(ruta_relativa)
    os.makedirs(ruta_fisica, exist_ok=True)
    return ruta_relativa


def construir_ruta_proyecto_nueva(proyecto) -> tuple[str, str]:
    """Construye una ruta nueva para un proyecto cuando no existe carpeta previa."""
    nombre_proyecto = (proyecto[2] or proyecto[1] or proyecto[4] or f"proyecto_{proyecto[0]}").strip()
    slug_proyecto = limpiar_nombre(nombre_proyecto) or f"proyecto_{proyecto[0]}"
    ruta_relativa = f"carpeta_matriz_documentos/{slug_proyecto}"
    return slug_proyecto, ruta_relativa


def obtener_carpeta_proyecto_activa(cur, proyecto_id: int):
    """Ubica la carpeta del proyecto sin depender de la carpeta matriz activa."""
    proyecto = obtener_proyecto_base(cur, proyecto_id)
    nombre_proyecto = (proyecto[2] or proyecto[1] or "").strip()
    slug_proyecto = limpiar_nombre(nombre_proyecto)
    candidatos = construir_candidatos_nombre_proyecto(proyecto)
    carpetas_matriz = obtener_carpetas_matriz_disponibles(cur)

    for carpeta_matriz in carpetas_matriz:
        ruta_esperada = f"{carpeta_matriz[2].replace('\\', '/').rstrip('/')}/{slug_proyecto}"

        cur.execute(
            """
            SELECT id, carpeta_id, nombre, ruta, descripcion
            FROM documento_carpeta_proyecto
            WHERE carpeta_id = %s
              AND (
                LOWER(nombre) = LOWER(%s)
                OR LOWER(nombre) = LOWER(%s)
                OR LOWER(ruta) = LOWER(%s)
                OR LOWER(ruta) LIKE LOWER(%s)
              )
            ORDER BY
                CASE
                    WHEN LOWER(ruta) = LOWER(%s) THEN 0
                    WHEN LOWER(nombre) = LOWER(%s) THEN 1
                    WHEN LOWER(nombre) = LOWER(%s) THEN 2
                    ELSE 3
                END,
                id DESC
            LIMIT 1
            """,
            (
                carpeta_matriz[0],
                nombre_proyecto,
                proyecto[1] or nombre_proyecto,
                ruta_esperada,
                f"%/{slug_proyecto}",
                ruta_esperada,
                nombre_proyecto,
                proyecto[1] or nombre_proyecto,
            )
        )
        carpeta_proyecto = cur.fetchone()

        if carpeta_proyecto:
            ruta_proyecto_fisica = ruta_relativa_a_fisica(carpeta_proyecto[3])
            if os.path.isdir(ruta_proyecto_fisica):
                return proyecto, carpeta_matriz, carpeta_proyecto

        coincidencia_directa = buscar_directorio_por_candidatos(carpeta_matriz[2], candidatos)
        if coincidencia_directa:
            carpeta_proyecto = (
                None,
                carpeta_matriz[0],
                coincidencia_directa[0],
                coincidencia_directa[1],
                "Carpeta de proyecto detectada en disco",
            )
            return proyecto, carpeta_matriz, carpeta_proyecto

    coincidencia_global = buscar_directorio_en_arbol(candidatos)
    if not coincidencia_global:
        nombre_proyecto_nuevo, ruta_proyecto_nueva = construir_ruta_proyecto_nueva(proyecto)
        asegurar_directorio_relativo(ruta_proyecto_nueva)
        coincidencia_global = (nombre_proyecto_nuevo, ruta_proyecto_nueva)

    carpeta_matriz = (None, "sin_restriccion_activa", "carpeta_matriz_documentos", "Carpeta matriz detectada por busqueda global", False)
    carpeta_proyecto = (
        None,
        None,
        coincidencia_global[0],
        coincidencia_global[1],
        "Carpeta de proyecto detectada por busqueda global en disco",
    )

    ruta_proyecto_fisica = ruta_relativa_a_fisica(carpeta_proyecto[3])
    if not os.path.isdir(ruta_proyecto_fisica):
        raise HTTPException(status_code=404, detail="La carpeta fisica del proyecto no existe en la matriz documental")

    return proyecto, carpeta_matriz, carpeta_proyecto


def obtener_subcarpeta_documento(cur, proyecto_id: int, tipo_documento: str):
    """Valida y retorna la subcarpeta fisica y logica del tipo documental pedido."""
    config = obtener_config_documento(tipo_documento)
    proyecto, carpeta_matriz, carpeta_proyecto = obtener_carpeta_proyecto_activa(cur, proyecto_id)

    subcarpeta = None
    if carpeta_proyecto[0] is not None:
        cur.execute(
            """
            SELECT id, nombre, ruta, descripcion
            FROM carpeta_documentos_proyecto
            WHERE carpeta_id = %s
              AND LOWER(nombre) = LOWER(%s)
            ORDER BY id DESC
            LIMIT 1
            """,
            (carpeta_proyecto[0], config["subcarpeta"])
        )
        subcarpeta = cur.fetchone()

    if not subcarpeta:
        coincidencia_subcarpeta = buscar_directorio_por_candidatos(carpeta_proyecto[3], [config["subcarpeta"], tipo_documento])

        if not coincidencia_subcarpeta:
            ruta_subcarpeta_nueva = f"{carpeta_proyecto[3].rstrip('/')}/{config['subcarpeta']}".replace("\\", "/")
            asegurar_directorio_relativo(ruta_subcarpeta_nueva)
            coincidencia_subcarpeta = (config["subcarpeta"], ruta_subcarpeta_nueva)

        subcarpeta = (
            None,
            coincidencia_subcarpeta[0],
            coincidencia_subcarpeta[1],
            "Subcarpeta documental detectada en disco",
        )

    ruta_subcarpeta_fisica = ruta_relativa_a_fisica(subcarpeta[2])
    if not os.path.isdir(ruta_subcarpeta_fisica):
        raise HTTPException(status_code=404, detail="La subcarpeta fisica del documento no existe en la matriz documental")

    return proyecto, carpeta_matriz, carpeta_proyecto, subcarpeta


def construir_nombre_carpeta_actividades(proyecto) -> str:
    """Genera el nombre de la carpeta contenedora de actividades del proyecto."""
    base = limpiar_nombre(proyecto[2] or proyecto[1] or proyecto[4] or f"proyecto_{proyecto[0]}")
    return f"actividades_{base or proyecto[0]}"


def construir_nombre_carpeta_actividad(actividad_id: int, actividad: str | None) -> str:
    """Genera el nombre de la subcarpeta de una actividad especifica."""
    slug = limpiar_nombre(actividad or "") or "actividad"
    return f"actividad_{actividad_id}_{slug}"


def obtener_carpeta_actividades_proyecto(cur, proyecto_id: int):
    """Asegura la carpeta raiz de actividades dentro de la carpeta del proyecto."""
    proyecto, carpeta_matriz, carpeta_proyecto = obtener_carpeta_proyecto_activa(cur, proyecto_id)
    nombre_carpeta = construir_nombre_carpeta_actividades(proyecto)
    ruta_carpeta = f"{carpeta_proyecto[3].rstrip('/')}/{nombre_carpeta}".replace("\\", "/")
    ruta_carpeta_fisica = ruta_relativa_a_fisica(ruta_carpeta)
    ruta_legacy = f"{carpeta_proyecto[3].rstrip('/')}/actividades_proyecto".replace("\\", "/")
    ruta_legacy_fisica = ruta_relativa_a_fisica(ruta_legacy)

    if not os.path.isdir(ruta_carpeta_fisica) and os.path.isdir(ruta_legacy_fisica):
        os.rename(ruta_legacy_fisica, ruta_carpeta_fisica)
    else:
        asegurar_directorio_relativo(ruta_carpeta)

    return proyecto, carpeta_matriz, carpeta_proyecto, nombre_carpeta, ruta_carpeta


def obtener_o_crear_carpeta_actividad(cur, proyecto_id: int, actividad_id: int, actividad: str | None):
    """Asegura la subcarpeta fisica de una actividad dentro del proyecto."""
    proyecto, carpeta_matriz, carpeta_proyecto, _, ruta_actividades = obtener_carpeta_actividades_proyecto(cur, proyecto_id)
    prefijo = f"actividad_{actividad_id}_"
    ruta_actividades_fisica = ruta_relativa_a_fisica(ruta_actividades)

    if os.path.isdir(ruta_actividades_fisica):
        for nombre in sorted(os.listdir(ruta_actividades_fisica), key=str.lower):
            ruta_hija = os.path.join(ruta_actividades_fisica, nombre)
            if os.path.isdir(ruta_hija) and nombre.lower().startswith(prefijo.lower()):
                ruta_relativa = f"{ruta_actividades.rstrip('/')}/{nombre}".replace("\\", "/")
                return proyecto, carpeta_matriz, carpeta_proyecto, ruta_actividades, nombre, ruta_relativa

    nombre_carpeta = construir_nombre_carpeta_actividad(actividad_id, actividad)
    ruta_relativa = f"{ruta_actividades.rstrip('/')}/{nombre_carpeta}".replace("\\", "/")
    asegurar_directorio_relativo(ruta_relativa)
    return proyecto, carpeta_matriz, carpeta_proyecto, ruta_actividades, nombre_carpeta, ruta_relativa


def obtener_actividad_proyecto(cur, proyecto_id: int, actividad_id: int):
    """Obtiene una actividad puntual del proyecto."""
    cur.execute(
        """
        SELECT id, proyecto_id, actividad, descripcion, fecha_inicio, fecha_fin,
               estado, documento_entrega, estado_documento_entrega, creado_en,
               usuario_creacion
        FROM actividades_proyecto
        WHERE id = %s
          AND proyecto_id = %s
        LIMIT 1
        """,
        (actividad_id, proyecto_id)
    )
    row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="La actividad no existe para este proyecto")

    return row


def serializar_actividad_proyecto(cur, row):
    """Transforma una actividad del proyecto en respuesta JSON."""
    proyecto_id = row[1]
    actividad_id = row[0]
    _, carpeta_matriz, carpeta_proyecto, ruta_actividades, nombre_carpeta, ruta_actividad = obtener_o_crear_carpeta_actividad(
        cur, proyecto_id, actividad_id, row[2]
    )
    return {
        "id": row[0],
        "proyecto_id": row[1],
        "actividad": row[2],
        "descripcion": row[3],
        "fecha_inicio": row[4],
        "fecha_fin": row[5],
        "estado": row[6],
        "documento_entrega": row[7],
        "url_documento_entrega": construir_url_archivo(row[7]),
        "estado_documento_entrega": row[8],
        "creado_en": row[9],
        "usuario_creacion": row[10],
        "carpeta_matriz": {
            "id": carpeta_matriz[0],
            "nombre": carpeta_matriz[1],
            "ruta": carpeta_matriz[2],
        },
        "carpeta_proyecto": {
            "id": carpeta_proyecto[0],
            "nombre": carpeta_proyecto[2],
            "ruta": carpeta_proyecto[3],
        },
        "carpeta_actividades": {
            "nombre": os.path.basename(ruta_actividades.rstrip('/')),
            "ruta": ruta_actividades,
        },
        "subcarpeta_actividad": {
            "nombre": nombre_carpeta,
            "ruta": ruta_actividad,
        },
        "archivos_subcarpeta": listar_archivos_directos(ruta_actividad),
    }


def normalizar_nombre_archivo(nombre_archivo: str) -> str:
    """Limpia el nombre del archivo recibido para guardarlo de forma segura."""
    nombre_base = os.path.basename((nombre_archivo or "").strip())
    if not nombre_base:
        raise HTTPException(status_code=400, detail="El archivo no tiene nombre valido")

    nombre_sin_extension, extension = os.path.splitext(nombre_base)
    nombre_seguro = re.sub(r"[^a-zA-Z0-9_-]", "_", nombre_sin_extension).strip("_")
    extension_segura = re.sub(r"[^a-zA-Z0-9.]", "", extension.lower())

    if not nombre_seguro:
        nombre_seguro = "documento"

    return f"{nombre_seguro}{extension_segura}"


async def guardar_archivo_documento(upload: UploadFile, ruta_subcarpeta_relativa: str) -> str:
    """Guarda un archivo fisicamente en la subcarpeta documental del proyecto."""
    nombre_archivo = normalizar_nombre_archivo(upload.filename or "")
    marca_tiempo = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    nombre_final = f"{marca_tiempo}_{nombre_archivo}"
    ruta_relativa = f"{ruta_subcarpeta_relativa.rstrip('/')}/{nombre_final}".replace("\\", "/")
    ruta_fisica = ruta_relativa_a_fisica(ruta_relativa)
    contenido = await upload.read()

    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo enviado esta vacio")

    with open(ruta_fisica, "wb") as archivo_salida:
        archivo_salida.write(contenido)

    return ruta_relativa


def resolver_archivo_subido(*archivos: UploadFile | None) -> UploadFile | None:
    """Retorna el primer archivo valido recibido bajo cualquiera de los aliases soportados."""
    for archivo in archivos:
        if archivo is None:
            continue

        if getattr(archivo, "filename", None):
            return archivo

    return None


def eliminar_archivo_documento(ruta_relativa: str | None) -> None:
    """Elimina del disco un archivo documental si existe."""
    if not ruta_relativa:
        return

    ruta_fisica = ruta_relativa_a_fisica(ruta_relativa)
    if os.path.isfile(ruta_fisica):
        os.remove(ruta_fisica)


def resolver_archivos_subidos(*grupos) -> list[UploadFile]:
    """Retorna todos los archivos validos recibidos bajo aliases de formulario."""
    archivos: list[UploadFile] = []

    for grupo in grupos:
        if not grupo:
            continue

        candidatos = grupo if isinstance(grupo, list) else [grupo]
        for archivo in candidatos:
            if archivo is not None and getattr(archivo, "filename", None):
                archivos.append(archivo)

    return archivos


def normalizar_documentos_trl(valor: str | None) -> list[str]:
    """Convierte el valor legacy o JSON de evidencias TRL a una lista de rutas."""
    texto = str(valor or "").strip()
    if not texto:
        return []

    try:
        data = json.loads(texto)
    except Exception:
        return [texto]

    if isinstance(data, list):
        rutas = []
        for item in data:
            if isinstance(item, str) and item.strip():
                rutas.append(item.strip())
            elif isinstance(item, dict):
                ruta = str(item.get("ruta") or item.get("url") or "").strip()
                if ruta:
                    rutas.append(ruta)
        return rutas

    if isinstance(data, dict):
        ruta = str(data.get("ruta") or data.get("url") or "").strip()
        return [ruta] if ruta else []

    return [texto]


def serializar_documentos_trl(rutas: list[str]) -> str | None:
    rutas_limpias = [ruta for ruta in rutas if str(ruta or "").strip()]
    if not rutas_limpias:
        return None

    return json.dumps(rutas_limpias, ensure_ascii=False)


def construir_nombre_carpeta_trl(proyecto) -> str:
    """Genera el nombre de la carpeta contenedora de registros TRL del proyecto."""
    base = limpiar_nombre(proyecto[2] or proyecto[1] or proyecto[4] or f"proyecto_{proyecto[0]}")
    return f"rtl_{base or proyecto[0]}"


def construir_nombre_subcarpeta_trl(trl_id: int, pregunta: str | None) -> str:
    """Genera el nombre de la subcarpeta documental de un registro TRL."""
    slug = limpiar_nombre(pregunta or "") or "registro_trl"
    return f"trl_{trl_id}_{slug}"


def inferir_carpeta_desde_documentos_trl(documentos: list[str]) -> str | None:
    """Recupera la carpeta del registro a partir de sus evidencias existentes."""
    for ruta in documentos:
        ruta_normalizada = str(ruta or "").replace("\\", "/").strip()
        if not ruta_normalizada:
            continue

        carpeta = os.path.dirname(ruta_normalizada).replace("\\", "/").strip()
        if carpeta:
            return carpeta

    return None


def obtener_carpeta_trl_proyecto(cur, proyecto_id: int):
    """Asegura la carpeta raiz de TRL dentro de la carpeta del proyecto."""
    proyecto, carpeta_matriz, carpeta_proyecto = obtener_carpeta_proyecto_activa(cur, proyecto_id)
    nombre_carpeta = construir_nombre_carpeta_trl(proyecto)
    ruta_carpeta = f"{carpeta_proyecto[3].rstrip('/')}/{nombre_carpeta}".replace("\\", "/")
    ruta_carpeta_fisica = ruta_relativa_a_fisica(ruta_carpeta)
    ruta_legacy = f"{carpeta_proyecto[3].rstrip('/')}/tabla_trl".replace("\\", "/")
    ruta_legacy_fisica = ruta_relativa_a_fisica(ruta_legacy)

    if not os.path.isdir(ruta_carpeta_fisica) and os.path.isdir(ruta_legacy_fisica):
        os.rename(ruta_legacy_fisica, ruta_carpeta_fisica)
    else:
        asegurar_directorio_relativo(ruta_carpeta)

    return proyecto, carpeta_matriz, carpeta_proyecto, nombre_carpeta, ruta_carpeta


def obtener_o_crear_carpeta_registro_trl(
    cur,
    proyecto_id: int,
    trl_id: int,
    pregunta: str | None,
    documentos_existentes: list[str] | None = None,
):
    """Asegura la subcarpeta fisica de un registro TRL dentro del proyecto."""
    proyecto, carpeta_matriz, carpeta_proyecto, _, ruta_trl = obtener_carpeta_trl_proyecto(cur, proyecto_id)
    ruta_trl_fisica = ruta_relativa_a_fisica(ruta_trl)

    carpeta_existente = inferir_carpeta_desde_documentos_trl(documentos_existentes or [])
    if carpeta_existente:
        ruta_existente_fisica = ruta_relativa_a_fisica(carpeta_existente)
        if os.path.isdir(ruta_existente_fisica):
            return (
                proyecto,
                carpeta_matriz,
                carpeta_proyecto,
                ruta_trl,
                os.path.basename(carpeta_existente.rstrip('/')),
                carpeta_existente,
            )

    prefijo = f"trl_{trl_id}_"
    if os.path.isdir(ruta_trl_fisica):
        for nombre in sorted(os.listdir(ruta_trl_fisica), key=str.lower):
            ruta_hija = os.path.join(ruta_trl_fisica, nombre)
            if os.path.isdir(ruta_hija) and nombre.lower().startswith(prefijo.lower()):
                ruta_relativa = f"{ruta_trl.rstrip('/')}/{nombre}".replace("\\", "/")
                return proyecto, carpeta_matriz, carpeta_proyecto, ruta_trl, nombre, ruta_relativa

    nombre_carpeta = construir_nombre_subcarpeta_trl(trl_id, pregunta)
    ruta_relativa = f"{ruta_trl.rstrip('/')}/{nombre_carpeta}".replace("\\", "/")
    asegurar_directorio_relativo(ruta_relativa)
    return proyecto, carpeta_matriz, carpeta_proyecto, ruta_trl, nombre_carpeta, ruta_relativa


def obtener_registro_trl(cur, proyecto_id: int, trl_id: int):
    """Obtiene un registro puntual de tabla_trl para un proyecto."""
    cur.execute(
        """
        SELECT id, id_proyecto, trl, numero_orden, pregunta_trl, cumple_trl,
               documento_evidencia, observaciones, estado_docuemento_entrega, creado_en,
               usuario_creacion
        FROM tabla_trl
        WHERE id = %s
          AND id_proyecto = %s
        LIMIT 1
        """,
        (trl_id, proyecto_id)
    )
    row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="El registro TRL no existe para este proyecto")

    return row


def serializar_registro_trl(cur, row) -> dict:
    documentos = normalizar_documentos_trl(row[6])
    _, carpeta_matriz, carpeta_proyecto, ruta_trl, nombre_subcarpeta, ruta_registro = obtener_o_crear_carpeta_registro_trl(
        cur, row[1], row[0], row[4], documentos
    )

    return {
        "id": row[0],
        "id_proyecto": row[1],
        "trl": row[2],
        "numero_orden": row[3],
        "pregunta_trl": row[4],
        "cumple_trl": row[5],
        "documento_evidencia": row[6],
        "documentos_evidencia": [
            {
                "nombre": os.path.basename(ruta.replace("\\", "/").split("?", 1)[0]),
                "ruta": ruta,
                "url": construir_url_archivo(ruta),
            }
            for ruta in documentos
        ],
        "observaciones": row[7],
        "estado_docuemento_entrega": row[8],
        "creado_en": row[9],
        "usuario_creacion": row[10],
        "carpeta_matriz": {
            "id": carpeta_matriz[0],
            "nombre": carpeta_matriz[1],
            "ruta": carpeta_matriz[2],
        },
        "carpeta_proyecto": {
            "id": carpeta_proyecto[0],
            "nombre": carpeta_proyecto[2],
            "ruta": carpeta_proyecto[3],
        },
        "carpeta_trl": {
            "nombre": os.path.basename(ruta_trl.rstrip('/')),
            "ruta": ruta_trl,
        },
        "subcarpeta_trl": {
            "nombre": nombre_subcarpeta,
            "ruta": ruta_registro,
        },
        "archivos_subcarpeta": listar_archivos_directos(ruta_registro),
    }


def columnas_documento(tipo_documento: str) -> list[str]:
    """Construye la lista de columnas relevantes para una tabla documental."""
    tipo_documento = resolver_tipo_documento(tipo_documento)
    config = obtener_config_documento(tipo_documento)
    columnas = ["id", "proyecto_id"]

    if config["bool_col"]:
        columnas.append(config["bool_col"])

    columnas.extend([config["fecha_col"], config["documento_col"], config["estado_col"], "creado_en", "usuario_creacion", "unidad_usuario_final"])
    return columnas


def obtener_registro_documento(cur, tipo_documento: str, proyecto_id: int):
    """Obtiene el ultimo registro documental asociado al proyecto."""
    tipo_documento = resolver_tipo_documento(tipo_documento)
    columnas = columnas_documento(tipo_documento)
    cur.execute(
        f"SELECT {', '.join(columnas)} FROM {tipo_documento} WHERE proyecto_id = %s ORDER BY id DESC LIMIT 1",
        (proyecto_id,)
    )
    return cur.fetchone(), columnas


def insertar_registro_documento(
    cur,
    tipo_documento: str,
    proyecto_id: int,
    proyecto,
    usuario_logueado: str,
    fecha_documento: str | None,
    estado_documento: str | None,
    valor_documento: bool | None,
    unidad_usuario_final: str | None,
    ruta_documento: str | None,
):
    """Inserta un registro documental nuevo para el proyecto."""
    tipo_documento = resolver_tipo_documento(tipo_documento)
    config = obtener_config_documento(tipo_documento)
    columnas = ["proyecto_id", config["fecha_col"], config["documento_col"], config["estado_col"], "usuario_creacion", "unidad_usuario_final"]
    valores = [
        proyecto_id,
        fecha_documento,
        ruta_documento,
        estado_documento or ("CARGADO" if ruta_documento else None),
        usuario_logueado,
        unidad_usuario_final or proyecto[3],
    ]

    if config["bool_col"]:
        columnas.insert(1, config["bool_col"])
        valores.insert(1, valor_documento if valor_documento is not None else bool(ruta_documento))

    placeholders = ", ".join(["%s"] * len(columnas))
    cur.execute(
        f"INSERT INTO {tipo_documento} ({', '.join(columnas)}) VALUES ({placeholders})",
        tuple(valores)
    )


def obtener_registros_documento(cur, tipo_documento: str, proyecto_id: int):
    """Obtiene todos los registros documentales de un tipo para un proyecto."""
    tipo_documento = resolver_tipo_documento(tipo_documento)
    columnas = columnas_documento(tipo_documento)
    cur.execute(
        f"SELECT {', '.join(columnas)} FROM {tipo_documento} WHERE proyecto_id = %s ORDER BY creado_en DESC, id DESC",
        (proyecto_id,)
    )
    return cur.fetchall(), columnas


def serializar_registro_documento(tipo_documento: str, row, ruta_subcarpeta: str, carpeta_matriz=None, carpeta_proyecto=None, subcarpeta=None):
    """Transforma un registro documental y su contexto en una respuesta JSON."""
    tipo_documento = resolver_tipo_documento(tipo_documento)
    config = obtener_config_documento(tipo_documento)
    columnas = columnas_documento(tipo_documento)
    data = dict(zip(columnas, row)) if row else {}
    ruta_archivo = data.get(config["documento_col"])
    respuesta = {
        "tipo_documento": tipo_documento,
        "tabla": tipo_documento,
        "subcarpeta": config["subcarpeta"],
        "registro_existe": row is not None,
        "id": data.get("id"),
        "proyecto_id": data.get("proyecto_id"),
        "fecha_documento": data.get(config["fecha_col"]),
        "ruta_documento": ruta_archivo,
        "url_documento": construir_url_archivo(ruta_archivo),
        "estado_documento": data.get(config["estado_col"]),
        "creado_en": data.get("creado_en"),
        "usuario_creacion": data.get("usuario_creacion"),
        "unidad_usuario_final": data.get("unidad_usuario_final"),
        "archivos_subcarpeta": listar_archivos_directos(ruta_subcarpeta),
    }

    if config["bool_col"]:
        respuesta[config["bool_col"]] = data.get(config["bool_col"])

    if carpeta_matriz:
        respuesta["carpeta_matriz"] = {"id": carpeta_matriz[0], "nombre": carpeta_matriz[1], "ruta": carpeta_matriz[2]}

    if carpeta_proyecto:
        respuesta["carpeta_proyecto"] = {"id": carpeta_proyecto[0], "nombre": carpeta_proyecto[2], "ruta": carpeta_proyecto[3], "descripcion": carpeta_proyecto[4]}

    if subcarpeta:
        respuesta["subcarpeta_detalle"] = {"id": subcarpeta[0], "nombre": subcarpeta[1], "ruta": subcarpeta[2], "descripcion": subcarpeta[3]}

    return respuesta


def obtener_documentos_proyecto(cur, proyecto_id: int) -> dict:
    """Consolida todos los tipos documentales configurados para un proyecto."""
    documentos = {}

    for tipo_documento in DOCUMENTOS_CONFIG:
        _, carpeta_matriz, carpeta_proyecto, subcarpeta = obtener_subcarpeta_documento(cur, proyecto_id, tipo_documento)
        row, _ = obtener_registro_documento(cur, tipo_documento, proyecto_id)
        documentos[tipo_documento] = serializar_registro_documento(
            tipo_documento,
            row,
            subcarpeta[2],
            carpeta_matriz,
            carpeta_proyecto,
            subcarpeta,
        )

    return documentos


def obtener_documentos_cargados_proyecto(cur, proyecto_id: int) -> list[dict]:
    """Retorna todos los registros documentales que tienen archivo asociado."""
    documentos_cargados = []

    for tipo_documento in DOCUMENTOS_CONFIG:
        _, carpeta_matriz, carpeta_proyecto, subcarpeta = obtener_subcarpeta_documento(cur, proyecto_id, tipo_documento)
        rows, columnas = obtener_registros_documento(cur, tipo_documento, proyecto_id)
        config = obtener_config_documento(tipo_documento)

        for row in rows:
            data = dict(zip(columnas, row))
            ruta_documento = data.get(config["documento_col"])

            if not ruta_documento:
                continue

            documentos_cargados.append({
                "id": data.get("id"),
                "tipo_documento": tipo_documento,
                "tabla": tipo_documento,
                "subcarpeta": config["subcarpeta"],
                "existe_registro": True,
                "valor_documento": data.get(config["bool_col"]) if config["bool_col"] else bool(ruta_documento),
                "fecha_documento": data.get(config["fecha_col"]),
                "estado_documento": data.get(config["estado_col"]),
                "documento": ruta_documento,
                "url_documento": construir_url_archivo(ruta_documento),
                "unidad_usuario_final": data.get("unidad_usuario_final"),
                "usuario_creacion": data.get("usuario_creacion"),
                "creado_en": data.get("creado_en"),
                "carpeta_matriz": {
                    "id": carpeta_matriz[0],
                    "nombre": carpeta_matriz[1],
                    "ruta": carpeta_matriz[2],
                },
                "carpeta_proyecto": {
                    "id": carpeta_proyecto[0],
                    "nombre": carpeta_proyecto[2],
                    "ruta": carpeta_proyecto[3],
                },
                "subcarpeta_detalle": {
                    "id": subcarpeta[0],
                    "nombre": subcarpeta[1],
                    "ruta": subcarpeta[2],
                },
            })

    documentos_cargados.sort(
        key=lambda doc: (doc.get("creado_en") is not None, doc.get("creado_en"), doc.get("id")),
        reverse=True,
    )
    return documentos_cargados


def obtener_usuario_logueado(payload: dict) -> str:
    """Resuelve el usuario autenticado desde el token o desde la tabla usuarios."""
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
    """Crea un proyecto y su estructura documental inicial dentro de la matriz activa.

    El endpoint valida duplicados de matricula, verifica la existencia de una
    carpeta matriz activa y crea la carpeta principal del proyecto junto con sus
    subcarpetas documentales estandar antes de insertar el registro principal en
    la tabla proyectos.
    """

    usuario_creacion = obtener_usuario_logueado(payload)

    nombre_carpeta = limpiar_nombre(titulo_corto or titulo)
    ruta_base = None
    carpeta_actividades = f"actividades_{nombre_carpeta}"

    subcarpetas = ["presupuesto_proyecto", "acta_cierre_proyecto", "informe_final_proyecto", "procediemientos_corrspondientes", "manual_ensamblador", "manual_usuario_final", "encuesta_unidad_usuario_final", "capacitacion_usuario_final", "paquete_tecnico_proyecto", "documento_entrega_proyecto", "compromiso_confidencialidad_proyecto", "cesion_derechos_proyecto", "seguimiento_proyecto_mensual", "control_cambios_proyecto", "elaboracion_formato_leciones_aprendidas", "pruebas_entorno_real_trl6", "pruebas_entorno_cercano_real_trl5", "pruebas_entorno_controlado_trl5", "pruebas_laboratorio_componetes_trl4", "pruebas_laboratorio_informe_analisis_trl3", "definicion_tecnica_solucion_trl2", "acta_validacion_proyecto", "acta_inicio_proyecto", "formato_formulacion_proyecto", carpeta_actividades, "tabla_trl"]



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

                # Registra la carpeta logica del proyecto dentro de la matriz activa.
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
    """Actualiza los campos editables del proyecto principal.

    Solo se modifican los valores enviados en el formulario. Si no llega ningun
    campo, el endpoint devuelve error de validacion.
    """
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


@router.post("/api/proyectos/{proyecto_id}/actividades")
async def crear_actividad_proyecto(
    proyecto_id: int,
    payload: dict = Depends(verificar_token),
    actividad: str = Form(...),
    descripcion: str | None = Form(None),
    fecha_inicio: str | None = Form(None),
    fecha_fin: str | None = Form(None),
    estado: str | None = Form(None),
    estado_documento_entrega: str | None = Form(None),
    archivo: UploadFile | None = File(None),
    documento: UploadFile | None = File(None),
    file: UploadFile | None = File(None),
):
    """Crea una actividad del proyecto y su subcarpeta documental."""
    usuario_logueado = obtener_usuario_logueado(payload)
    archivo_recibido = resolver_archivo_subido(archivo, documento, file)
    ruta_documento = None
    actividad_id = None
    committed = False

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                obtener_proyecto_base(cur, proyecto_id)
                cur.execute(
                    """
                    INSERT INTO actividades_proyecto (
                        proyecto_id,
                        actividad,
                        descripcion,
                        fecha_inicio,
                        fecha_fin,
                        estado,
                        estado_documento_entrega,
                        usuario_creacion
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        proyecto_id,
                        actividad,
                        descripcion,
                        fecha_inicio,
                        fecha_fin,
                        estado,
                        estado_documento_entrega,
                        usuario_logueado,
                    )
                )
                actividad_id = cur.fetchone()[0]

                _, _, _, _, _, ruta_actividad = obtener_o_crear_carpeta_actividad(cur, proyecto_id, actividad_id, actividad)

                if archivo_recibido is not None:
                    ruta_documento = await guardar_archivo_documento(archivo_recibido, ruta_actividad)
                    cur.execute(
                        """
                        UPDATE actividades_proyecto
                        SET documento_entrega = %s,
                            estado_documento_entrega = %s
                        WHERE id = %s
                          AND proyecto_id = %s
                        """,
                        (ruta_documento, estado_documento_entrega or "CARGADO", actividad_id, proyecto_id)
                    )

            conn.commit()
            committed = True

        with get_conn() as conn:
            with conn.cursor() as cur:
                row = obtener_actividad_proyecto(cur, proyecto_id, actividad_id)
                actividad_data = serializar_actividad_proyecto(cur, row)

        return {
            "mensaje": "Actividad creada correctamente",
            "actividad": actividad_data,
        }
    except HTTPException:
        if ruta_documento and not committed:
            eliminar_archivo_documento(ruta_documento)
        raise
    except Exception as e:
        if ruta_documento and not committed:
            eliminar_archivo_documento(ruta_documento)
        raise HTTPException(status_code=500, detail=f"Error creando actividad: {str(e)}")


@router.get("/api/proyectos/{proyecto_id}/actividades")
async def listar_actividades_proyecto(
    proyecto_id: int,
    payload: dict = Depends(verificar_token)
):
    """Lista las actividades asociadas al proyecto."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            obtener_proyecto_base(cur, proyecto_id)
            cur.execute(
                """
                SELECT id, proyecto_id, actividad, descripcion, fecha_inicio, fecha_fin,
                       estado, documento_entrega, estado_documento_entrega, creado_en,
                       usuario_creacion
                FROM actividades_proyecto
                WHERE proyecto_id = %s
                ORDER BY creado_en DESC, id DESC
                """,
                (proyecto_id,)
            )
            rows = cur.fetchall()
            actividades = [serializar_actividad_proyecto(cur, row) for row in rows]

    return {
        "proyecto_id": proyecto_id,
        "total": len(actividades),
        "actividades": actividades,
    }


@router.get("/api/proyectos/{proyecto_id}/actividades/{actividad_id}")
async def obtener_actividad_proyecto_endpoint(
    proyecto_id: int,
    actividad_id: int,
    payload: dict = Depends(verificar_token)
):
    """Obtiene el detalle de una actividad del proyecto."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            row = obtener_actividad_proyecto(cur, proyecto_id, actividad_id)
            actividad_data = serializar_actividad_proyecto(cur, row)

    return actividad_data


@router.put("/api/proyectos/{proyecto_id}/actividades/{actividad_id}")
async def actualizar_actividad_proyecto(
    proyecto_id: int,
    actividad_id: int,
    payload: dict = Depends(verificar_token),
    actividad: str | None = Form(None),
    descripcion: str | None = Form(None),
    fecha_inicio: str | None = Form(None),
    fecha_fin: str | None = Form(None),
    estado: str | None = Form(None),
    estado_documento_entrega: str | None = Form(None),
    archivo: UploadFile | None = File(None),
    documento: UploadFile | None = File(None),
    file: UploadFile | None = File(None),
):
    """Actualiza una actividad del proyecto y su documento de entrega."""
    usuario_logueado = obtener_usuario_logueado(payload)
    archivo_recibido = resolver_archivo_subido(archivo, documento, file)
    ruta_nueva = None
    ruta_anterior = None
    committed = False

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                row = obtener_actividad_proyecto(cur, proyecto_id, actividad_id)
                nombre_actividad = actividad if actividad is not None else row[2]
                _, _, _, _, _, ruta_actividad = obtener_o_crear_carpeta_actividad(cur, proyecto_id, actividad_id, nombre_actividad)
                ruta_anterior = row[7]

                if archivo_recibido is not None:
                    ruta_nueva = await guardar_archivo_documento(archivo_recibido, ruta_actividad)

                campos = []
                valores = []

                if actividad is not None:
                    campos.append("actividad = %s")
                    valores.append(actividad)

                if descripcion is not None:
                    campos.append("descripcion = %s")
                    valores.append(descripcion)

                if fecha_inicio is not None:
                    campos.append("fecha_inicio = %s")
                    valores.append(fecha_inicio)

                if fecha_fin is not None:
                    campos.append("fecha_fin = %s")
                    valores.append(fecha_fin)

                if estado is not None:
                    campos.append("estado = %s")
                    valores.append(estado)

                if ruta_nueva is not None:
                    campos.append("documento_entrega = %s")
                    valores.append(ruta_nueva)

                if estado_documento_entrega is not None:
                    campos.append("estado_documento_entrega = %s")
                    valores.append(estado_documento_entrega)
                elif ruta_nueva is not None:
                    campos.append("estado_documento_entrega = %s")
                    valores.append("CARGADO")

                if not campos:
                    raise HTTPException(status_code=400, detail="No se enviaron campos para actualizar")

                campos.append("usuario_creacion = %s")
                valores.append(usuario_logueado)
                valores.extend([actividad_id, proyecto_id])

                cur.execute(
                    f"UPDATE actividades_proyecto SET {', '.join(campos)} WHERE id = %s AND proyecto_id = %s",
                    tuple(valores)
                )

            conn.commit()
            committed = True

        if ruta_nueva and ruta_anterior and ruta_nueva != ruta_anterior:
            eliminar_archivo_documento(ruta_anterior)

        with get_conn() as conn:
            with conn.cursor() as cur:
                row = obtener_actividad_proyecto(cur, proyecto_id, actividad_id)
                actividad_data = serializar_actividad_proyecto(cur, row)

        return {
            "mensaje": "Actividad actualizada correctamente",
            "actividad": actividad_data,
        }
    except HTTPException:
        if ruta_nueva and not committed:
            eliminar_archivo_documento(ruta_nueva)
        raise
    except Exception as e:
        if ruta_nueva and not committed:
            eliminar_archivo_documento(ruta_nueva)
        raise HTTPException(status_code=500, detail=f"Error actualizando actividad: {str(e)}")


@router.delete("/api/proyectos/{proyecto_id}/actividades/{actividad_id}")
async def eliminar_actividad_proyecto(
    proyecto_id: int,
    actividad_id: int,
    payload: dict = Depends(verificar_token)
):
    """Elimina una actividad del proyecto junto con su carpeta documental."""
    ruta_documento = None
    ruta_actividad = None

    with get_conn() as conn:
        with conn.cursor() as cur:
            row = obtener_actividad_proyecto(cur, proyecto_id, actividad_id)
            ruta_documento = row[7]
            _, _, _, _, _, ruta_actividad = obtener_o_crear_carpeta_actividad(cur, proyecto_id, actividad_id, row[2])

            cur.execute(
                "DELETE FROM actividades_proyecto WHERE id = %s AND proyecto_id = %s",
                (actividad_id, proyecto_id)
            )

        conn.commit()

    eliminar_archivo_documento(ruta_documento)

    if ruta_actividad:
        ruta_actividad_fisica = ruta_relativa_a_fisica(ruta_actividad)
        if os.path.isdir(ruta_actividad_fisica):
            shutil.rmtree(ruta_actividad_fisica, ignore_errors=True)

    return {
        "mensaje": "Actividad eliminada correctamente",
        "proyecto_id": proyecto_id,
        "actividad_id": actividad_id,
    }


@router.post("/api/proyectos/{proyecto_id}/documentos/{tipo_documento}")
async def crear_documento_proyecto(
    proyecto_id: int,
    tipo_documento: str,
    payload: dict = Depends(verificar_token),
    fecha_documento: str | None = Form(None),
    estado_documento: str | None = Form(None),
    valor_documento: bool | None = Form(None),
    unidad_usuario_final: str | None = Form(None),
    archivo: UploadFile | None = File(None),
    documento: UploadFile | None = File(None),
    file: UploadFile | None = File(None),
):
    """Crea el registro documental de un proyecto y guarda el archivo si llega.

    El tipo documental define automaticamente la tabla, la subcarpeta y las
    columnas SQL involucradas mediante DOCUMENTOS_CONFIG.
    """
    tipo_documento = resolver_tipo_documento(tipo_documento)
    usuario_logueado = obtener_usuario_logueado(payload)
    config = obtener_config_documento(tipo_documento)
    archivo_recibido = resolver_archivo_subido(archivo, documento, file)
    ruta_nueva = None
    committed = False

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                proyecto, carpeta_matriz, carpeta_proyecto, subcarpeta = obtener_subcarpeta_documento(cur, proyecto_id, tipo_documento)

                if archivo_recibido is not None:
                    ruta_nueva = await guardar_archivo_documento(archivo_recibido, subcarpeta[2])

                if valor_documento is True and archivo_recibido is None:
                    raise HTTPException(status_code=400, detail="Se indico que existe documento, pero no se recibio ningun archivo en el formulario")

                if not any([ruta_nueva, fecha_documento, estado_documento, valor_documento is not None, unidad_usuario_final]):
                    raise HTTPException(status_code=400, detail="Debe enviar metadata o un archivo para registrar el documento")

                insertar_registro_documento(
                    cur,
                    tipo_documento,
                    proyecto_id,
                    proyecto,
                    usuario_logueado,
                    fecha_documento,
                    estado_documento,
                    valor_documento,
                    unidad_usuario_final,
                    ruta_nueva,
                )

            conn.commit()
            committed = True

        with get_conn() as conn:
            with conn.cursor() as cur:
                _, carpeta_matriz, carpeta_proyecto, subcarpeta = obtener_subcarpeta_documento(cur, proyecto_id, tipo_documento)
                row_guardada, _ = obtener_registro_documento(cur, tipo_documento, proyecto_id)

        return {
            "mensaje": "Documento registrado correctamente",
            "documento": serializar_registro_documento(
                tipo_documento,
                row_guardada,
                subcarpeta[2],
                carpeta_matriz,
                carpeta_proyecto,
                subcarpeta,
            )
        }
    except HTTPException:
        if ruta_nueva and not committed:
            eliminar_archivo_documento(ruta_nueva)
        raise
    except Exception as e:
        if ruta_nueva and not committed:
            eliminar_archivo_documento(ruta_nueva)
        raise HTTPException(status_code=500, detail=f"Error registrando documento: {str(e)}")


@router.get("/api/proyectos/{proyecto_id}/documentos")
async def listar_documentos_proyecto(
    proyecto_id: int,
    payload: dict = Depends(verificar_token)
):
    """Lista el estado documental consolidado de un proyecto."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            obtener_proyecto_base(cur, proyecto_id)
            documentos = obtener_documentos_proyecto(cur, proyecto_id)
  
    return {
        "proyecto_id": proyecto_id,
        "documentos": documentos
    }


@router.get("/api/proyectos/{proyecto_id}/documentos/cargados")
async def listar_documentos_cargados_proyecto(
    proyecto_id: int,
    payload: dict = Depends(verificar_token)
):
    """Devuelve solo los documentos que ya tienen archivo cargado para el proyecto."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            obtener_proyecto_base(cur, proyecto_id)
            documentos_cargados = obtener_documentos_cargados_proyecto(cur, proyecto_id)

    return {
        "proyecto_id": proyecto_id,
        "total": len(documentos_cargados),
        "documentos": documentos_cargados,
    }


@router.get("/api/proyectos/{proyecto_id}/documentos/{tipo_documento}")
async def obtener_documento_proyecto(
    proyecto_id: int,
    tipo_documento: str,
    payload: dict = Depends(verificar_token)
):
    """Devuelve el detalle de un unico tipo documental para un proyecto."""
    tipo_documento = resolver_tipo_documento(tipo_documento)
    with get_conn() as conn:
        with conn.cursor() as cur:
            _, carpeta_matriz, carpeta_proyecto, subcarpeta = obtener_subcarpeta_documento(cur, proyecto_id, tipo_documento)
            row, _ = obtener_registro_documento(cur, tipo_documento, proyecto_id)

    return serializar_registro_documento(
        tipo_documento,
        row,
        subcarpeta[2],
        carpeta_matriz,
        carpeta_proyecto,
        subcarpeta,
    )


@router.put("/api/proyectos/{proyecto_id}/documentos/{tipo_documento}")
async def actualizar_documento_proyecto(
    proyecto_id: int,
    tipo_documento: str,
    payload: dict = Depends(verificar_token),
    fecha_documento: str | None = Form(None),
    estado_documento: str | None = Form(None),
    valor_documento: bool | None = Form(None),
    unidad_usuario_final: str | None = Form(None),
    archivo: UploadFile | None = File(None),
    documento: UploadFile | None = File(None),
    file: UploadFile | None = File(None),
):
    """Actualiza metadata documental o agrega un nuevo archivo al mismo modulo."""
    tipo_documento = resolver_tipo_documento(tipo_documento)
    usuario_logueado = obtener_usuario_logueado(payload)
    config = obtener_config_documento(tipo_documento)
    archivo_recibido = resolver_archivo_subido(archivo, documento, file)
    ruta_nueva = None
    ruta_anterior = None
    committed = False

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                proyecto, carpeta_matriz, carpeta_proyecto, subcarpeta = obtener_subcarpeta_documento(cur, proyecto_id, tipo_documento)
                row_actual, columnas = obtener_registro_documento(cur, tipo_documento, proyecto_id)

                if not row_actual:
                    raise HTTPException(status_code=404, detail="El documento no existe para este proyecto")

                data_actual = dict(zip(columnas, row_actual))
                ruta_anterior = data_actual.get(config["documento_col"])

                if archivo_recibido is not None:
                    ruta_nueva = await guardar_archivo_documento(archivo_recibido, subcarpeta[2])

                if valor_documento is True and archivo_recibido is None and not ruta_anterior:
                    raise HTTPException(status_code=400, detail="Se indico que existe documento, pero no se recibio ningun archivo en el formulario")

                if ruta_nueva:
                    insertar_registro_documento(
                        cur,
                        tipo_documento,
                        proyecto_id,
                        proyecto,
                        usuario_logueado,
                        fecha_documento or data_actual.get(config["fecha_col"]),
                        estado_documento or data_actual.get(config["estado_col"]),
                        valor_documento if valor_documento is not None else True,
                        unidad_usuario_final or data_actual.get("unidad_usuario_final"),
                        ruta_nueva,
                    )
                    conn.commit()
                    committed = True
                    ruta_nueva = None
                else:
                    campos = []
                    valores = []

                    if config["bool_col"] and valor_documento is not None:
                        campos.append(f"{config['bool_col']} = %s")
                        valores.append(valor_documento)

                    if fecha_documento is not None:
                        campos.append(f"{config['fecha_col']} = %s")
                        valores.append(fecha_documento)

                    if estado_documento is not None:
                        campos.append(f"{config['estado_col']} = %s")
                        valores.append(estado_documento)

                    if unidad_usuario_final is not None:
                        campos.append("unidad_usuario_final = %s")
                        valores.append(unidad_usuario_final)

                    if not campos:
                        raise HTTPException(status_code=400, detail="No se enviaron campos para actualizar")

                    campos.append("usuario_creacion = %s")
                    valores.append(usuario_logueado)
                    valores.append(proyecto_id)

                    cur.execute(
                        f"UPDATE {tipo_documento} SET {', '.join(campos)} WHERE proyecto_id = %s AND id = %s",
                        tuple(valores + [data_actual.get('id')])
                    )

                    conn.commit()
                    committed = True

        with get_conn() as conn:
            with conn.cursor() as cur:
                _, carpeta_matriz, carpeta_proyecto, subcarpeta = obtener_subcarpeta_documento(cur, proyecto_id, tipo_documento)
                row_actualizada, _ = obtener_registro_documento(cur, tipo_documento, proyecto_id)

        return {
            "mensaje": "Documento actualizado correctamente",
            "documento": serializar_registro_documento(
                tipo_documento,
                row_actualizada,
                subcarpeta[2],
                carpeta_matriz,
                carpeta_proyecto,
                subcarpeta,
            )
        }
    except HTTPException:
        if ruta_nueva and not committed:
            eliminar_archivo_documento(ruta_nueva)
        raise
    except Exception as e:
        if ruta_nueva and not committed:
            eliminar_archivo_documento(ruta_nueva)
        raise HTTPException(status_code=500, detail=f"Error actualizando documento: {str(e)}")


@router.delete("/api/proyectos/{proyecto_id}/documentos/{tipo_documento}")
async def eliminar_documento_proyecto(
    proyecto_id: int,
    tipo_documento: str,
    payload: dict = Depends(verificar_token)
):
    """Elimina el registro documental del proyecto y su archivo asociado."""
    tipo_documento = resolver_tipo_documento(tipo_documento)
    ruta_documento = None

    with get_conn() as conn:
        with conn.cursor() as cur:
            obtener_subcarpeta_documento(cur, proyecto_id, tipo_documento)
            row_actual, columnas = obtener_registro_documento(cur, tipo_documento, proyecto_id)

            if not row_actual:
                raise HTTPException(status_code=404, detail="El documento no existe para este proyecto")

            ruta_documento = dict(zip(columnas, row_actual)).get(obtener_config_documento(tipo_documento)["documento_col"])

            cur.execute(
                f"DELETE FROM {tipo_documento} WHERE proyecto_id = %s",
                (proyecto_id,)
            )

        conn.commit()

    eliminar_archivo_documento(ruta_documento)

    return {
        "mensaje": "Documento eliminado correctamente",
        "proyecto_id": proyecto_id,
        "tipo_documento": tipo_documento
    }


@router.get("/api/proyectos/{proyecto_id}/trl")
async def listar_tabla_trl_proyecto(
    proyecto_id: int,
    payload: dict = Depends(verificar_token)
):
    """Lista la matriz TRL registrada para un proyecto."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            obtener_proyecto_base(cur, proyecto_id)
            cur.execute(
                """
                SELECT id, id_proyecto, trl, numero_orden, pregunta_trl, cumple_trl,
                       documento_evidencia, observaciones, estado_docuemento_entrega, creado_en,
                       usuario_creacion
                FROM tabla_trl
                WHERE id_proyecto = %s
                ORDER BY trl ASC, numero_orden ASC, id ASC
                """,
                (proyecto_id,)
            )
            rows = cur.fetchall()
            registros = [serializar_registro_trl(cur, row) for row in rows]

    return {
        "proyecto_id": proyecto_id,
        "total": len(registros),
        "registros": registros,
    }


@router.get("/api/proyectos/{proyecto_id}/trl/{trl_id}")
async def obtener_registro_trl_proyecto_endpoint(
    proyecto_id: int,
    trl_id: int,
    payload: dict = Depends(verificar_token)
):
    """Obtiene el detalle de un registro TRL del proyecto."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            row = obtener_registro_trl(cur, proyecto_id, trl_id)
            registro_data = serializar_registro_trl(cur, row)

    return registro_data


@router.post("/api/proyectos/{proyecto_id}/trl")
async def crear_registro_trl_proyecto(
    proyecto_id: int,
    payload: dict = Depends(verificar_token),
    trl: int = Form(...),
    numero_orden: int | None = Form(None),
    pregunta_trl: str = Form(...),
    cumple_trl: bool = Form(False),
    observaciones: str | None = Form(None),
    estado_docuemento_entrega: str | None = Form(None),
    documento_evidencia: list[UploadFile] | None = File(None),
    documentos_evidencia: list[UploadFile] | None = File(None),
    archivo: list[UploadFile] | None = File(None),
    file: list[UploadFile] | None = File(None),
):
    """Crea un registro TRL del proyecto y su subcarpeta documental."""
    usuario_logueado = obtener_usuario_logueado(payload)
    archivos_recibidos = resolver_archivos_subidos(documento_evidencia, documentos_evidencia, archivo, file)
    rutas_nuevas: list[str] = []
    committed = False

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                obtener_proyecto_base(cur, proyecto_id)
                cur.execute(
                    """
                    INSERT INTO tabla_trl (
                        id_proyecto, trl, numero_orden, pregunta_trl, cumple_trl,
                        documento_evidencia, observaciones, estado_docuemento_entrega, usuario_creacion
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        proyecto_id,
                        trl,
                        numero_orden,
                        pregunta_trl,
                        cumple_trl,
                        None,
                        observaciones,
                        estado_docuemento_entrega or ("CARGADO" if archivos_recibidos else "PENDIENTE"),
                        usuario_logueado,
                    )
                )
                registro_id = cur.fetchone()[0]

                _, _, _, _, _, ruta_registro = obtener_o_crear_carpeta_registro_trl(
                    cur, proyecto_id, registro_id, pregunta_trl
                )

                for archivo_recibido in archivos_recibidos:
                    rutas_nuevas.append(await guardar_archivo_documento(archivo_recibido, ruta_registro))

                documento_guardado = serializar_documentos_trl(rutas_nuevas)
                estado_final = estado_docuemento_entrega or ("CARGADO" if documento_guardado else "PENDIENTE")

                cur.execute(
                    """
                    UPDATE tabla_trl
                    SET documento_evidencia = %s,
                        estado_docuemento_entrega = %s
                    WHERE id = %s
                      AND id_proyecto = %s
                    """,
                    (documento_guardado, estado_final, registro_id, proyecto_id)
                )

            conn.commit()
            committed = True

        with get_conn() as conn:
            with conn.cursor() as cur:
                row = obtener_registro_trl(cur, proyecto_id, registro_id)
                registro_data = serializar_registro_trl(cur, row)

        return {
            "mensaje": "Registro TRL guardado correctamente",
            "registro": registro_data,
        }
    except HTTPException:
        if not committed:
            for ruta in rutas_nuevas:
                eliminar_archivo_documento(ruta)
        raise
    except Exception as e:
        if not committed:
            for ruta in rutas_nuevas:
                eliminar_archivo_documento(ruta)
        raise HTTPException(status_code=500, detail=f"Error guardando registro TRL: {str(e)}")


@router.put("/api/proyectos/{proyecto_id}/trl/{trl_id}")
async def actualizar_registro_trl_proyecto(
    proyecto_id: int,
    trl_id: int,
    payload: dict = Depends(verificar_token),
    trl: int | None = Form(None),
    numero_orden: int | None = Form(None),
    pregunta_trl: str | None = Form(None),
    cumple_trl: bool | None = Form(None),
    observaciones: str | None = Form(None),
    estado_docuemento_entrega: str | None = Form(None),
    documento_evidencia: list[UploadFile] | None = File(None),
    documentos_evidencia: list[UploadFile] | None = File(None),
    archivo: list[UploadFile] | None = File(None),
    file: list[UploadFile] | None = File(None),
):
    """Actualiza un registro TRL del proyecto y agrega evidencias sin eliminar las anteriores."""
    usuario_logueado = obtener_usuario_logueado(payload)
    archivos_recibidos = resolver_archivos_subidos(documento_evidencia, documentos_evidencia, archivo, file)
    rutas_nuevas: list[str] = []
    committed = False

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                obtener_proyecto_base(cur, proyecto_id)
                row = obtener_registro_trl(cur, proyecto_id, trl_id)
                documentos_existentes = normalizar_documentos_trl(row[6])
                trl_final = trl if trl is not None else row[2]
                numero_orden_final = numero_orden if numero_orden is not None else row[3]
                pregunta_final = pregunta_trl if pregunta_trl is not None else row[4]
                cumple_final = cumple_trl if cumple_trl is not None else row[5]
                observaciones_final = observaciones if observaciones is not None else row[7]

                _, _, _, _, _, ruta_registro = obtener_o_crear_carpeta_registro_trl(
                    cur, proyecto_id, trl_id, pregunta_final, documentos_existentes
                )

                for archivo_recibido in archivos_recibidos:
                    rutas_nuevas.append(await guardar_archivo_documento(archivo_recibido, ruta_registro))

                documentos = documentos_existentes + rutas_nuevas
                documento_guardado = serializar_documentos_trl(documentos)
                estado_final = estado_docuemento_entrega or ("CARGADO" if documento_guardado else "PENDIENTE")

                campos = []
                valores = []

                if trl is not None:
                    campos.append("trl = %s")
                    valores.append(trl_final)

                if numero_orden is not None:
                    campos.append("numero_orden = %s")
                    valores.append(numero_orden_final)

                if pregunta_trl is not None:
                    campos.append("pregunta_trl = %s")
                    valores.append(pregunta_final)

                if cumple_trl is not None:
                    campos.append("cumple_trl = %s")
                    valores.append(cumple_final)

                if observaciones is not None:
                    campos.append("observaciones = %s")
                    valores.append(observaciones_final)

                if rutas_nuevas:
                    campos.append("documento_evidencia = %s")
                    valores.append(documento_guardado)

                if estado_docuemento_entrega is not None:
                    campos.append("estado_docuemento_entrega = %s")
                    valores.append(estado_final)
                elif rutas_nuevas:
                    campos.append("estado_docuemento_entrega = %s")
                    valores.append("CARGADO")

                if not campos:
                    raise HTTPException(status_code=400, detail="No se enviaron campos para actualizar")

                campos.append("usuario_creacion = %s")
                valores.append(usuario_logueado)
                valores.extend([trl_id, proyecto_id])

                cur.execute(
                    f"UPDATE tabla_trl SET {', '.join(campos)} WHERE id = %s AND id_proyecto = %s",
                    tuple(valores)
                )

            conn.commit()
            committed = True

        with get_conn() as conn:
            with conn.cursor() as cur:
                row = obtener_registro_trl(cur, proyecto_id, trl_id)
                registro_data = serializar_registro_trl(cur, row)

        return {
            "mensaje": "Registro TRL actualizado correctamente",
            "registro": registro_data,
        }
    except HTTPException:
        if not committed:
            for ruta in rutas_nuevas:
                eliminar_archivo_documento(ruta)
        raise
    except Exception as e:
        if not committed:
            for ruta in rutas_nuevas:
                eliminar_archivo_documento(ruta)
        raise HTTPException(status_code=500, detail=f"Error actualizando registro TRL: {str(e)}")


@router.delete("/api/proyectos/{proyecto_id}/trl/{trl_id}")
async def eliminar_registro_trl_proyecto(
    proyecto_id: int,
    trl_id: int,
    payload: dict = Depends(verificar_token)
):
    """Elimina un registro TRL del proyecto junto con su carpeta documental."""
    ruta_registro = None
    documentos = []

    with get_conn() as conn:
        with conn.cursor() as cur:
            row = obtener_registro_trl(cur, proyecto_id, trl_id)
            documentos = normalizar_documentos_trl(row[6])
            _, _, _, _, _, ruta_registro = obtener_o_crear_carpeta_registro_trl(
                cur, proyecto_id, trl_id, row[4], documentos
            )

            cur.execute(
                "DELETE FROM tabla_trl WHERE id = %s AND id_proyecto = %s",
                (trl_id, proyecto_id)
            )

        conn.commit()

    for ruta in documentos:
        eliminar_archivo_documento(ruta)

    if ruta_registro:
        ruta_registro_fisica = ruta_relativa_a_fisica(ruta_registro)
        if os.path.isdir(ruta_registro_fisica):
            shutil.rmtree(ruta_registro_fisica, ignore_errors=True)

    return {
        "mensaje": "Registro TRL eliminado correctamente",
        "proyecto_id": proyecto_id,
        "trl_id": trl_id,
    }


@router.get("/api/proyectos/{proyecto_id}")
async def obtener_proyecto(
    proyecto_id: int,
    payload: dict = Depends(verificar_token)
 ):
    """Obtiene el detalle completo del proyecto, su arbol y su estado documental."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Consulta principal del proyecto con nombres de area y subarea.
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
            documentos_proyecto = {}
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

            # Si la estructura documental no esta completa, se retorna el proyecto
            # sin bloquear la respuesta principal del CRUD base.
            try:
                documentos_proyecto = obtener_documentos_proyecto(cur, proyecto_id)
            except HTTPException:
                documentos_proyecto = {}

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
                "carpetas_proyecto": carpetas_proyecto,
                "documentos": documentos_proyecto
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
    """Lista proyectos con filtros basicos sobre matricula, titulo y fechas."""
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
    """Cierra el pool de conexiones cuando el servicio se apaga."""
    pool.close()
