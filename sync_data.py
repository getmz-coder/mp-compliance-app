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

COLS_FRECUENCIAS = ['rutina', 'frecuencia_medidor', 'frecuencia_dias']


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
    Lee Excel de programación MP (soporta formato v2 y v3).
    v2: hoja Programacion_preventivos, 14 columnas, ind_desviacion entero
    v3: hoja Sheet1, 11 columnas, Ind_desviacion decimal, +tipo_ot, -4 columnas
    Hace UPSERT en tabla equipos basado en consecutivo.
    """
    # Detectar hoja automáticamente
    xls = pd.ExcelFile(filepath)
    if 'Programacion_preventivos' in xls.sheet_names:
        sheet = 'Programacion_preventivos'
    elif 'Sheet1' in xls.sheet_names:
        sheet = 'Sheet1'
    else:
        sheet = xls.sheet_names[0]

    df = pd.read_excel(filepath, sheet_name=sheet, header=0, dtype=str)
    df.columns = df.columns.str.strip()

    # Normalizar nombres de columna (soporta ambos formatos)
    col_renames = {}
    for c in df.columns:
        cl = c.lower().replace(' ', '_')
        if cl == 'ind_desviacion' or cl == 'indice_desviacion':
            col_renames[c] = 'ind_desviacion'
    if col_renames:
        df = df.rename(columns=col_renames)

    missing_req = [c for c in COLS_PROGRAMACION_REQUERIDAS if c not in df.columns]
    if missing_req:
        raise ValueError(
            f"Columnas requeridas faltantes en Excel: {', '.join(missing_req)}"
        )

    for col in df.columns:
        df[col] = df[col].map(lambda x: str(x).strip() if pd.notna(x) else None)

    df = df[df['consecutivo'].map(lambda x: _clean(x) is not None)]

    # H-NEW-06: Detectar si el Excel es idéntico al último sync
    # Fingerprint = hash de consecutivos + desviaciones + estados
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

    # Verificar fingerprint del último sync
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
        # Mismo archivo — reusar ciclo existente
        sync_id = last_sync['sync_id']
        ciclo_reusado = True
    else:
        sync_id = int(datetime.now(TZ_COL).timestamp())

    sync_timestamp = datetime.now(TZ_COL).isoformat()
    nuevos = 0
    actualizados = 0

    # Snapshot de vehículos en zona de riesgo ANTES del UPSERT
    # Zona de riesgo = estado_mp indica que requiere atención
    _ESTADOS_RIESGO = ('Vencido por tiempo', 'Vencido por medidor', 'Próximo', 'En tolerancia')
    prev_en_riesgo = {}
    for r in cur.execute(
        """SELECT vehiculo, ind_desviacion AS ind,
                  familia, rutina, sync_id, estado_mp
           FROM equipos
           WHERE estado_mp IN ({})
             AND vehiculo IS NOT NULL""".format(','.join('?' * len(_ESTADOS_RIESGO))),
        _ESTADOS_RIESGO
    ).fetchall():
        v = r['vehiculo']
        ind = float(r['ind']) if r['ind'] is not None else -999
        if v not in prev_en_riesgo or ind > (prev_en_riesgo[v]['ind'] or -999):
            prev_en_riesgo[v] = {
                'ind':     ind,
                'familia': r['familia'],
                'rutina':  r['rutina'],
                'sync_id': r['sync_id'],
                'estado_mp': r['estado_mp'],
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
                    familia=?, rutina=?, desviacion=?, ind_desviacion=?, estado_mp=?,
                    fecha_programacion=?, justificacion=?, observaciones=?,
                    observaciones_2=?, tipo_ot=?, sync_id=?, sync_timestamp=?
                WHERE consecutivo=?
            """, (*vals, consecutivo))
            actualizados += 1
        else:
            cur.execute("""
                INSERT INTO equipos
                    (consecutivo, vehiculo, categoria, estado_vehiculo, linea_vehiculo,
                     familia, rutina, desviacion, ind_desviacion, estado_mp,
                     fecha_programacion, justificacion, observaciones, observaciones_2,
                     tipo_ot, sync_id, sync_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (consecutivo, *vals))
            nuevos += 1

    # Detección de ejecuciones no reportadas
    no_reportadas = 0
    ahora_nr = datetime.now(TZ_COL).isoformat()
    for vehiculo, prev in prev_en_riesgo.items():
        new_rows = cur.execute(
            """SELECT estado_mp, ind_desviacion AS ind
               FROM equipos
               WHERE UPPER(vehiculo) = ? AND sync_id = ?""",
            (vehiculo.upper(), sync_id)
        ).fetchall()
        if not new_rows:
            continue
        # Si todos los equipos del vehículo salieron de zona de riesgo → no reportada
        new_estados = [r['estado_mp'] for r in new_rows if r['estado_mp']]
        if not new_estados:
            continue
        if any(e in _ESTADOS_RIESGO for e in new_estados):
            continue  # sigue en zona de riesgo

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
    # Compara estado_mp anterior vs nuevo para confirmar si el MP realmente se hizo.
    # Confirmada: estado_mp cambió a 'En ciclo' (equipo regresó a zona normal)
    # No confirmada: estado_mp sigue en zona de riesgo tras ventana de gracia
    # H-NEW-08: Ventana de gracia de 5 días para Tipo C (Paymover, Dorthy)
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
            # Verificar ventana de gracia
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
            continue  # Sin dato u otro estado, no actualizar

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
        'en_gracia': en_gracia,
        'fingerprint': fingerprint,
        'ciclo_reusado': ciclo_reusado,
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


def sync_frecuencias(filepath):
    """
    Lee Excel hoja 'DB_FRECUENCIAS' y reemplaza tabla frecuencias_rutinas
    con DELETE + INSERT completo.
    Retorna: {'total_registros': X}
    """
    df = pd.read_excel(filepath, sheet_name='DB_FRECUENCIAS', header=0, dtype=str)
    df.columns = df.columns.str.strip().str.lower()

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


COLS_UBICACIONES = ['CODIGO SAP', 'NOMBRE', 'UBICACION']


def sync_ubicaciones(filepath):
    """
    Lee Excel de ubicaciones de filtros (3 columnas: CODIGO SAP, NOMBRE, UBICACION).
    Hace DELETE + INSERT completo en tabla ubicaciones_filtros.
    Retorna: {'total_registros': X, 'codigos_unicos': Y}
    """
    df = pd.read_excel(filepath, header=0, dtype=str)
    df.columns = df.columns.str.strip().str.upper()

    missing = [c for c in COLS_UBICACIONES if c not in df.columns]
    if missing:
        raise ValueError(f"Columnas faltantes en Excel de ubicaciones: {', '.join(missing)}")

    df = df[COLS_UBICACIONES].copy()

    for col in df.columns:
        df[col] = df[col].map(lambda x: str(x).strip() if pd.notna(x) else None)

    df = df[df['CODIGO SAP'].map(lambda x: _clean(x) is not None)]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM ubicaciones_filtros")

    ahora = datetime.now(TZ_COL).isoformat()
    for _, row in df.iterrows():
        cur.execute(
            """INSERT INTO ubicaciones_filtros (codigo_sap, nombre, ubicacion, sync_timestamp)
               VALUES (?, ?, ?, ?)""",
            (_clean_sap(_clean(row['CODIGO SAP'])),
             _clean(row['NOMBRE']),
             _clean(row['UBICACION']),
             ahora)
        )

    conn.commit()
    total_registros = len(df)
    codigos_unicos = df['CODIGO SAP'].nunique()
    conn.close()

    return {'total_registros': total_registros, 'codigos_unicos': codigos_unicos}
