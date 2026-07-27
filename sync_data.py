"""ETL: sincronización de datos desde archivos Excel hacia SQLite.

v2 — Ciclo diario:
  Si el último sync fue hace >= 20 hr, se hace CORTE DIARIO al inicio del nuevo:
    - Solicitudes pendientes sin respuesta → estado='sin_respuesta'
    - Ejecuciones no reportadas pendientes → estado='cerrado_ciclo'
    - Se registra el corte en tabla ciclos_diarios
  Ejecuciones no reportadas ahora se etiquetan con tipo_categoria (motorizado / no_motorizado)
  según la categoría del vehículo en el maestro.
"""
import logging
import re
import unicodedata
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_COL = ZoneInfo('America/Bogota')

from models import get_db


COLS_PROGRAMACION_REQUERIDAS = ['consecutivo', 'vehiculo', 'rutina', 'estado_mp']

COLS_FILTROS = ['EQUIPO', 'TIPO', 'NOMBRE ARTÍCULO', 'CODIGO SAP', 'TIPO FILTRO']

COLS_HOMOLOGOS = ['Grupo', 'Estado', 'Codigo SAP', 'Descripcion']

COLS_FRECUENCIAS = ['rutina', 'frecuencia_medidor', 'frecuencia_dias']

# Umbral (en horas) para disparar el corte diario del ciclo de planeación.
HORAS_CORTE_DIARIO = 20

# Sinónimos para normalización de cabeceras
_COL_SYNONYMS = {
    'descripcion': 'nombre',
    'articulo': 'nombre',
    'nombre_articulo': 'nombre',
    'locacion': 'ubicacion',
    'ubicacion_almacen': 'ubicacion',
    'codigo_sap': 'codigo_sap',
    'sap': 'codigo_sap',
    'frecuencia_medidor': 'frecuencia_medidor',
    'frecuencia_dias': 'frecuencia_dias',
    'indice_desviacion': 'ind_desviacion',
    'ind_desviacion': 'ind_desviacion',
    'desv_medidor': 'desv_medidor',
    'desviacion_medidor': 'desv_medidor',
    'desv_tiempo': 'desv_tiempo',
    'desviacion_tiempo': 'desv_tiempo',
}


def _normalize_col_name(name):
    """Normaliza nombre de columna: strip, lower, sin tildes, espacios→_, sinónimos."""
    s = str(name).strip()
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn')
    s = s.lower().replace(' ', '_')
    return _COL_SYNONYMS.get(s, s)


def _normalize_columns(df):
    """Normaliza todas las cabeceras de un DataFrame."""
    df.columns = [_normalize_col_name(c) for c in df.columns]
    return df


def clasificar_rutina(nombre_rutina, frecuencia_medidor=None, frecuencia_dias=None):
    """Clasifica una rutina como 'principal' o 'verificacion'."""
    nombre_upper = (nombre_rutina or '').upper()
    if 'PRUEBA DE SERVICIO' in nombre_upper:
        return 'verificacion'
    if 'PRUEBA' in nombre_upper and 'SERVICIO' in nombre_upper:
        return 'verificacion'
    try:
        fm = float(frecuencia_medidor) if frecuencia_medidor else None
        fd = float(frecuencia_dias) if frecuencia_dias else None
        if fm and fm <= 200 and (not fd or fd < 30):
            return 'verificacion'
    except (ValueError, TypeError):
        pass
    return 'principal'


def _clean(val):
    """Convierte NaN/NaT/None/vacíos a None; hace strip al resto."""
    if val is None:
        return None
    s = str(val).strip()
    return None if s.lower() in ('nan', 'nat', 'none', '') else s


def _get_col(row, *names):
    """Retorna el primer valor no-None de la fila para los nombres dados."""
    for name in names:
        if name in row.index:
            v = _clean(row[name])
            if v is not None:
                return v
    return None


def _es_no_motorizado(categoria):
    """
    Determina si una categoría de vehículo corresponde a 'no motorizado'.
    Case-insensitive, tolerante a variaciones de espacios/tildes.
    """
    if not categoria:
        return False
    return 'no motoriz' in categoria.lower().strip()


def _tipo_categoria_from(categoria):
    """Retorna 'no_motorizado' o 'motorizado' según la categoría de equipos."""
    return 'no_motorizado' if _es_no_motorizado(categoria) else 'motorizado'


def _aplicar_corte_diario(cur, sync_id, ahora):
    """
    Cierra el ciclo del día anterior si aplica.

    Retorna dict con contadores:
      {'aplicado': bool, 'solicitudes_cerradas': int,
       'ejec_motor_cerradas': int, 'ejec_no_motor_cerradas': int,
       'horas_transcurridas': float | None}
    """
    resultado = {
        'aplicado': False,
        'solicitudes_cerradas': 0,
        'ejec_motor_cerradas': 0,
        'ejec_no_motor_cerradas': 0,
        'horas_transcurridas': None,
    }

    # Última fecha de sync registrada
    last_ts_row = cur.execute(
        "SELECT MAX(sync_timestamp) AS ts FROM equipos WHERE sync_timestamp IS NOT NULL"
    ).fetchone()
    if not last_ts_row or not last_ts_row['ts']:
        return resultado

    try:
        last_dt = datetime.fromisoformat(last_ts_row['ts'])
    except (ValueError, TypeError):
        return resultado

    horas = (ahora - last_dt).total_seconds() / 3600.0
    resultado['horas_transcurridas'] = horas

    if horas < HORAS_CORTE_DIARIO:
        return resultado

    # 1. Cerrar solicitudes pendientes SIN respuesta como 'sin_respuesta'
    cur.execute(
        """UPDATE solicitudes
           SET estado = 'sin_respuesta'
           WHERE estado = 'pendiente'
             AND id NOT IN (
                 SELECT solicitud_id FROM respuestas
                 WHERE solicitud_id IS NOT NULL
             )"""
    )
    resultado['solicitudes_cerradas'] = cur.rowcount

    # 2. Cerrar ejecuciones no reportadas pendientes → 'cerrado_ciclo'
    #    Separado por tipo_categoria para poder contar cada uno
    cur.execute(
        """UPDATE ejecuciones_no_reportadas
           SET estado = 'cerrado_ciclo'
           WHERE estado = 'pendiente'
             AND tipo_categoria = 'motorizado'"""
    )
    resultado['ejec_motor_cerradas'] = cur.rowcount

    cur.execute(
        """UPDATE ejecuciones_no_reportadas
           SET estado = 'cerrado_ciclo'
           WHERE estado = 'pendiente'
             AND (tipo_categoria = 'no_motorizado' OR tipo_categoria IS NULL)"""
    )
    resultado['ejec_no_motor_cerradas'] = cur.rowcount

    # 3. Registrar el corte en ciclos_diarios
    cur.execute(
        """INSERT INTO ciclos_diarios
               (sync_id, fecha_corte, solicitudes_pendientes_cerradas,
                ejec_no_reportadas_motor, ejec_no_reportadas_no_motor,
                usuario_id, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (sync_id, ahora.isoformat(),
         resultado['solicitudes_cerradas'],
         resultado['ejec_motor_cerradas'],
         resultado['ejec_no_motor_cerradas'],
         None,
         ahora.isoformat())
    )

    resultado['aplicado'] = True
    return resultado


def sync_programacion(filepath):
    """
    Lee Excel de programación MP (soporta formato v2 y v3).
    Hace UPSERT en tabla equipos basado en consecutivo.
    Aplica corte diario si han pasado >= 20 hr desde el último sync.
    """
    xls = pd.ExcelFile(filepath)
    if 'Programacion_preventivos' in xls.sheet_names:
        sheet = 'Programacion_preventivos'
    elif 'Sheet1' in xls.sheet_names:
        sheet = 'Sheet1'
    else:
        sheet = xls.sheet_names[0]

    df = pd.read_excel(filepath, sheet_name=sheet, header=0, dtype=str)
    df = _normalize_columns(df)

    missing_req = [c for c in COLS_PROGRAMACION_REQUERIDAS if c not in df.columns]
    if missing_req:
        raise ValueError(
            f"Columnas requeridas faltantes en Excel: {', '.join(missing_req)}"
        )

    for col in df.columns:
        df[col] = df[col].map(lambda x: str(x).strip() if pd.notna(x) else None)

    df = df[df['consecutivo'].map(lambda x: _clean(x) is not None)]

    # Fingerprint (idempotencia)
    import hashlib
    fingerprint_parts = []
    for _, row in df.iterrows():
        c = _clean(row.get('consecutivo', ''))
        d = _clean(row.get('desviacion', ''))
        e = _clean(row.get('estado_mp', ''))
        i = _clean(row.get('indice_desviacion', ''))
        fingerprint_parts.append(f"{c}|{d}|{e}|{i}")
    fingerprint_parts.sort()
    fingerprint = hashlib.sha256('|'.join(fingerprint_parts).encode()).hexdigest()[:16]

    conn = get_db()
    cur = conn.cursor()
    ahora_dt = datetime.now(TZ_COL)

    ciclo_reusado = False
    last_sync = cur.execute(
        "SELECT sync_id FROM equipos ORDER BY sync_timestamp DESC LIMIT 1"
    ).fetchone()
    last_fingerprint = None
    if last_sync:
        last_fp_row = cur.execute(
            "SELECT detalle FROM sync_log WHERE tipo_sync = 'programacion' ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if last_fp_row and last_fp_row['detalle']:
            import json as _json
            try:
                last_detail = _json.loads(last_fp_row['detalle'])
                last_fingerprint = last_detail.get('fingerprint')
            except (ValueError, TypeError):
                pass

    if last_fingerprint and last_fingerprint == fingerprint and last_sync:
        sync_id = last_sync['sync_id']
        ciclo_reusado = True
    else:
        sync_id = int(ahora_dt.timestamp())

    # === CORTE DIARIO (independiente del reuse de ciclo) ===
    # Si han pasado >= 20 hr desde el último sync, cerramos ciclo anterior.
    corte = _aplicar_corte_diario(cur, sync_id, ahora_dt)

    sync_timestamp = ahora_dt.isoformat()
    nuevos = 0
    actualizados = 0

    # Snapshot de vehículos en zona de riesgo ANTES del UPSERT
    _ESTADOS_RIESGO = ('Vencido por tiempo', 'Vencido por medidor', 'Próximo', 'En tolerancia')
    prev_en_riesgo = {}
    for r in cur.execute(
        """SELECT vehiculo, ind_desviacion AS ind,
                  familia, rutina, categoria, sync_id, estado_mp
           FROM equipos
           WHERE estado_mp IN ({})
             AND vehiculo IS NOT NULL""".format(','.join('?' * len(_ESTADOS_RIESGO))),
        _ESTADOS_RIESGO
    ).fetchall():
        v = r['vehiculo']
        ind = float(r['ind']) if r['ind'] is not None else -999
        if v not in prev_en_riesgo or ind > (prev_en_riesgo[v]['ind'] or -999):
            prev_en_riesgo[v] = {
                'ind':       ind,
                'familia':   r['familia'],
                'rutina':    r['rutina'],
                'categoria': r['categoria'],  # v2 — para tipo_categoria
                'sync_id':   r['sync_id'],
                'estado_mp': r['estado_mp'],
            }

    # Snapshot ind_desviacion de respuestas "ejecutado" sin verificar, ANTES del UPSERT
    prev_ejecutados = {}
    for r in cur.execute(
        """SELECT s.equipo_id, e.ind_desviacion AS old_ind
           FROM respuestas r
           JOIN solicitudes s ON s.id = r.solicitud_id
           JOIN equipos e     ON e.id = s.equipo_id
           WHERE r.accion = 'ejecutado' AND r.verificacion IS NULL"""
    ).fetchall():
        eid = r['equipo_id']
        if eid not in prev_ejecutados:
            prev_ejecutados[eid] = r['old_ind']

    # UPSERT
    for _, row in df.iterrows():
        consecutivo_raw = _get_col(row, 'consecutivo')
        if consecutivo_raw is None:
            continue
        try:
            consecutivo = int(float(consecutivo_raw))
        except (ValueError, TypeError):
            logging.warning("Consecutivo no numérico ignorado: %r", consecutivo_raw)
            continue

        vehiculo = _get_col(row, 'vehiculo')
        if vehiculo:
            vehiculo = vehiculo.upper().strip()

        fecha_raw = _get_col(row, 'fecha_programacion')
        fecha_programacion = None
        if fecha_raw:
            try:
                dt = pd.to_datetime(fecha_raw, dayfirst=False, errors='coerce')
                if pd.notna(dt):
                    fecha_programacion = dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass

        ind_raw = _get_col(row, 'ind_desviacion', 'indice_desviacion', 'Ind_desviacion')
        ind_desviacion = None
        if ind_raw is not None:
            try:
                ind_desviacion = float(ind_raw.replace(',', '.'))
            except (ValueError, TypeError):
                logging.warning("ind_desviacion no numérico ignorado: %r", ind_raw)

        vals = (
            vehiculo,
            _get_col(row, 'categoria'),
            _get_col(row, 'estado_vehiculo'),
            _get_col(row, 'linea_vehiculo'),
            _get_col(row, 'familia'),
            _get_col(row, 'rutina'),
            _get_col(row, 'desviacion'),
            _get_col(row, 'desv_medidor'),
            _get_col(row, 'desv_tiempo'),
            ind_desviacion,
            _get_col(row, 'estado_mp'),
            fecha_programacion,
            _get_col(row, 'justificacion'),
            _get_col(row, 'observaciones'),
            _get_col(row, 'observaciones_2'),
            _get_col(row, 'tipo_ot'),
            sync_id,
            sync_timestamp,
        )

        exists = cur.execute(
            "SELECT id FROM equipos WHERE consecutivo = ?", (consecutivo,)
        ).fetchone()

        if exists:
            cur.execute("""
                UPDATE equipos
                SET vehiculo=?, categoria=?, estado_vehiculo=?, linea_vehiculo=?,
                    familia=?, rutina=?, desviacion=?, desv_medidor=?, desv_tiempo=?,
                    ind_desviacion=?, estado_mp=?,
                    fecha_programacion=?, justificacion=?, observaciones=?,
                    observaciones_2=?, tipo_ot=?, sync_id=?, sync_timestamp=?
                WHERE consecutivo=?
            """, (*vals, consecutivo))
            actualizados += 1
        else:
            cur.execute("""
                INSERT INTO equipos
                    (consecutivo, vehiculo, categoria, estado_vehiculo, linea_vehiculo,
                     familia, rutina, desviacion, desv_medidor, desv_tiempo,
                     ind_desviacion, estado_mp,
                     fecha_programacion, justificacion, observaciones, observaciones_2,
                     tipo_ot, sync_id, sync_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (consecutivo, *vals))
            nuevos += 1

    # Clasificar rutinas: principal vs verificación
    freq_map = {}
    for fr in cur.execute("SELECT rutina, frecuencia_medidor, frecuencia_dias FROM frecuencias_rutinas").fetchall():
        freq_map[fr['rutina'].upper().strip() if fr['rutina'] else ''] = (
            fr['frecuencia_medidor'], fr['frecuencia_dias']
        )

    for eq in cur.execute("SELECT id, rutina FROM equipos WHERE sync_id = ?", (sync_id,)).fetchall():
        rutina_name = (eq['rutina'] or '').upper().strip()
        fm, fd = freq_map.get(rutina_name, (None, None))
        tipo = clasificar_rutina(eq['rutina'], fm, fd)
        cur.execute("UPDATE equipos SET tipo_rutina = ? WHERE id = ?", (tipo, eq['id']))

    conn.commit()

    # Detección de ejecuciones no reportadas
    # v2 — cada registro se etiqueta con tipo_categoria según el maestro
    no_reportadas = 0
    no_reportadas_motor = 0
    no_reportadas_no_motor = 0
    ahora_nr = ahora_dt.isoformat()

    for vehiculo, prev in prev_en_riesgo.items():
        new_rows = cur.execute(
            """SELECT estado_mp, ind_desviacion AS ind
               FROM equipos
               WHERE UPPER(vehiculo) = ? AND sync_id = ?""",
            (vehiculo.upper(), sync_id)
        ).fetchall()
        if not new_rows:
            continue
        new_estados = [r['estado_mp'] for r in new_rows if r['estado_mp']]
        if not new_estados:
            continue
        if any(e in _ESTADOS_RIESGO for e in new_estados):
            continue

        new_inds = [float(r['ind']) for r in new_rows if r['ind'] is not None]

        prev_sync_id = prev['sync_id']
        if not prev_sync_id:
            continue

        ejecutado = cur.execute(
            """SELECT 1 FROM respuestas r
               JOIN solicitudes s ON s.id = r.solicitud_id
               JOIN equipos e     ON e.id = s.equipo_id
               WHERE UPPER(e.vehiculo) = ? AND s.sync_id = ? AND r.accion = 'ejecutado'
               LIMIT 1""",
            (vehiculo.upper(), prev_sync_id)
        ).fetchone()
        if ejecutado:
            continue

        no_ejecutado_resp = cur.execute(
            """SELECT r.id FROM respuestas r
               JOIN solicitudes s ON s.id = r.solicitud_id
               JOIN equipos e     ON e.id = s.equipo_id
               WHERE UPPER(e.vehiculo) = ? AND s.sync_id = ? AND r.accion = 'no_ejecutado'
               LIMIT 1""",
            (vehiculo.upper(), prev_sync_id)
        ).fetchone()
        if no_ejecutado_resp:
            cur.execute(
                """UPDATE respuestas SET verificacion = 'contradiccion_medidor'
                   WHERE id = ?""",
                (no_ejecutado_resp['id'],)
            )
            continue

        ya = cur.execute(
            """SELECT 1 FROM ejecuciones_no_reportadas
               WHERE UPPER(vehiculo) = ? AND sync_id_anterior = ? AND sync_id_nuevo = ?
               LIMIT 1""",
            (vehiculo.upper(), prev_sync_id, sync_id)
        ).fetchone()
        if ya:
            continue

        # v2 — clasificar por categoría de vehículo
        tipo_cat = _tipo_categoria_from(prev.get('categoria'))

        cur.execute(
            """INSERT INTO ejecuciones_no_reportadas
                   (vehiculo, familia, rutina, ind_desviacion_anterior,
                    ind_desviacion_nuevo, sync_id_anterior, sync_id_nuevo,
                    estado, tipo_categoria, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente', ?, ?)""",
            (vehiculo, prev['familia'], prev['rutina'],
             prev['ind'], min(new_inds),
             prev_sync_id, sync_id, tipo_cat, ahora_nr)
        )
        no_reportadas += 1
        if tipo_cat == 'motorizado':
            no_reportadas_motor += 1
        else:
            no_reportadas_no_motor += 1

    # Verificación de ejecuciones reportadas por el CIO
    DIAS_GRACIA = 5
    verificadas     = 0
    no_verificadas  = 0
    en_gracia       = 0

    resp_ejecutados = {}
    for r in cur.execute(
        """SELECT s.equipo_id, r.timestamp AS resp_ts
           FROM respuestas r
           JOIN solicitudes s ON s.id = r.solicitud_id
           WHERE r.accion = 'ejecutado' AND r.verificacion IS NULL"""
    ).fetchall():
        resp_ejecutados[r['equipo_id']] = r['resp_ts']

    for equipo_id, old_ind in prev_ejecutados.items():
        new_row = cur.execute(
            "SELECT ind_desviacion, estado_mp FROM equipos WHERE id = ?", (equipo_id,)
        ).fetchone()
        if not new_row:
            continue

        new_estado = new_row['estado_mp'] or ''
        new_ind = float(new_row['ind_desviacion']) if new_row['ind_desviacion'] is not None else None

        if new_estado == 'En ciclo':
            verif = 'confirmada'
            verificadas += 1
        elif new_estado in _ESTADOS_RIESGO:
            resp_ts = resp_ejecutados.get(equipo_id)
            if resp_ts:
                try:
                    resp_dt = datetime.fromisoformat(resp_ts)
                    dias_desde = (datetime.now(TZ_COL) - resp_dt).days
                    if dias_desde < DIAS_GRACIA:
                        en_gracia += 1
                        continue
                except (ValueError, TypeError):
                    pass
            verif = 'no_confirmada'
            no_verificadas += 1
        else:
            continue

        cur.execute(
            """UPDATE respuestas
               SET verificacion = ?, ind_desv_anterior = ?, ind_desv_posterior = ?
               WHERE accion = 'ejecutado' AND verificacion IS NULL
               AND solicitud_id IN (
                   SELECT id FROM solicitudes WHERE equipo_id = ?
               )""",
            (verif, old_ind, new_ind, equipo_id)
        )

    conn.commit()
    conn.close()

    return {
        'nuevos': nuevos,
        'actualizados': actualizados,
        'total': nuevos + actualizados,
        'sync_id': sync_id,
        'no_reportadas': no_reportadas,
        'no_reportadas_motor': no_reportadas_motor,
        'no_reportadas_no_motor': no_reportadas_no_motor,
        'verificadas': verificadas,
        'no_verificadas': no_verificadas,
        'en_gracia': en_gracia,
        'fingerprint': fingerprint,
        'ciclo_reusado': ciclo_reusado,
        # v2 — corte diario
        'corte_diario_aplicado': corte['aplicado'],
        'horas_desde_ultimo_sync': corte['horas_transcurridas'],
        'solicitudes_cerradas_sin_respuesta': corte['solicitudes_cerradas'],
        'ejec_no_rep_motor_cerradas': corte['ejec_motor_cerradas'],
        'ejec_no_rep_no_motor_cerradas': corte['ejec_no_motor_cerradas'],
    }


def _clean_sap(val):
    """Convierte SAP a string entero limpio: '10045678.0' → '10045678'."""
    if val is None:
        return None
    try:
        return str(int(float(val)))
    except (ValueError, TypeError):
        return val


def sync_filtros(filepath):
    """Reemplaza toda la tabla filtros_equipo con DELETE + INSERT."""
    df = pd.read_excel(filepath, sheet_name='Filtros', header=0, dtype=str)
    df.columns = df.columns.str.strip()

    missing = [c for c in COLS_FILTROS if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes en Excel de filtración: {', '.join(missing)}")

    df = df[COLS_FILTROS].copy()
    for col in df.columns:
        df[col] = df[col].map(lambda x: str(x).strip() if pd.notna(x) else None)

    df['EQUIPO'] = df['EQUIPO'].str.upper().str.strip()
    df = df[df['EQUIPO'].map(lambda x: _clean(x) is not None)]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM filtros_equipo")

    for _, row in df.iterrows():
        cur.execute("""
            INSERT INTO filtros_equipo (equipo, tipo, nombre_articulo, codigo_sap, tipo_filtro)
            VALUES (?, ?, ?, ?, ?)
        """, (
            _clean(row['EQUIPO']),
            _clean(row['TIPO']),
            _clean(row['NOMBRE ARTÍCULO']),
            _clean_sap(_clean(row['CODIGO SAP'])),
            _clean(row['TIPO FILTRO']),
        ))

    conn.commit()
    total_registros = len(df)
    equipos_unicos = df['EQUIPO'].nunique()
    conn.close()
    return {'total_registros': total_registros, 'equipos_unicos': equipos_unicos}


def sync_homologos(filepath):
    """Reemplaza tabla homologos con DELETE + INSERT."""
    df = pd.read_excel(filepath, sheet_name='Grupos_Homologos', header=0, dtype=str)
    df.columns = df.columns.str.strip()

    missing = [c for c in COLS_HOMOLOGOS if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes en Excel de homólogos: {', '.join(missing)}")

    for col in df.columns:
        df[col] = df[col].map(lambda x: str(x).strip() if pd.notna(x) else None)

    df = df[df['Grupo'].map(lambda x: _clean(x) is not None)]
    df = df[df['Codigo SAP'].map(lambda x: _clean(x) is not None)]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM homologos")

    for _, row in df.iterrows():
        grupo_raw = _clean(row['Grupo'])
        try:
            grupo = int(float(grupo_raw))
        except (ValueError, TypeError):
            logging.warning("Grupo no numérico ignorado: %r", grupo_raw)
            continue

        cur.execute("""
            INSERT INTO homologos (grupo, codigo_sap, descripcion, estado)
            VALUES (?, ?, ?, ?)
        """, (
            grupo,
            _clean_sap(_clean(row['Codigo SAP'])),
            _clean(row['Descripcion']),
            _clean(row['Estado']),
        ))

    conn.commit()
    total_registros = conn.execute("SELECT COUNT(*) FROM homologos").fetchone()[0]
    grupos = conn.execute("SELECT COUNT(DISTINCT grupo) FROM homologos").fetchone()[0]
    conn.close()

    return {'total_registros': int(total_registros), 'grupos': int(grupos)}


def sync_frecuencias(filepath):
    """Reemplaza tabla frecuencias_rutinas con DELETE + INSERT."""
    xls = pd.ExcelFile(filepath)
    sheet = 'DB_FRECUENCIAS' if 'DB_FRECUENCIAS' in xls.sheet_names else xls.sheet_names[0]
    df = pd.read_excel(filepath, sheet_name=sheet, header=0, dtype=str)
    df = _normalize_columns(df)

    missing = [c for c in COLS_FRECUENCIAS if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes en DB_FRECUENCIAS: {', '.join(missing)}")

    for col in df.columns:
        df[col] = df[col].map(lambda x: str(x).strip() if pd.notna(x) else None)

    df = df[df['rutina'].map(lambda x: _clean(x) is not None)]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM frecuencias_rutinas")

    for _, row in df.iterrows():
        rutina = _clean(row['rutina'])
        freq_med = None
        freq_dias = None
        try:
            v = _clean(row.get('frecuencia_medidor'))
            if v:
                freq_med = float(v)
        except (ValueError, TypeError):
            pass
        try:
            v = _clean(row.get('frecuencia_dias'))
            if v:
                freq_dias = int(float(v))
        except (ValueError, TypeError):
            pass

        cur.execute(
            "INSERT INTO frecuencias_rutinas (rutina, frecuencia_medidor, frecuencia_dias) VALUES (?, ?, ?)",
            (rutina, freq_med, freq_dias)
        )

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM frecuencias_rutinas").fetchone()[0]
    conn.close()
    return {'total_registros': int(total)}


COLS_UBICACIONES = ['codigo_sap', 'nombre', 'ubicacion']


def sync_ubicaciones(filepath):
    """DELETE + INSERT completo en tabla ubicaciones_filtros."""
    df = pd.read_excel(filepath, header=0, dtype=str)
    df = _normalize_columns(df)

    missing = [c for c in COLS_UBICACIONES if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes en Excel de ubicaciones: {', '.join(missing)}")

    df = df[COLS_UBICACIONES].copy()
    for col in df.columns:
        df[col] = df[col].map(lambda x: str(x).strip() if pd.notna(x) else None)

    df = df[df['codigo_sap'].map(lambda x: _clean(x) is not None)]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM ubicaciones_filtros")

    ahora = datetime.now(TZ_COL).isoformat()
    for _, row in df.iterrows():
        cur.execute(
            """INSERT INTO ubicaciones_filtros (codigo_sap, nombre, ubicacion, sync_timestamp)
               VALUES (?, ?, ?, ?)""",
            (_clean_sap(_clean(row['codigo_sap'])),
             _clean(row['nombre']),
             _clean(row['ubicacion']),
             ahora)
        )

    conn.commit()
    total_registros = len(df)
    codigos_unicos = df['codigo_sap'].nunique()
    conn.close()

    return {'total_registros': total_registros, 'codigos_unicos': codigos_unicos}


def sync_medidor_promedio(filepath):
    """Sync de promedios por vehículo + estándar por familia."""
    xls = pd.ExcelFile(filepath)

    sheet1 = 'DB_MEDIDOR_PROM' if 'DB_MEDIDOR_PROM' in xls.sheet_names else xls.sheet_names[0]
    df = pd.read_excel(filepath, sheet_name=sheet1, header=0, dtype=str)
    df = _normalize_columns(df)

    col_map = {
        'vehiculo': 'vehiculo',
        'tipo_vehiculo': 'tipo_vehiculo',
        'familia': 'familia',
        'medidor_transcurrido': 'medidor_transcurrido',
        'dias_transcurridos': 'dias_transcurridos',
        'medidor_promedio_dia_calc.': 'promedio_dia_calc',
        'medidor_promedio_dia_conf.': 'promedio_dia_conf',
        'medidor_trabajo_dia': 'medidor_trabajo_dia',
        'medidor_estandar': 'medidor_estandar',
        'tipo_medidor': 'tipo_medidor',
    }
    rename = {}
    for col in df.columns:
        if col in col_map:
            rename[col] = col_map[col]
    df = df.rename(columns=rename)

    if 'tipo_medidor' in df.columns:
        df = df[df['tipo_medidor'].notna() & (df['tipo_medidor'].str.strip() != '')]
    else:
        return {'vehiculos': 0, 'familias_estandar': 0, 'error': 'Columna tipo_medidor no encontrada'}

    for col in ['medidor_transcurrido', 'dias_transcurridos', 'promedio_dia_calc',
                'promedio_dia_conf', 'medidor_trabajo_dia', 'medidor_estandar']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].str.replace(',', '.') if df[col].dtype == object else df[col],
                                    errors='coerce')

    if 'vehiculo' in df.columns and 'medidor_trabajo_dia' in df.columns:
        df = df.sort_values('medidor_trabajo_dia', ascending=False, na_position='last')
        df = df.drop_duplicates(subset=['vehiculo', 'tipo_medidor'], keep='first')

    ahora = datetime.now(TZ_COL).isoformat()

    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM promedios_vehiculo")
    insertados = 0
    for _, row in df.iterrows():
        veh = _clean(row.get('vehiculo', ''))
        if not veh:
            continue
        cur.execute(
            """INSERT OR REPLACE INTO promedios_vehiculo
               (vehiculo, tipo_vehiculo, familia, medidor_transcurrido, dias_transcurridos,
                promedio_dia_calc, promedio_dia_conf, medidor_trabajo_dia,
                tipo_medidor, medidor_estandar, sync_timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (veh.upper().strip(),
             _clean(row.get('tipo_vehiculo', '')),
             _clean(row.get('familia', '')),
             row.get('medidor_transcurrido'),
             row.get('dias_transcurridos'),
             row.get('promedio_dia_calc'),
             row.get('promedio_dia_conf'),
             row.get('medidor_trabajo_dia'),
             _clean(row.get('tipo_medidor', '')),
             row.get('medidor_estandar'),
             ahora)
        )
        insertados += 1

    familias_estandar = 0
    if 'MED_ESTANDAR' in xls.sheet_names:
        df2 = pd.read_excel(filepath, sheet_name='MED_ESTANDAR', header=0, dtype=str)
        df2 = _normalize_columns(df2)

        cur.execute("DELETE FROM medidor_estandar")
        for _, row in df2.iterrows():
            fam = _clean(row.get('familia', ''))
            if not fam:
                continue
            val = None
            for col_name in ['medidor_estandar', 'valor']:
                if col_name in df2.columns:
                    try:
                        val = float(str(row.get(col_name, '')).replace(',', '.'))
                    except (ValueError, TypeError):
                        pass
                    break
            tipo = _clean(row.get('tipo_medidor', ''))
            if val and tipo:
                cur.execute(
                    "INSERT OR REPLACE INTO medidor_estandar (familia, valor, tipo_medidor) VALUES (?, ?, ?)",
                    (fam.upper().strip(), val, tipo)
                )
                familias_estandar += 1

    conn.commit()
    conn.close()

    return {
        'vehiculos': insertados,
        'familias_estandar': familias_estandar,
        'total_registros': insertados + familias_estandar,
    }
