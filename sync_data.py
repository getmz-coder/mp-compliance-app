"""ETL: sincronización de datos desde archivos Excel hacia SQLite."""
import logging
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_COL = ZoneInfo('America/Bogota')

from models import get_db


COLS_PROGRAMACION_REQUERIDAS = ['consecutivo', 'vehiculo', 'rutina', 'estado_mp']

COLS_FILTROS = ['EQUIPO', 'TIPO', 'NOMBRE ARTÍCULO', 'CODIGO SAP', 'TIPO FILTRO']

COLS_HOMOLOGOS = ['Grupo', 'Estado', 'Codigo SAP', 'Descripcion']


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


def sync_programacion(filepath):
    """
    Lee Excel procesado (hoja Programacion_preventivos, header en fila 1)
    y hace UPSERT en tabla equipos basado en consecutivo.
    Retorna: {'nuevos': X, 'actualizados': Y, 'total': Z, 'sync_id': N}
    """
    df = pd.read_excel(
        filepath,
        sheet_name='Programacion_preventivos',
        header=0,
        dtype=str,
    )
    df.columns = df.columns.str.strip()

    missing_req = [c for c in COLS_PROGRAMACION_REQUERIDAS if c not in df.columns]
    if missing_req:
        raise ValueError(
            f"Columnas requeridas faltantes en Excel: {', '.join(missing_req)}"
        )

    for col in df.columns:
        df[col] = df[col].map(lambda x: str(x).strip() if pd.notna(x) else None)

    df = df[df['consecutivo'].map(lambda x: _clean(x) is not None)]

    sync_id = int(datetime.now(TZ_COL).timestamp())
    sync_timestamp = datetime.now(TZ_COL).isoformat()

    conn = get_db()
    cur = conn.cursor()
    nuevos = 0
    actualizados = 0

    # Snapshot de vehículos en zona de riesgo ANTES del UPSERT
    prev_en_riesgo = {}
    for r in cur.execute(
        """SELECT vehiculo, CAST(ind_desviacion AS INTEGER) AS ind,
                  familia, rutina, sync_id
           FROM equipos
           WHERE CAST(ind_desviacion AS INTEGER) >= -10
             AND vehiculo IS NOT NULL"""
    ).fetchall():
        v = r['vehiculo']
        ind = r['ind'] if r['ind'] is not None else -999
        if v not in prev_en_riesgo or ind > (prev_en_riesgo[v]['ind'] or -999):
            prev_en_riesgo[v] = {
                'ind':     ind,
                'familia': r['familia'],
                'rutina':  r['rutina'],
                'sync_id': r['sync_id'],
            }

    # Snapshot ind_desviacion de respuestas "ejecutado" sin verificar, ANTES del UPSERT
    prev_ejecutados = {}  # equipo_id -> ind_desv anterior
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
                dt = pd.to_datetime(fecha_raw, dayfirst=True, errors='coerce')
                if pd.notna(dt):
                    fecha_programacion = dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass

        ind_raw = _get_col(row, 'indice_desviacion')
        ind_desviacion = None
        if ind_raw is not None:
            try:
                ind_desviacion = int(float(ind_raw))
            except (ValueError, TypeError):
                logging.warning("indice_desviacion no numérico ignorado: %r", ind_raw)

        vals = (
            vehiculo,
            _get_col(row, 'categoria'),
            _get_col(row, 'estado_vehiculo'),
            _get_col(row, 'linea_vehiculo'),
            _get_col(row, 'familia'),
            _get_col(row, 'rutina'),
            _get_col(row, 'desviacion'),
            ind_desviacion,
            _get_col(row, 'estado_mp'),
            fecha_programacion,
            _get_col(row, 'justificacion'),
            _get_col(row, 'observaciones'),
            _get_col(row, 'observaciones_2'),
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
                    familia=?, rutina=?, desviacion=?, ind_desviacion=?, estado_mp=?,
                    fecha_programacion=?, justificacion=?, observaciones=?,
                    observaciones_2=?, sync_id=?, sync_timestamp=?
                WHERE consecutivo=?
            """, (*vals, consecutivo))
            actualizados += 1
        else:
            cur.execute("""
                INSERT INTO equipos
                    (consecutivo, vehiculo, categoria, estado_vehiculo, linea_vehiculo,
                     familia, rutina, desviacion, ind_desviacion, estado_mp,
                     fecha_programacion, justificacion, observaciones, observaciones_2,
                     sync_id, sync_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (consecutivo, *vals))
            nuevos += 1

    # Detección de ejecuciones no reportadas
    no_reportadas = 0
    ahora_nr = datetime.now(TZ_COL).isoformat()
    for vehiculo, prev in prev_en_riesgo.items():
        new_rows = cur.execute(
            """SELECT CAST(ind_desviacion AS INTEGER) AS ind
               FROM equipos
               WHERE UPPER(vehiculo) = ? AND sync_id = ?""",
            (vehiculo.upper(), sync_id)
        ).fetchall()
        if not new_rows:
            continue
        new_inds = [r['ind'] for r in new_rows if r['ind'] is not None]
        if not new_inds or max(new_inds) >= -10:
            continue  # sigue en zona de riesgo o sin dato

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

        ya = cur.execute(
            """SELECT 1 FROM ejecuciones_no_reportadas
               WHERE UPPER(vehiculo) = ? AND sync_id_anterior = ? AND sync_id_nuevo = ?
               LIMIT 1""",
            (vehiculo.upper(), prev_sync_id, sync_id)
        ).fetchone()
        if ya:
            continue

        cur.execute(
            """INSERT INTO ejecuciones_no_reportadas
                   (vehiculo, familia, rutina, ind_desviacion_anterior,
                    ind_desviacion_nuevo, sync_id_anterior, sync_id_nuevo,
                    estado, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente', ?)""",
            (vehiculo, prev['familia'], prev['rutina'],
             prev['ind'], min(new_inds),
             prev_sync_id, sync_id, ahora_nr)
        )
        no_reportadas += 1

    # Verificación de ejecuciones reportadas por el CIO
    # Compara ind_desviacion anterior vs nuevo para confirmar si el MP realmente se hizo.
    # Umbral: new_ind < -20 → confirmada (contador se reinició)
    #         new_ind >= -10 → no_confirmada (sigue en zona de riesgo, no hubo cambio)
    verificadas     = 0
    no_verificadas  = 0
    for equipo_id, old_ind in prev_ejecutados.items():
        new_row = cur.execute(
            "SELECT ind_desviacion FROM equipos WHERE id = ?", (equipo_id,)
        ).fetchone()
        if not new_row or new_row['ind_desviacion'] is None:
            continue

        new_ind = int(new_row['ind_desviacion'])

        if new_ind < -20:
            verif = 'confirmada'
            verificadas += 1
        elif new_ind >= -10:
            verif = 'no_confirmada'
            no_verificadas += 1
        else:
            continue  # zona ambigua (-20 <= new_ind < -10), no actualizar

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
        'verificadas': verificadas,
        'no_verificadas': no_verificadas,
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
    """
    Lee Excel maestro filtración (hoja 'Filtros', header fila 1) y reemplaza
    toda la tabla filtros_equipo con DELETE + INSERT.
    Retorna: {'total_registros': X, 'equipos_unicos': Y}
    """
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
    """
    Lee Excel hoja 'Grupos_Homologos' y reemplaza tabla homologos
    con DELETE + INSERT completo.
    Retorna: {'total_registros': X, 'grupos': Y}
    """
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
