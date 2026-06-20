"""ETL: sincronización de datos desde archivos Excel hacia SQLite."""
import logging
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_COL = ZoneInfo('America/Bogota')

from models import get_db


COLS_PROGRAMACION_REQUERIDAS = ['consecutivo', 'vehiculo', 'rutina', 'estado_mp']

COLS_FILTROS = ['EQUIPO', 'TIPO', 'NOMBRE ARTÍCULO', 'CODIGO SAP', 'TIPO FILTRO']


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

    conn.commit()
    conn.close()

    return {
        'nuevos': nuevos,
        'actualizados': actualizados,
        'total': nuevos + actualizados,
        'sync_id': sync_id,
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
