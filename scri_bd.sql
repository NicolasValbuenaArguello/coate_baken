-- ============================================================
-- BASE DE DATOS: MANDO CONTROL COATE
-- Version consolidada y organizada por dependencias
-- ============================================================

SET client_min_messages TO WARNING;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- CATALOGOS BASE
-- ============================================================

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,
    descripcion TEXT
);

INSERT INTO roles (nombre, descripcion) VALUES
('SUPER', 'Super administrador con control total'),
('ADMIN', 'Administrador con acceso ampliado'),
('USUARIO', 'Operador con acceso restringido')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS grados (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,
    abreviatura VARCHAR(20),
    nivel INTEGER NOT NULL
);

INSERT INTO grados (nombre, abreviatura, nivel) VALUES
('General', 'GR', 0),
('Mayor General', 'MG', 1),
('Brigadier General', 'BG', 2),
('Coronel', 'CR', 3),
('Teniente Coronel', 'TC', 4),
('Mayor', 'MY', 5),
('Capitan', 'CT', 6),
('Teniente', 'TE', 7),
('Subteniente', 'ST', 8),
('Sargento Mayor Comando', 'SMC', 9),
('Sargento Mayor', 'SM', 10),
('Sargento Primero', 'SP', 11),
('Sargento Segundo', 'SS', 12),
('Cabo Primero', 'CP', 13),
('Cabo Segundo', 'CS', 14),
('Cabo Tercero', 'C3', 15),
('Soldado Profesional', 'SLP', 16),
('Civil', 'CIV', 17)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS paginas (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    ruta VARCHAR(200) UNIQUE NOT NULL,
    descripcion TEXT,
    activa BOOLEAN DEFAULT TRUE,
    creada_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_paginas_nombre ON paginas(nombre);
CREATE INDEX IF NOT EXISTS idx_paginas_activa ON paginas(activa);

INSERT INTO paginas (nombre, ruta, descripcion) VALUES
('Home', '/home', 'Panel principal'),
('Usuarios Ingreso', '/usuarios/nuevos', 'Creacion de usuarios'),
('Usuarios Listados', '/usuarios/listado', 'Listado y gestion de usuarios'),
('Cargue Personal', '/personal/cargue', 'Carga masiva de novedades de personal'),
('Dashboard Personal', '/personal/dashboard', 'Panel de estadisticas de personal'),
('Areas', '/areas/subareas', 'Gestion de areas y subareas'),
('Ordenes', '/ordenes/creacion', 'Gestion de ordenes'),
('Ordenes', '/ordenes/listado', 'Listado de ordenes'),
('Ordenes', '/ordenes/dashboard', 'Dashboard de ordenes'),
('Proyectos', '/proyectos/creacion', 'Gestion de proyectos'),
('Proyectos', '/proyectos/listado', 'Listado de proyectos'),
('Proyectos', '/proyectos/dashboard', 'Dashboard de proyectos'),
('Calendario', '/calendario/calendario', 'Calendario de actividades'),
('Chat', '/chat/chat', 'Modulo de chat'),
('Chat', '/chat/foro', 'Modulo de foro'),
('Configuracion', '/configuracion/general', 'Configuracion de parametros generales'),
('Carpetas Documentos', '/carpetas/documentos', 'Gestion de carpetas y documentos')
ON CONFLICT (ruta) DO NOTHING;

CREATE TABLE IF NOT EXISTS unidades (
    id SERIAL PRIMARY KEY,
    sigla VARCHAR(10) UNIQUE NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    nivel VARCHAR(50) NOT NULL DEFAULT 'OTRA'
);

-- ============================================================
-- PERSONAL
-- ============================================================

CREATE TABLE IF NOT EXISTS personal_novedades (
    id SERIAL PRIMARY KEY,
    id_grado INTEGER REFERENCES grados(id) ON DELETE SET NULL,
    apellidos_nombres TEXT,
    cc BIGINT,
    relacion_mando TEXT,
    ciclo TEXT,
    actividad TEXT,
    ubicacion TEXT,
    cargo_especialidad TEXT,
    sexo TEXT,
    telefono BIGINT,
    rh TEXT,
    contacto_emergencia TEXT,
    telefono_emergencia BIGINT,
    parentesco TEXT,
    fecha_inicio_novedad DATE,
    fecha_termino_novedad DATE,
    estado_civil TEXT,
    escolaridad TEXT,
    correo_personal TEXT,
    correo_institucional TEXT,
    actitud_psicofisica TEXT,
    porcentaje_discapacidad NUMERIC(5,2),
    usuario_ingreso TEXT,
    nivel_unidad TEXT,
    unidad_usuario TEXT,
    fecha_creacion DATE DEFAULT CURRENT_DATE
);

CREATE INDEX IF NOT EXISTS idx_pn_cc ON personal_novedades(cc);
CREATE INDEX IF NOT EXISTS idx_pn_fecha_inicio ON personal_novedades(fecha_inicio_novedad);
CREATE INDEX IF NOT EXISTS idx_pn_nivel_unidad ON personal_novedades(nivel_unidad);
CREATE INDEX IF NOT EXISTS idx_pn_unidad_usuario ON personal_novedades(unidad_usuario);
CREATE INDEX IF NOT EXISTS idx_pn_fecha_creacion ON personal_novedades(fecha_creacion);
CREATE INDEX IF NOT EXISTS idx_pn_cc_fecha_reciente ON personal_novedades(cc, fecha_creacion DESC, id DESC) WHERE cc IS NOT NULL;

CREATE TABLE IF NOT EXISTS fotos_personal (
    id SERIAL PRIMARY KEY,
    id_personal_novedad INTEGER REFERENCES personal_novedades(id) ON DELETE CASCADE,
    ruta_foto VARCHAR(255) NOT NULL,
    fecha_subida TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fotos_personal_novedad ON fotos_personal(id_personal_novedad);

CREATE TABLE IF NOT EXISTS medallas (
    id SERIAL PRIMARY KEY,
    id_personal_novedad INTEGER REFERENCES personal_novedades(id) ON DELETE CASCADE,
    nombre VARCHAR(150) UNIQUE NOT NULL,
    fecha_adquisicion DATE,
    descripcion TEXT
);

CREATE INDEX IF NOT EXISTS idx_medallas_personal ON medallas(id_personal_novedad);

CREATE TABLE IF NOT EXISTS hijos_personal (
    id SERIAL PRIMARY KEY,
    id_personal_novedad INTEGER REFERENCES personal_novedades(id) ON DELETE CASCADE,
    nombre_completo VARCHAR(200) NOT NULL,
    fecha_nacimiento DATE NOT NULL,
    grado_estudio VARCHAR(100),
    edad INTEGER,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_hijos_personal_novedad ON hijos_personal(id_personal_novedad);
CREATE INDEX IF NOT EXISTS idx_hijos_personal_fecha ON hijos_personal(fecha_nacimiento);

-- ============================================================
-- USUARIOS Y SEGURIDAD
-- ============================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    id_personal_novedad INTEGER REFERENCES personal_novedades(id) ON DELETE SET NULL,
    usuario VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    foto VARCHAR(255),
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_usuario_login ON usuarios(usuario, activo);
CREATE INDEX IF NOT EXISTS idx_usuarios_personal_novedad ON usuarios(id_personal_novedad);

CREATE TABLE IF NOT EXISTS usuario_rol (
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    rol_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (usuario_id, rol_id)
);

CREATE TABLE IF NOT EXISTS rol_pagina (
    rol_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
    pagina_id INTEGER REFERENCES paginas(id) ON DELETE CASCADE,
    tiene_permiso BOOLEAN DEFAULT TRUE,
    puede_ver BOOLEAN DEFAULT TRUE,
    puede_crear BOOLEAN DEFAULT FALSE,
    puede_editar BOOLEAN DEFAULT FALSE,
    puede_eliminar BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (rol_id, pagina_id)
);

CREATE TABLE IF NOT EXISTS usuario_pagina (
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    pagina_id INTEGER REFERENCES paginas(id) ON DELETE CASCADE,
    tiene_permiso BOOLEAN DEFAULT TRUE,
    puede_ver BOOLEAN DEFAULT TRUE,
    puede_crear BOOLEAN DEFAULT FALSE,
    puede_editar BOOLEAN DEFAULT FALSE,
    puede_eliminar BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (usuario_id, pagina_id)
);

CREATE TABLE IF NOT EXISTS historial_accesos (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    pagina_id INTEGER REFERENCES paginas(id) ON DELETE CASCADE,
    fecha_acceso TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_usuario_rol_usuario ON usuario_rol(usuario_id);
CREATE INDEX IF NOT EXISTS idx_usuario_rol_rol ON usuario_rol(rol_id);
CREATE INDEX IF NOT EXISTS idx_rol_pagina_rol ON rol_pagina(rol_id);
CREATE INDEX IF NOT EXISTS idx_rol_pagina_pagina ON rol_pagina(pagina_id);
CREATE INDEX IF NOT EXISTS idx_usuario_pagina_usuario ON usuario_pagina(usuario_id);
CREATE INDEX IF NOT EXISTS idx_usuario_pagina_pagina ON usuario_pagina(pagina_id);
CREATE INDEX IF NOT EXISTS idx_historial_usuario ON historial_accesos(usuario_id);
CREATE INDEX IF NOT EXISTS idx_historial_pagina ON historial_accesos(pagina_id);
CREATE INDEX IF NOT EXISTS idx_historial_fecha ON historial_accesos(fecha_acceso);

-- ============================================================
-- MODULO DE AREAS
-- ============================================================

CREATE TABLE IF NOT EXISTS areas (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,
    descripcion TEXT
);

CREATE TABLE IF NOT EXISTS subareas (
    id SERIAL PRIMARY KEY,
    area_id INTEGER REFERENCES areas(id) ON DELETE CASCADE,
    nombre VARCHAR(100) UNIQUE NOT NULL,
    descripcion TEXT
);

CREATE INDEX IF NOT EXISTS idx_areas_nombre ON areas(nombre);
CREATE INDEX IF NOT EXISTS idx_subareas_area ON subareas(area_id);
CREATE INDEX IF NOT EXISTS idx_subareas_nombre ON subareas(nombre);

-- ============================================================
-- MODULO DE CURSOS
-- ============================================================

CREATE TABLE IF NOT EXISTS cursos_combate (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(150) UNIQUE NOT NULL,
    descripcion TEXT
);

CREATE TABLE IF NOT EXISTS personal_curso (
    id_personal_novedad INTEGER REFERENCES personal_novedades(id) ON DELETE CASCADE,
    curso_id INTEGER REFERENCES cursos_combate(id) ON DELETE CASCADE,
    fecha_inicio DATE,
    fecha_fin DATE,
    PRIMARY KEY (id_personal_novedad, curso_id)
);

CREATE INDEX IF NOT EXISTS idx_cursos_nombre ON cursos_combate(nombre);
CREATE INDEX IF NOT EXISTS idx_personal_curso_personal_novedad ON personal_curso(id_personal_novedad);
CREATE INDEX IF NOT EXISTS idx_personal_curso_curso ON personal_curso(curso_id);

-- ============================================================
-- MODULO DE ORDENES
-- ============================================================

CREATE TABLE IF NOT EXISTS ordenes (
    id SERIAL PRIMARY KEY,
    numero_orden VARCHAR(50) UNIQUE NOT NULL,
    descripcion TEXT,
    fecha_emision DATE,
    fecha_vencimiento DATE,
    CONSTRAINT chk_ordenes_fechas CHECK (
        fecha_vencimiento IS NULL
        OR fecha_emision IS NULL
        OR fecha_vencimiento >= fecha_emision
    )
);

CREATE TABLE IF NOT EXISTS actividades_orden (
    id SERIAL PRIMARY KEY,
    orden_id INTEGER REFERENCES ordenes(id) ON DELETE CASCADE,
    titulo VARCHAR(200),
    descripcion TEXT,
    fecha_inicio TIMESTAMP,
    fecha_fin TIMESTAMP,
    CONSTRAINT chk_actividades_orden_fechas CHECK (
        fecha_fin IS NULL
        OR fecha_inicio IS NULL
        OR fecha_fin >= fecha_inicio
    )
);

CREATE TABLE IF NOT EXISTS usuario_orden (
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    orden_id INTEGER REFERENCES ordenes(id) ON DELETE CASCADE,
    fecha_asignacion DATE,
    PRIMARY KEY (usuario_id, orden_id)
);

CREATE INDEX IF NOT EXISTS idx_ordenes_numero ON ordenes(numero_orden);
CREATE INDEX IF NOT EXISTS idx_ordenes_fecha_vencimiento ON ordenes(fecha_vencimiento);
CREATE INDEX IF NOT EXISTS idx_actividades_orden_orden ON actividades_orden(orden_id);
CREATE INDEX IF NOT EXISTS idx_actividades_orden_orden_fecha ON actividades_orden(orden_id, fecha_inicio);
CREATE INDEX IF NOT EXISTS idx_usuario_orden_usuario ON usuario_orden(usuario_id);
CREATE INDEX IF NOT EXISTS idx_usuario_orden_orden ON usuario_orden(orden_id);

-- ============================================================
-- MODULO DE PROYECTOS
-- ============================================================

CREATE TABLE IF NOT EXISTS proyectos (
    id SERIAL PRIMARY KEY,
    unidad VARCHAR(50) NOT NULL,
    numero_matricula VARCHAR(100) UNIQUE NOT NULL,
    titulo TEXT NOT NULL,
    titulo_corto VARCHAR(150) NOT NULL,
    investigador_principal VARCHAR(150) NOT NULL,
    fecha_inicio DATE,
    objetivo_general TEXT,
    id_area INTEGER REFERENCES areas(id) ON DELETE SET NULL,
    id_subarea INTEGER REFERENCES subareas(id) ON DELETE SET NULL,
    enfoque_investigativo TEXT,
    responsable_seguimiento VARCHAR(150),
    proyeto_matriculado BOOLEAN DEFAULT FALSE,
    proyecto_fase_formulacion BOOLEAN DEFAULT FALSE,
    otras_iniciativas BOOLEAN DEFAULT FALSE,
    trl INTEGER,
    tipo_proyecto VARCHAR(200),
    resumen TEXT,
    tiempo_ejecucion_meses INTEGER,
    presupuesto NUMERIC(15,2),
    identificacion_necesidad TEXT,
    identificacion_usuario_final TEXT,
    otro TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150),
    CONSTRAINT chk_proyectos_trl CHECK (trl IS NULL OR trl BETWEEN 1 AND 9),
    CONSTRAINT chk_proyectos_tiempo CHECK (tiempo_ejecucion_meses IS NULL OR tiempo_ejecucion_meses >= 0)

);
create table if not exists presupuesto_proyecto (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    presupuesto NUMERIC(15,2),
    fecha_presupuesto TIMESTAMP,
    documento_presupuesto TEXT,
    estado_documento_presupuesto VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists acta_cierre_proyecto (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    acta_cierre BOOLEAN DEFAULT FALSE,
    fecha_cierre TIMESTAMP,
    documento_acta_cierre TEXT,
    estado_documento_acta_cierre VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists informe_final_proyecto (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    informe_final BOOLEAN DEFAULT FALSE,
    fecha_informe TIMESTAMP,
    documento_informe TEXT,
    estado_documento_informe VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists procediemientos_corrspondientes (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    procediemientos_corrspondientes BOOLEAN DEFAULT FALSE,
    fecha_procedimientos TIMESTAMP,
    documento_procedimientos TEXT,
    estado_documento_procedimientos VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists manual_ensamblador (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    manual_ensamblador BOOLEAN DEFAULT FALSE,
    fecha_manual TIMESTAMP,
    documento_manual TEXT,
    estado_documento_manual VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists manual_usuario_final (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    manual_usuario_final BOOLEAN DEFAULT FALSE,
    fecha_manual TIMESTAMP,
    documento_manual TEXT,
    estado_documento_manual VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists encuesta_unidad_usuario_final (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    encuesta_unidad_usuario_final BOOLEAN DEFAULT FALSE,
    fecha_encuesta TIMESTAMP,
    documento_encuesta TEXT,
    estado_documento_encuesta VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists capacitacion_usuario_final (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    capacitacion_usuario_final BOOLEAN DEFAULT FALSE,
    fecha_capacitacion TIMESTAMP,
    documento_capacitacion TEXT,
    estado_documento_capacitacion VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists paquete_tecnico_proyecto (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    paquete_tecnico BOOLEAN DEFAULT FALSE,
    fecha_entrega TIMESTAMP,
    documento_paquete_tecnico TEXT,
    estado_documento_paquete_tecnico VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists documento_entrega_proyecto (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    documento_entrega TEXT,
    estado_documento_entrega VARCHAR(50),
    fecha_entrega TIMESTAMP,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists compromiso_confidencialidad_proyecto (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    compromiso_confidencialidad BOOLEAN DEFAULT FALSE,
    fecha_compromiso TIMESTAMP,
    documento_compromiso TEXT,
    estado_documento_compromiso VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists cesion_derechos_proyecto (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    cesion_derechos BOOLEAN DEFAULT FALSE,
    fecha_cesion TIMESTAMP,
    documento_cesion TEXT,
    estado_documento_cesion VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists seguimiento_proyecto_mensual (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    seguimiento BOOLEAN DEFAULT FALSE,
    fecha_seguimiento TIMESTAMP,
    documento_seguimiento TEXT,
    estado_documento_seguimiento VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists control_cambios_proyecto (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    control_cambios BOOLEAN DEFAULT FALSE,
    fecha_control_cambios TIMESTAMP,
    documento_control_cambios TEXT,
    estado_documento_control_cambios VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists elaboracion_formato_leciones_aprendidas (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    formato_lecciones_aprendidas BOOLEAN DEFAULT FALSE,
    fecha_formato_lecciones_aprendidas TIMESTAMP,
    documento_formato_lecciones_aprendidas TEXT,
    estado_documento_formato_lecciones_aprendidas VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists pruebas_entorno_real_trl6 (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    pruebas_entorno_real BOOLEAN DEFAULT FALSE,
    fecha_pruebas_entorno_real TIMESTAMP,
    documento_pruebas_entorno_real TEXT,
    estado_documento_pruebas_entorno_real VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists pruebas_entorno_cercano_real_trl5 (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    pruebas_entorno_cercano_real BOOLEAN DEFAULT FALSE,
    fecha_pruebas_entorno_cercano_real TIMESTAMP,
    documento_pruebas_entorno_cercano_real TEXT,
    estado_documento_pruebas_entorno_cercano_real VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists pruebas_entorno_controlado_trl5 (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    pruebas_entorno_controlado BOOLEAN DEFAULT FALSE,
    fecha_pruebas_entorno_controlado TIMESTAMP,
    documento_pruebas_entorno_controlado TEXT,
    estado_documento_pruebas_entorno_controlado VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists pruebas_laboratorio_componetes_trl4 (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    pruebas_laboratorio BOOLEAN DEFAULT FALSE,
    fecha_pruebas_laboratorio TIMESTAMP,
    documento_pruebas_laboratorio TEXT,
    estado_documento_pruebas_laboratorio VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists pruebas_laboratorio_informe_analisis_trl3 (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    pruebas_laboratorio BOOLEAN DEFAULT FALSE,
    fecha_pruebas_laboratorio TIMESTAMP,
    documento_pruebas_laboratorio TEXT,
    estado_documento_pruebas_laboratorio VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists definicion_tecnica_solucion_trl2 (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    definicion_tecnica BOOLEAN DEFAULT FALSE,
    fecha_definicion TIMESTAMP,
    documento_definicion TEXT,
    estado_documento_definicion VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists acta_validacion_proyecto (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    acta_validacion BOOLEAN DEFAULT FALSE,
    fecha_validacion TIMESTAMP,
    documento_acta_validacion TEXT,
    estado_documento_acta_validacion VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists acta_inicio_proyecto (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    acta_inicio BOOLEAN DEFAULT FALSE,
    fecha_inicio TIMESTAMP,
    documento_acta_inicio TEXT,
    estado_documento_acta_inicio VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);
create table if not exists formato_formulacion_proyecto (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    formato_entregado BOOLEAN DEFAULT FALSE,
    fecha_entrega TIMESTAMP,
    documento_formato TEXT,
    estado_documento_formato VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    unidad_usuario_final VARCHAR(150)
);

CREATE TABLE IF NOT EXISTS actividades_proyecto (
    id SERIAL PRIMARY KEY,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    actividad TEXT,
    descripcion TEXT,
    fecha_inicio TIMESTAMP,
    fecha_fin TIMESTAMP,
    estado VARCHAR(50),
    documento_entrega TEXT,
    estado_documento_entrega VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    CONSTRAINT chk_actividades_proyecto_fechas CHECK (
        fecha_fin IS NULL
        OR fecha_inicio IS NULL
        OR fecha_fin >= fecha_inicio
    )
);

CREATE TABLE IF NOT EXISTS usuario_proyecto (
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    proyecto_id INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    fecha_asignacion DATE,
    PRIMARY KEY (usuario_id, proyecto_id)
);

CREATE INDEX IF NOT EXISTS idx_proyectos_numero_matricula ON proyectos(numero_matricula);
CREATE INDEX IF NOT EXISTS idx_proyectos_titulo_corto ON proyectos(titulo_corto);
CREATE INDEX IF NOT EXISTS idx_proyectos_area ON proyectos(id_area);
CREATE INDEX IF NOT EXISTS idx_proyectos_subarea ON proyectos(id_subarea);
CREATE INDEX IF NOT EXISTS idx_proyectos_trl ON proyectos(trl);
CREATE INDEX IF NOT EXISTS idx_proyectos_creado_en ON proyectos(creado_en);
CREATE INDEX IF NOT EXISTS idx_actividades_proyecto_proyecto ON actividades_proyecto(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_actividades_proyecto_proyecto_estado ON actividades_proyecto(proyecto_id, estado);
CREATE INDEX IF NOT EXISTS idx_usuario_proyecto_usuario ON usuario_proyecto(usuario_id);
CREATE INDEX IF NOT EXISTS idx_usuario_proyecto_proyecto ON usuario_proyecto(proyecto_id);

CREATE TABLE IF NOT EXISTS tabla_trl (
    id SERIAL PRIMARY KEY,
    id_proyecto INTEGER REFERENCES proyectos(id) ON DELETE CASCADE,
    trl INTEGER NOT NULL,
    numero_orden INTEGER,
    pregunta_trl TEXT,
    cumple_trl BOOLEAN DEFAULT FALSE,
    documento_evidencia TEXT,
    observaciones TEXT,
    estado_docuemento_entrega VARCHAR(50),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_creacion VARCHAR(150),
    CONSTRAINT chk_tabla_trl_valor CHECK (trl BETWEEN 1 AND 9)
);

CREATE INDEX IF NOT EXISTS idx_tabla_trl_proyecto ON tabla_trl(id_proyecto);
CREATE INDEX IF NOT EXISTS idx_tabla_trl_numero_orden ON tabla_trl(numero_orden);
CREATE INDEX IF NOT EXISTS idx_tabla_trl_proyecto_trl_orden ON tabla_trl(id_proyecto, trl, numero_orden);
CREATE INDEX IF NOT EXISTS idx_presupuesto_proyecto_proyecto ON presupuesto_proyecto(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_acta_cierre_proyecto_proyecto ON acta_cierre_proyecto(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_informe_final_proyecto_proyecto ON informe_final_proyecto(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_procediemientos_corrspondientes_proyecto ON procediemientos_corrspondientes(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_manual_ensamblador_proyecto ON manual_ensamblador(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_manual_usuario_final_proyecto ON manual_usuario_final(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_encuesta_uuf_proyecto ON encuesta_unidad_usuario_final(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_capacitacion_uuf_proyecto ON capacitacion_usuario_final(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_paquete_tecnico_proyecto ON paquete_tecnico_proyecto(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_documento_entrega_proyecto_proyecto ON documento_entrega_proyecto(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_compromiso_confidencialidad_proyecto ON compromiso_confidencialidad_proyecto(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_cesion_derechos_proyecto ON cesion_derechos_proyecto(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_seguimiento_proyecto_mensual_proyecto ON seguimiento_proyecto_mensual(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_control_cambios_proyecto_proyecto ON control_cambios_proyecto(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_lecciones_aprendidas_proyecto ON elaboracion_formato_leciones_aprendidas(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_pruebas_entorno_real_trl6_proyecto ON pruebas_entorno_real_trl6(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_pruebas_entorno_cercano_real_trl5_proyecto ON pruebas_entorno_cercano_real_trl5(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_pruebas_entorno_controlado_trl5_proyecto ON pruebas_entorno_controlado_trl5(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_pruebas_laboratorio_componetes_trl4_proyecto ON pruebas_laboratorio_componetes_trl4(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_pruebas_laboratorio_informe_analisis_trl3_proyecto ON pruebas_laboratorio_informe_analisis_trl3(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_definicion_tecnica_solucion_trl2_proyecto ON definicion_tecnica_solucion_trl2(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_acta_validacion_proyecto_proyecto ON acta_validacion_proyecto(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_acta_inicio_proyecto_proyecto ON acta_inicio_proyecto(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_formato_formulacion_proyecto_proyecto ON formato_formulacion_proyecto(proyecto_id);
-- ============================================================
-- MODULOS INDEPENDIENTES
-- ============================================================

CREATE TABLE IF NOT EXISTS calendario (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(200) NOT NULL,
    descripcion TEXT,
    fecha_inicio TIMESTAMP,
    fecha_fin TIMESTAMP,
    CONSTRAINT chk_calendario_fechas CHECK (
        fecha_fin IS NULL
        OR fecha_inicio IS NULL
        OR fecha_fin >= fecha_inicio
    )
);

CREATE INDEX IF NOT EXISTS idx_calendario_inicio ON calendario(fecha_inicio);
CREATE INDEX IF NOT EXISTS idx_calendario_fin ON calendario(fecha_fin);

create table if not exists chat (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    mensaje TEXT NOT NULL,
    fecha_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_usuario_fecha_envio ON chat(usuario_id, fecha_envio DESC);
create table if not exists foro (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    titulo VARCHAR(200) NOT NULL,
    mensaje TEXT NOT NULL,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_foro_usuario_fecha_creacion ON foro(usuario_id, fecha_creacion DESC);
create table if not exists respuesta_foro (
    id SERIAL PRIMARY KEY,
    foro_id INTEGER REFERENCES foro(id) ON DELETE CASCADE,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    mensaje TEXT NOT NULL,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
); 
CREATE INDEX IF NOT EXISTS idx_respuesta_foro_foro_fecha ON respuesta_foro(foro_id, fecha_creacion DESC);
create table if not exists carperta_documentos_matriz (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    ruta text NOT NULL,
    descripcion TEXT,
    estado boolean DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE IF EXISTS carperta_documentos_matriz
ADD COLUMN IF NOT EXISTS estado boolean DEFAULT TRUE;
UPDATE carperta_documentos_matriz
SET estado = TRUE
WHERE estado IS NULL;
CREATE INDEX IF NOT EXISTS idx_carperta_documentos_matriz_nombre ON carperta_documentos_matriz(nombre);
CREATE INDEX IF NOT EXISTS idx_carperta_documentos_matriz_estado ON carperta_documentos_matriz(estado);
create table if not exists documento_carpeta_proyecto (
    id SERIAL PRIMARY KEY,
    carpeta_id INTEGER REFERENCES carperta_documentos_matriz(id) ON DELETE CASCADE,
    nombre VARCHAR(150) NOT NULL,
    ruta text NOT NULL,
    descripcion TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_documento_carpeta_proyecto_carpeta ON documento_carpeta_proyecto(carpeta_id);
create table if not exists carpeta_documentos_proyecto (
    id SERIAL PRIMARY KEY,
    carpeta_id INTEGER REFERENCES documento_carpeta_proyecto(id) ON DELETE CASCADE,
    nombre VARCHAR(150) NOT NULL,
    ruta text NOT NULL,
    descripcion TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_carpeta_documentos_proyecto_carpeta ON carpeta_documentos_proyecto(carpeta_id);


-- ============================================================
-- VISTAS
-- ============================================================

CREATE OR REPLACE VIEW vw_personal_novedad_actual AS
SELECT DISTINCT ON (pn.cc)
    pn.id,
    pn.cc,
    g.nombre AS grado,
    pn.apellidos_nombres,
    pn.correo_personal,
    pn.correo_institucional,
    pn.nivel_unidad,
    pn.unidad_usuario,
    pn.fecha_creacion
FROM personal_novedades pn
LEFT JOIN grados g ON g.id = pn.id_grado
WHERE pn.cc IS NOT NULL
ORDER BY pn.cc, pn.fecha_creacion DESC, pn.id DESC;

CREATE OR REPLACE VIEW vw_usuarios_detalle AS
SELECT
    u.id,
    u.usuario,
    u.foto,
    u.activo,
    u.creado_en,
    pn.id AS id_personal_novedad,
    pn.cc,
    pn.apellidos_nombres AS nombre_completo,
    COALESCE(pn.correo_institucional, pn.correo_personal) AS correo,
    g.nombre AS grado,
    pn.nivel_unidad,
    pn.unidad_usuario
FROM usuarios u
LEFT JOIN personal_novedades pn ON pn.id = u.id_personal_novedad
LEFT JOIN grados g ON g.id = pn.id_grado;

CREATE OR REPLACE VIEW vw_proyectos_resumen AS
SELECT
    p.id,
    p.numero_matricula,
    p.titulo_corto,
    p.investigador_principal,
    p.trl,
    p.proyeto_matriculado,
    p.proyecto_fase_formulacion,
    p.otras_iniciativas,
    p.creado_en,
    a.nombre AS area,
    s.nombre AS subarea,
    COUNT(DISTINCT ap.id) AS total_actividades,
    COUNT(DISTINCT up.usuario_id) AS total_responsables,
    COUNT(DISTINCT tt.id) FILTER (WHERE tt.cumple_trl) AS total_trl_cumplidos,
    COUNT(DISTINCT tt.id) AS total_trl_registros
FROM proyectos p
LEFT JOIN areas a ON a.id = p.id_area
LEFT JOIN subareas s ON s.id = p.id_subarea
LEFT JOIN actividades_proyecto ap ON ap.proyecto_id = p.id
LEFT JOIN usuario_proyecto up ON up.proyecto_id = p.id
LEFT JOIN tabla_trl tt ON tt.id_proyecto = p.id
GROUP BY
    p.id,
    p.numero_matricula,
    p.titulo_corto,
    p.investigador_principal,
    p.trl,
    p.proyeto_matriculado,
    p.proyecto_fase_formulacion,
    p.otras_iniciativas,
    p.creado_en,
    a.nombre,
    s.nombre;

CREATE OR REPLACE VIEW vw_permisos_usuario AS
SELECT
    u.id AS usuario_id,
    p.id AS pagina_id,
    p.nombre AS pagina,
    p.ruta,
    COALESCE(MAX(up.tiene_permiso::INT), MAX(rp.tiene_permiso::INT), 0)::BOOLEAN AS tiene_permiso,
    COALESCE(MAX(up.puede_ver::INT), MAX(rp.puede_ver::INT), 0)::BOOLEAN AS puede_ver,
    COALESCE(MAX(up.puede_crear::INT), MAX(rp.puede_crear::INT), 0)::BOOLEAN AS puede_crear,
    COALESCE(MAX(up.puede_editar::INT), MAX(rp.puede_editar::INT), 0)::BOOLEAN AS puede_editar,
    COALESCE(MAX(up.puede_eliminar::INT), MAX(rp.puede_eliminar::INT), 0)::BOOLEAN AS puede_eliminar
FROM usuarios u
CROSS JOIN paginas p
LEFT JOIN usuario_pagina up
    ON up.usuario_id = u.id
   AND up.pagina_id = p.id
LEFT JOIN usuario_rol ur
    ON ur.usuario_id = u.id
LEFT JOIN rol_pagina rp
    ON rp.rol_id = ur.rol_id
   AND rp.pagina_id = p.id
GROUP BY u.id, p.id, p.nombre, p.ruta;

-- ============================================================
-- FUNCIONES
-- ============================================================

CREATE OR REPLACE FUNCTION validar_rango_fechas()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_fecha_inicio TIMESTAMP;
    v_fecha_fin TIMESTAMP;
BEGIN
    v_fecha_inicio := NULLIF(to_jsonb(NEW) ->> TG_ARGV[0], '')::TIMESTAMP;
    v_fecha_fin := NULLIF(to_jsonb(NEW) ->> TG_ARGV[1], '')::TIMESTAMP;

    IF v_fecha_inicio IS NOT NULL
       AND v_fecha_fin IS NOT NULL
       AND v_fecha_fin < v_fecha_inicio THEN
        RAISE EXCEPTION 'La fecha final no puede ser menor a la fecha inicial en %', TG_TABLE_NAME;
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION calcular_edad_hijo()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.edad := EXTRACT(YEAR FROM AGE(CURRENT_DATE, NEW.fecha_nacimiento))::INTEGER;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validar_subarea_proyecto()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_area_id INTEGER;
BEGIN
    IF NEW.id_subarea IS NULL OR NEW.id_area IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT area_id
    INTO v_area_id
    FROM subareas
    WHERE id = NEW.id_subarea;

    IF v_area_id IS NULL THEN
        RAISE EXCEPTION 'La subarea % no existe', NEW.id_subarea;
    END IF;

    IF v_area_id <> NEW.id_area THEN
        RAISE EXCEPTION 'La subarea % no pertenece al area %', NEW.id_subarea, NEW.id_area;
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION crear_usuario_desde_personal(
    p_cc BIGINT,
    p_usuario VARCHAR(100),
    p_password_hash TEXT,
    p_rol_id INTEGER,
    p_activo BOOLEAN DEFAULT TRUE
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_personal RECORD;
    v_usuario_id INTEGER;
BEGIN
    SELECT *
    INTO v_personal
    FROM vw_personal_novedad_actual
    WHERE cc = p_cc;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'No existe personal_novedades para la cedula %', p_cc;
    END IF;

    IF v_personal.apellidos_nombres IS NULL OR TRIM(v_personal.apellidos_nombres) = '' THEN
        RAISE EXCEPTION 'La cedula % no tiene nombre en personal_novedades', p_cc;
    END IF;

    IF COALESCE(v_personal.correo_institucional, v_personal.correo_personal) IS NULL THEN
        RAISE EXCEPTION 'La cedula % no tiene correo en personal_novedades', p_cc;
    END IF;

    INSERT INTO usuarios (
        id_personal_novedad,
        usuario,
        password_hash,
        activo
    )
    VALUES (
        v_personal.id,
        p_usuario,
        p_password_hash,
        p_activo
    )
    ON CONFLICT (usuario) DO UPDATE
    SET
        id_personal_novedad = EXCLUDED.id_personal_novedad,
        activo = EXCLUDED.activo
    RETURNING id INTO v_usuario_id;

    INSERT INTO usuario_rol (usuario_id, rol_id)
    VALUES (v_usuario_id, p_rol_id)
    ON CONFLICT DO NOTHING;

    RETURN v_usuario_id;
END;
$$;

DROP TRIGGER IF EXISTS trg_hijos_personal_calcular_edad ON hijos_personal;
CREATE TRIGGER trg_hijos_personal_calcular_edad
BEFORE INSERT OR UPDATE OF fecha_nacimiento
ON hijos_personal
FOR EACH ROW
EXECUTE FUNCTION calcular_edad_hijo();

DROP TRIGGER IF EXISTS trg_ordenes_validar_fechas ON ordenes;
CREATE TRIGGER trg_ordenes_validar_fechas
BEFORE INSERT OR UPDATE OF fecha_emision, fecha_vencimiento
ON ordenes
FOR EACH ROW
EXECUTE FUNCTION validar_rango_fechas('fecha_emision', 'fecha_vencimiento');

DROP TRIGGER IF EXISTS trg_actividades_orden_validar_fechas ON actividades_orden;
CREATE TRIGGER trg_actividades_orden_validar_fechas
BEFORE INSERT OR UPDATE OF fecha_inicio, fecha_fin
ON actividades_orden
FOR EACH ROW
EXECUTE FUNCTION validar_rango_fechas('fecha_inicio', 'fecha_fin');

DROP TRIGGER IF EXISTS trg_actividades_proyecto_validar_fechas ON actividades_proyecto;
CREATE TRIGGER trg_actividades_proyecto_validar_fechas
BEFORE INSERT OR UPDATE OF fecha_inicio, fecha_fin
ON actividades_proyecto
FOR EACH ROW
EXECUTE FUNCTION validar_rango_fechas('fecha_inicio', 'fecha_fin');

DROP TRIGGER IF EXISTS trg_calendario_validar_fechas ON calendario;
CREATE TRIGGER trg_calendario_validar_fechas
BEFORE INSERT OR UPDATE OF fecha_inicio, fecha_fin
ON calendario
FOR EACH ROW
EXECUTE FUNCTION validar_rango_fechas('fecha_inicio', 'fecha_fin');

DROP TRIGGER IF EXISTS trg_proyectos_validar_subarea ON proyectos;
CREATE TRIGGER trg_proyectos_validar_subarea
BEFORE INSERT OR UPDATE OF id_area, id_subarea
ON proyectos
FOR EACH ROW
EXECUTE FUNCTION validar_subarea_proyecto();

-- ============================================================
-- DATOS INICIALES
-- ============================================================

INSERT INTO unidades (nivel, sigla, nombre)
VALUES ('EJC', 'EJC', 'Ejercito Nacional')
ON CONFLICT (sigla) DO NOTHING;

INSERT INTO usuarios (usuario, password_hash)
VALUES (
    'admin',
    '$2b$12$FE15whjzDoCcoroKuhSi6.gyayl6sXAjEr8rxTmqNckuijIk1N4vi'
)
ON CONFLICT (usuario) DO NOTHING;

INSERT INTO usuario_rol (usuario_id, rol_id)
SELECT u.id, r.id
FROM usuarios u
CROSS JOIN roles r
WHERE u.usuario = 'admin'
  AND r.nombre = 'SUPER'
ON CONFLICT DO NOTHING;

INSERT INTO rol_pagina (rol_id, pagina_id, tiene_permiso, puede_ver, puede_crear, puede_editar, puede_eliminar)
SELECT r.id, p.id, TRUE, TRUE, TRUE, TRUE, TRUE
FROM roles r
CROSS JOIN paginas p
WHERE r.nombre = 'SUPER'
ON CONFLICT DO NOTHING;

SET client_min_messages TO NOTICE;
