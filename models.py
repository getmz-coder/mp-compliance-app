import sqlite3
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from werkzeug.security import generate_password_hash

TZ_COL = ZoneInfo('America/Bogota')

import config


def get_db():
    """Retorna conexión con row_factory y foreign keys activos."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Crea todas las tablas si no existen."""
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS catalogo_motivos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo      VARCHAR(10),
            descripcion VARCHAR(200),
            activo      BOOLEAN DEFAULT TRUE,
            orden       INTEGER
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        VARCHAR(50) UNIQUE,
            password_hash   VARCHAR(256),
            nombre_completo VARCHAR(100),
            rol             VARCHAR(20),
            activo          BOOLEAN DEFAULT TRUE,
            created_at      DATETIME
        );

        CREATE TABLE IF NOT EXISTS equipos (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            consecutivo        INTEGER,
            vehiculo           VARCHAR(30),
            categoria          VARCHAR(50),
            estado_vehiculo    VARCHAR(20),
            linea_vehiculo     TEXT,
            familia            VARCHAR(100),
            rutina             TEXT,
            desviacion         TEXT,
            ind_desviacion     INTEGER,
            estado_mp          VARCHAR(50),
            fecha_programacion DATETIME,
            justificacion      TEXT,
            observaciones      TEXT,
            observaciones_2    TEXT,
            sync_id            INTEGER,
            sync_timestamp     DATETIME
        );

        CREATE TABLE IF NOT EXISTS filtros_equipo (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo          VARCHAR(30),
            tipo            VARCHAR(50),
            nombre_articulo VARCHAR(200),
            codigo_sap      VARCHAR(30),
            tipo_filtro     VARCHAR(50)
        );

        CREATE TABLE IF NOT EXISTS homologos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo       INTEGER,
            codigo_sap  VARCHAR(30),
            descripcion VARCHAR(200),
            estado      VARCHAR(50)
        );

        CREATE TABLE IF NOT EXISTS promedios_familia (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            familia            VARCHAR(100) UNIQUE,
            horas_promedio_dia FLOAT,
            km_promedio_dia    FLOAT,
            actualizado_por    INTEGER REFERENCES usuarios(id),
            timestamp          DATETIME
        );

        CREATE TABLE IF NOT EXISTS frecuencias_rutinas (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            rutina             VARCHAR(200),
            frecuencia_medidor INTEGER,
            frecuencia_dias    INTEGER
        );

        CREATE TABLE IF NOT EXISTS solicitudes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo_id       INTEGER REFERENCES equipos(id),
            solicitado_por  INTEGER REFERENCES usuarios(id),
            fecha_solicitud DATETIME,
            sync_id         INTEGER,
            estado          VARCHAR(20) DEFAULT 'pendiente'
        );

        CREATE TABLE IF NOT EXISTS respuestas (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            solicitud_id    INTEGER REFERENCES solicitudes(id),
            respondido_por  INTEGER REFERENCES usuarios(id),
            accion          VARCHAR(20),
            motivo_id       INTEGER REFERENCES catalogo_motivos(id),
            comentario_libre TEXT,
            timestamp       DATETIME,
            ip_address      VARCHAR(45)
        );

        CREATE TABLE IF NOT EXISTS log_actividad (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id  INTEGER REFERENCES usuarios(id),
            accion_tipo VARCHAR(30),
            detalle     TEXT,
            ip_address  VARCHAR(45),
            timestamp   DATETIME
        );

        CREATE TABLE IF NOT EXISTS sugerencias_filtros (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo        VARCHAR(30),
            filtro_id       INTEGER REFERENCES filtros_equipo(id),
            usuario_id      INTEGER REFERENCES usuarios(id),
            descripcion     TEXT,
            estado          VARCHAR(20) DEFAULT 'pendiente',
            respuesta_admin TEXT,
            timestamp       DATETIME
        );

        CREATE TABLE IF NOT EXISTS ejecuciones_no_reportadas (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo                VARCHAR(30),
            familia                 VARCHAR(100),
            rutina                  TEXT,
            ind_desviacion_anterior INTEGER,
            ind_desviacion_nuevo    INTEGER,
            sync_id_anterior        INTEGER,
            sync_id_nuevo           INTEGER,
            estado                  VARCHAR(20) DEFAULT 'pendiente',
            justificacion           TEXT,
            registrado_por          INTEGER REFERENCES usuarios(id),
            timestamp               DATETIME
        );

        CREATE TABLE IF NOT EXISTS historial_cambios_filtros (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo                VARCHAR(30),
            tipo_cambio             VARCHAR(20),
            filtro_anterior_tipo    VARCHAR(50),
            filtro_anterior_nombre  VARCHAR(200),
            filtro_anterior_sap     VARCHAR(30),
            filtro_nuevo_tipo       VARCHAR(50),
            filtro_nuevo_nombre     VARCHAR(200),
            filtro_nuevo_sap        VARCHAR(30),
            sugerencia_id           INTEGER REFERENCES sugerencias_filtros(id),
            solicitado_por          INTEGER REFERENCES usuarios(id),
            autorizado_por          INTEGER REFERENCES usuarios(id),
            timestamp               DATETIME
        );
    """)

    _migrate_equipos(conn)
    _migrate_respuestas(conn)
    _migrate_planeacion(conn)

    conn.commit()
    conn.close()


def _migrate_equipos(conn):
    """Agrega columnas nuevas a tabla equipos en DBs ya existentes."""
    cur = conn.cursor()
    existing = {row[1] for row in cur.execute("PRAGMA table_info(equipos)")}
    nuevas = {
        'linea_vehiculo': 'TEXT',
        'justificacion':  'TEXT',
        'observaciones':  'TEXT',
        'observaciones_2': 'TEXT',
    }
    for col, coltype in nuevas.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE equipos ADD COLUMN {col} {coltype}")


def _migrate_planeacion(conn):
    """Crea tablas de planeación en DBs existentes si no existen."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS promedios_familia (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            familia            VARCHAR(100) UNIQUE,
            horas_promedio_dia FLOAT,
            km_promedio_dia    FLOAT,
            actualizado_por    INTEGER REFERENCES usuarios(id),
            timestamp          DATETIME
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS frecuencias_rutinas (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            rutina             VARCHAR(200),
            frecuencia_medidor INTEGER,
            frecuencia_dias    INTEGER
        )
    """)


def _migrate_respuestas(conn):
    """Agrega columnas de verificación a tabla respuestas en DBs ya existentes."""
    cur = conn.cursor()
    existing = {row[1] for row in cur.execute("PRAGMA table_info(respuestas)")}
    nuevas = {
        'verificacion':       'VARCHAR(20)',
        'ind_desv_anterior':  'INTEGER',
        'ind_desv_posterior': 'INTEGER',
    }
    for col, coltype in nuevas.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE respuestas ADD COLUMN {col} {coltype}")


def seed_motivos():
    """Inserta los motivos iniciales si aún no existen."""
    conn = get_db()
    cur = conn.cursor()

    for motivo in config.CATALOGO_MOTIVOS_INICIAL:
        existe = cur.execute(
            "SELECT 1 FROM catalogo_motivos WHERE codigo = ?",
            (motivo['codigo'],)
        ).fetchone()
        if not existe:
            cur.execute(
                "INSERT INTO catalogo_motivos (codigo, descripcion, activo, orden) VALUES (?, ?, 1, ?)",
                (motivo['codigo'], motivo['descripcion'], motivo['orden'])
            )

    conn.commit()
    conn.close()


def create_user(username, password, nombre, rol):
    """Crea un usuario con password hasheado. Retorna el id insertado o None si ya existe."""
    conn = get_db()
    cur = conn.cursor()

    existe = cur.execute(
        "SELECT 1 FROM usuarios WHERE username = ?", (username,)
    ).fetchone()

    if existe:
        conn.close()
        return None

    password_hash = generate_password_hash(password)
    cur.execute(
        """INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo, created_at)
           VALUES (?, ?, ?, ?, 1, ?)""",
        (username, password_hash, nombre, rol, datetime.now(TZ_COL).isoformat())
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


if __name__ == '__main__':
    print("Inicializando base de datos...")
    init_db()
    print("  Tablas creadas.")

    seed_motivos()
    print("  Catálogo de motivos cargado.")

    # IMPORTANTE: cambia estas contraseñas desde el panel de Usuarios antes de ir a producción.
    uid = create_user('admin', 'admin123', 'Administrador Planeación', 'admin')
    print(f"  Usuario admin {'creado (id={})'.format(uid) if uid else 'ya existía'}.")

    uid = create_user('cio_bog', 'cio123', 'CIO BOG', 'cio')
    print(f"  Usuario cio_bog {'creado (id={})'.format(uid) if uid else 'ya existía'}.")

    uid = create_user('tecnico_bog', 'tec123', 'Técnico-Almacén BOG', 'tecnico')
    print(f"  Usuario tecnico_bog {'creado (id={})'.format(uid) if uid else 'ya existía'}.")

    uid = create_user('mz13', 'Mzaba*13', 'Super Admin GET', 'superadmin')
    print(f"  Usuario mz13 {'creado (id={})'.format(uid) if uid else 'ya existía'}.")

    print("Listo.")
