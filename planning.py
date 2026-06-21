"""Lógica de planeación predictiva de repuestos."""
import re
from datetime import date, timedelta


def parse_desviacion(s):
    """
    Parsea un string de desviación MP a dict con tipo, valor y si está vencido.

    Formatos soportados:
      'Hoy'              → {'tipo': 'dias', 'valor': 0, 'vencido': False}
      'Falta 17d'        → {'tipo': 'dias', 'valor': 17, 'vencido': False}
      'Falta 43.9 Horas' → {'tipo': 'horas', 'valor': 43.9, 'vencido': False}
      'Falta 28 H'       → {'tipo': 'horas', 'valor': 28, 'vencido': False}
      'Falta 1 Hora'     → {'tipo': 'horas', 'valor': 1, 'vencido': False}
      'Hace 46 Horas'    → {'tipo': 'horas', 'valor': 46, 'vencido': True}
      'Hace 2y 7M 1d'    → {'tipo': 'dias', 'valor': 941, 'vencido': True}
      'Falta 120 km'     → {'tipo': 'km', 'valor': 120, 'vencido': False}

    Retorna None si no se puede parsear.
    """
    if not s or not isinstance(s, str):
        return None

    s = s.strip()

    if s.lower() == 'hoy':
        return {'tipo': 'dias', 'valor': 0, 'vencido': False}

    sl = s.lower()
    if sl.startswith('falta'):
        vencido = False
        resto = s[5:].strip()
    elif sl.startswith('hace'):
        vencido = True
        resto = s[4:].strip()
    else:
        return None

    tokens = re.findall(r'(\d+(?:\.\d+)?)\s*([A-Za-z]+)', resto)
    if not tokens:
        return None

    total_dias = 0.0
    total_horas = 0.0
    total_km = 0.0

    for num_str, unit in tokens:
        num = float(num_str)
        unit_l = unit.lower()
        if unit_l in ('h', 'hora', 'horas'):
            total_horas += num
        elif unit_l in ('km', 'k'):
            total_km += num
        elif unit_l in ('d', 'dia', 'dias'):
            total_dias += num
        elif unit_l in ('m', 'mes', 'meses'):
            total_dias += num * 30
        elif unit_l in ('y', 'ano', 'anos', 'year', 'years'):
            total_dias += num * 365
        else:
            total_dias += num

    if total_km > 0 and total_horas == 0 and total_dias == 0:
        return {'tipo': 'km', 'valor': total_km, 'vencido': vencido}
    if total_horas > 0 and total_km == 0 and total_dias == 0:
        return {'tipo': 'horas', 'valor': total_horas, 'vencido': vencido}
    if total_dias > 0:
        if total_horas > 0:
            total_dias += total_horas / 24.0
        return {'tipo': 'dias', 'valor': total_dias, 'vencido': vencido}
    if total_horas > 0:
        return {'tipo': 'horas', 'valor': total_horas, 'vencido': vencido}

    return None


def calcular_fecha_estimada(parsed, familia, promedios_map, today=None):
    """
    Calcula la fecha estimada de próximo MP.

    parsed: resultado de parse_desviacion()
    familia: string nombre de familia del equipo
    promedios_map: dict {familia: {'horas_promedio_dia': float, 'km_promedio_dia': float}}
    today: date (inyectable para tests), default date.today()

    Retorna:
      {'fecha': date|None, 'tipo': str|None, 'sin_dato': bool, 'vencido': bool}
    """
    if today is None:
        today = date.today()

    if parsed is None:
        return {'fecha': None, 'tipo': None, 'sin_dato': True, 'vencido': False}

    tipo = parsed['tipo']
    valor = parsed['valor']
    vencido = parsed['vencido']

    if tipo == 'dias':
        delta = timedelta(days=valor)
        fecha = (today - delta) if vencido else (today + delta)
        return {'fecha': fecha, 'tipo': 'dias', 'sin_dato': False, 'vencido': vencido}

    prom = promedios_map.get(familia, {}) if promedios_map else {}

    if tipo == 'horas':
        hpd = prom.get('horas_promedio_dia')
        if not hpd or hpd <= 0:
            return {'fecha': None, 'tipo': 'horas', 'sin_dato': True, 'vencido': vencido}
        dias = valor / hpd
        delta = timedelta(days=dias)
        fecha = (today - delta) if vencido else (today + delta)
        return {'fecha': fecha, 'tipo': 'horas', 'sin_dato': False, 'vencido': vencido}

    if tipo == 'km':
        kpd = prom.get('km_promedio_dia')
        if not kpd or kpd <= 0:
            return {'fecha': None, 'tipo': 'km', 'sin_dato': True, 'vencido': vencido}
        dias = valor / kpd
        delta = timedelta(days=dias)
        fecha = (today - delta) if vencido else (today + delta)
        return {'fecha': fecha, 'tipo': 'km', 'sin_dato': False, 'vencido': vencido}

    return {'fecha': None, 'tipo': tipo, 'sin_dato': True, 'vencido': vencido}


def calcular_planeacion(conn, fecha_desde, fecha_hasta, incluir_vencidos, today=None):
    """
    Calcula equipos en rango de fechas para planeación de repuestos.

    conn: conexión sqlite3 abierta
    fecha_desde, fecha_hasta: objetos date
    incluir_vencidos: bool — incluir equipos vencidos sin respuesta registrada
    today: date inyectable para tests

    Retorna:
      {
        'en_rango': [...],
        'sin_dato': [...],
        'vencidos_pendientes': [...],
        'kpis': {
          'total_en_rango': int,
          'sin_dato': int,
          'vencidos_pendientes': int,
          'familias': int,
        }
      }
    """
    if today is None:
        today = date.today()

    promedios_map = {}
    for row in conn.execute(
        "SELECT familia, horas_promedio_dia, km_promedio_dia FROM promedios_familia"
    ).fetchall():
        promedios_map[row['familia']] = {
            'horas_promedio_dia': row['horas_promedio_dia'],
            'km_promedio_dia': row['km_promedio_dia'],
        }

    row = conn.execute("SELECT MAX(sync_id) AS msid FROM equipos").fetchone()
    if not row or not row['msid']:
        return {
            'en_rango': [], 'sin_dato': [], 'vencidos_pendientes': [],
            'kpis': {'total_en_rango': 0, 'sin_dato': 0, 'vencidos_pendientes': 0, 'familias': 0},
        }

    last_sync = row['msid']

    ejecutados = {
        r['equipo_id']
        for r in conn.execute(
            """SELECT DISTINCT s.equipo_id
               FROM solicitudes s
               JOIN respuestas r ON r.solicitud_id = s.id
               WHERE s.sync_id = ?""",
            (last_sync,)
        ).fetchall()
    }

    equipos = conn.execute(
        """SELECT id, vehiculo, familia, rutina, desviacion, ind_desviacion, estado_mp
           FROM equipos WHERE sync_id = ? ORDER BY familia, vehiculo""",
        (last_sync,)
    ).fetchall()

    en_rango = []
    sin_dato = []
    vencidos_pendientes = []

    for eq in equipos:
        if eq['id'] in ejecutados:
            continue

        parsed = parse_desviacion(eq['desviacion'] or '')
        est = calcular_fecha_estimada(parsed, eq['familia'], promedios_map, today=today)

        equipo_dict = {
            'id': eq['id'],
            'vehiculo': eq['vehiculo'],
            'familia': eq['familia'],
            'rutina': eq['rutina'],
            'desviacion': eq['desviacion'],
            'ind_desviacion': eq['ind_desviacion'],
            'estado_mp': eq['estado_mp'],
            'fecha_estimada': est['fecha'],
            'tipo_medidor': est['tipo'],
            'sin_dato': est['sin_dato'],
            'vencido_actual': est['vencido'],
        }

        if est['sin_dato']:
            sin_dato.append(equipo_dict)
        elif est['vencido'] or (est['fecha'] and est['fecha'] <= today):
            if incluir_vencidos:
                vencidos_pendientes.append(equipo_dict)
        elif est['fecha'] and fecha_desde <= est['fecha'] <= fecha_hasta:
            en_rango.append(equipo_dict)

    en_rango.sort(key=lambda x: x['fecha_estimada'])

    familias_en_rango = len({e['familia'] for e in en_rango})

    return {
        'en_rango': en_rango,
        'sin_dato': sin_dato,
        'vencidos_pendientes': vencidos_pendientes,
        'kpis': {
            'total_en_rango': len(en_rango),
            'sin_dato': len(sin_dato),
            'vencidos_pendientes': len(vencidos_pendientes),
            'familias': familias_en_rango,
        },
    }


def agregar_repuestos(conn, vehiculos):
    """
    Agrega filtros requeridos por lista de vehículos, cruzando con homólogos.

    vehiculos: list de strings (nombres de vehículo, ej. 'AGPU 21')

    Retorna lista de dicts ordenada por cantidad DESC:
      {'codigo_sap', 'nombre_articulo', 'tipo_filtro', 'cantidad', 'equipos': list, 'homologos': list}
    """
    if not vehiculos:
        return []

    placeholders = ','.join('?' * len(vehiculos))
    upper_vehiculos = [v.upper() for v in vehiculos]

    rows = conn.execute(
        f"""SELECT f.codigo_sap, f.nombre_articulo, f.tipo_filtro,
                   UPPER(f.equipo) AS equipo
            FROM filtros_equipo f
            WHERE UPPER(f.equipo) IN ({placeholders})
              AND f.codigo_sap IS NOT NULL""",
        upper_vehiculos
    ).fetchall()

    grupos = {}
    for row in rows:
        sap = row['codigo_sap']
        if sap not in grupos:
            grupos[sap] = {
                'codigo_sap': sap,
                'nombre_articulo': row['nombre_articulo'],
                'tipo_filtro': row['tipo_filtro'],
                'cantidad': 0,
                'equipos': [],
            }
        grupos[sap]['cantidad'] += 1
        if row['equipo'] not in grupos[sap]['equipos']:
            grupos[sap]['equipos'].append(row['equipo'])

    all_saps = list(grupos.keys())
    homo_map = {}
    if all_saps:
        ph2 = ','.join('?' * len(all_saps))
        homo_rows = conn.execute(
            f"""SELECT h.codigo_sap AS sap_principal,
                       h2.codigo_sap, h2.descripcion, h2.estado
                FROM homologos h
                JOIN homologos h2 ON h2.grupo = h.grupo
                WHERE h.codigo_sap IN ({ph2})
                ORDER BY h.codigo_sap, h2.estado DESC, h2.codigo_sap""",
            all_saps
        ).fetchall()
        for hr in homo_rows:
            sp = hr['sap_principal']
            if sp not in homo_map:
                homo_map[sp] = []
            homo_map[sp].append({
                'codigo_sap': hr['codigo_sap'],
                'descripcion': hr['descripcion'],
                'estado': hr['estado'],
            })

    resultado = []
    for sap, g in grupos.items():
        g['homologos'] = homo_map.get(sap, [])
        resultado.append(g)

    resultado.sort(key=lambda x: x['cantidad'], reverse=True)
    return resultado
