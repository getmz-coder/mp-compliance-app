# Planeación de Repuestos Predictiva — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar módulo de Planeación Predictiva de Repuestos para admin/superadmin: calcula fecha estimada de próximo MP por equipo usando desviación actual + promedios de consumo por familia, agrega los filtros requeridos por código SAP, y permite exportar a Excel.

**Architecture:** Server-rendered Jinja2. Nueva ruta `GET /admin/planeacion` con calculadora de rango de fechas (query params `fd`, `fh`, `iv`). Módulo `planning.py` con funciones puras testeables. Template con 4 secciones: promedios editables (AJAX inline), calculadora, tabla de resultados, agregado de repuestos.

**Tech Stack:** Python 3.11, Flask, SQLite (sqlite3), pandas + openpyxl para ETL, Jinja2 templates, fetch() AJAX para promedios inline.

## Global Constraints

- Zero CDN — todo CSS/JS embebido en el template, nada externo
- Branding Talma: Azul `#002D6E`, Verde `#80AE3F`, Cielo `#1E88E5`, Ámbar `#E67E22`, Fondo `#F0F2F5`
- Español en UI y docstrings; inglés en variables y funciones de Python
- Commits en español, descriptivos
- Solo roles `admin` y `superadmin` pueden acceder
- Respuestas inmutables — esta feature solo lee datos

---

## File Map

| Archivo | Cambio |
|---|---|
| `models.py` | Agregar tablas `promedios_familia`, `frecuencias_rutinas`; llamar `_migrate_planeacion()` en `init_db()` |
| `sync_data.py` | Agregar `COLS_FRECUENCIAS` y función `sync_frecuencias(filepath)` |
| `app.py` | Route `admin_sync`: campo `file_frecuencias`; nueva ruta `GET/POST /admin/planeacion`; ruta `POST /admin/planeacion/promedio/<familia>`; ruta `GET /admin/planeacion/exportar` |
| `templates/admin/sync.html` | Agregar sección #4 upload frecuencias |
| `templates/admin/planeacion.html` | **Crear** — template completo con 4 secciones + CSS + JS |
| `base.html` | Agregar link "Planeación" en navbar admin |
| `planning.py` | **Crear** — 4 funciones: `parse_desviacion`, `calcular_fecha_estimada`, `calcular_planeacion`, `agregar_repuestos` |
| `tests/test_planning_parser.py` | **Crear** — tests para `parse_desviacion` |
| `tests/test_planning_calc.py` | **Crear** — tests para `calcular_fecha_estimada` y `calcular_planeacion` |
| `tests/test_planning_repuestos.py` | **Crear** — tests para `agregar_repuestos` |
| `tests/test_sync_frecuencias.py` | **Crear** — tests para `sync_frecuencias` |

---

## Task 1: Tablas BD y migración

**Files:**
- Modify: `models.py` (función `init_db`, bloque `executescript`, y agregar `_migrate_planeacion`)

**Interfaces:**
- Produces: tablas `promedios_familia(familia UNIQUE, horas_promedio_dia, km_promedio_dia, updated_at)` y `frecuencias_rutinas(rutina, frecuencia_medidor, frecuencia_dias)` en SQLite

- [ ] **Step 1: Agregar tablas en `executescript` de `init_db()`**

En `models.py`, dentro del bloque `cur.executescript("""...""")`, agregar antes del `""")`:

```sql
        CREATE TABLE IF NOT EXISTS promedios_familia (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            familia             VARCHAR(100) UNIQUE,
            horas_promedio_dia  REAL,
            km_promedio_dia     REAL,
            updated_at          DATETIME
        );

        CREATE TABLE IF NOT EXISTS frecuencias_rutinas (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            rutina              TEXT,
            frecuencia_medidor  REAL,
            frecuencia_dias     INTEGER
        );
```

- [ ] **Step 2: Agregar `_migrate_planeacion()` y llamarla en `init_db()`**

Agregar función antes de `seed_motivos()`:

```python
def _migrate_planeacion(conn):
    """Crea tablas de planeación si no existen en BDs ya inicializadas."""
    cur = conn.cursor()
    tablas = {row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'promedios_familia' not in tablas:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS promedios_familia (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                familia             VARCHAR(100) UNIQUE,
                horas_promedio_dia  REAL,
                km_promedio_dia     REAL,
                updated_at          DATETIME
            )
        """)
    if 'frecuencias_rutinas' not in tablas:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS frecuencias_rutinas (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                rutina              TEXT,
                frecuencia_medidor  REAL,
                frecuencia_dias     INTEGER
            )
        """)
```

En `init_db()`, después de las llamadas a `_migrate_equipos(conn)` y `_migrate_respuestas(conn)`, agregar:

```python
    _migrate_planeacion(conn)
```

- [ ] **Step 3: Verificar con test rápido**

```bash
python -c "import models; models.init_db(); from models import get_db; conn=get_db(); print([r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]); conn.close()"
```

Debe incluir `promedios_familia` y `frecuencias_rutinas` en la lista.

---

## Task 2: ETL `sync_frecuencias` + upload en sync

**Files:**
- Modify: `sync_data.py` (agregar constante + función)
- Modify: `app.py` (route `admin_sync`, manejo de `file_frecuencias`)
- Modify: `templates/admin/sync.html` (agregar sección #4)
- Create: `tests/test_sync_frecuencias.py`

**Interfaces:**
- Lee hoja `DB_FRECUENCIAS` del Excel con columnas `rutina`, `frecuencia_medidor`, `frecuencia_dias`
- Hace DELETE + INSERT (reemplazo completo)
- Retorna `{'total_registros': X}`

- [ ] **Step 1: Agregar en `sync_data.py`**

Agregar constante después de `COLS_HOMOLOGOS`:

```python
COLS_FRECUENCIAS = ['rutina', 'frecuencia_medidor', 'frecuencia_dias']
```

Agregar función al final del archivo:

```python
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
```

- [ ] **Step 2: Modificar route `admin_sync` en `app.py`**

En la función `admin_sync()`, dentro del bloque `if request.method == 'POST':`, agregar manejo de `file_frecuencias` similar a los otros archivos. Buscar el bloque que maneja `file_homologos` y agregar después:

```python
        file_frec = request.files.get('file_frecuencias')
        if file_frec and file_frec.filename:
            filename = secure_filename(file_frec.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file_frec.save(path)
            try:
                r = sync_frecuencias(path)
                resultados['frecuencias'] = r
                flash(f"Frecuencias sincronizadas: {r['total_registros']} rutinas.", 'success')
            except Exception as e:
                flash(f"Error en frecuencias: {e}", 'error')
            finally:
                if os.path.exists(path):
                    os.remove(path)
```

También agregar el import en la parte superior donde se importa `sync_data`:

```python
from sync_data import sync_programacion, sync_filtros, sync_homologos, sync_frecuencias
```

- [ ] **Step 3: Agregar sección #4 en `templates/admin/sync.html`**

Agregar nueva clase de ícono en el bloque `<style>`:

```css
  .section-icon.purple { background: #f5f3ff; }
  .section-icon.purple svg { stroke: #7c3aed; }
```

Agregar sección antes del `<div class="form-footer">`:

```html
      <!-- Frecuencias de Rutinas -->
      <div class="upload-section">
        <div class="section-header">
          <div class="section-icon purple">
            <svg viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
          </div>
          <div class="section-info">
            <h3>Frecuencias de Rutinas <span class="badge-optional">Opcional</span></h3>
            <p>Tabla de frecuencias por rutina MP (horas o km por ciclo, días entre mantenimientos). Usada por el módulo de Planeación Predictiva.</p>
          </div>
        </div>

        <div class="file-zone" id="zone-frec">
          <input type="file" name="file_frecuencias" accept=".xlsx,.xls"
                 onchange="setFile(this,'zone-frec','name-frec')">
          <div class="file-zone-inner">
            <div class="fz-icon">
              <svg viewBox="0 0 24 24">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </div>
            <div>
              <div class="fz-text">Haz clic para seleccionar o arrastra el archivo aquí</div>
              <div class="fz-name" id="name-frec"></div>
            </div>
          </div>
        </div>

        <p class="cols-hint">
          Hoja requerida: <code>DB_FRECUENCIAS</code> · Columnas: <code>rutina</code> · <code>frecuencia_medidor</code> · <code>frecuencia_dias</code>
        </p>
      </div>
```

Actualizar el `<span class="form-note">` del footer para reflejar cuatro archivos:

```html
        <span class="form-note">Se debe subir al menos uno de los cuatro archivos.</span>
```

- [ ] **Step 4: Crear `tests/test_sync_frecuencias.py`**

```python
import pytest
import openpyxl
from sync_data import sync_frecuencias
from models import get_db


@pytest.fixture
def frec_xlsx(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'DB_FRECUENCIAS'
    ws.append(['rutina', 'frecuencia_medidor', 'frecuencia_dias'])
    ws.append(['MANTENIMIENTO TIPO A 400H', 400, 90])
    ws.append(['MANTENIMIENTO TIPO B 1000H', 1000, 180])
    path = str(tmp_path / 'frecuencias.xlsx')
    wb.save(path)
    return path


def test_sync_frecuencias_inserta(frec_xlsx):
    r = sync_frecuencias(frec_xlsx)
    assert r['total_registros'] == 2


def test_sync_frecuencias_reemplaza(frec_xlsx):
    sync_frecuencias(frec_xlsx)
    sync_frecuencias(frec_xlsx)
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM frecuencias_rutinas").fetchone()[0]
    conn.close()
    assert count == 2


def test_sync_frecuencias_columna_faltante(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'DB_FRECUENCIAS'
    ws.append(['rutina'])
    ws.append(['MANTENIMIENTO A'])
    path = str(tmp_path / 'bad.xlsx')
    wb.save(path)
    with pytest.raises(ValueError, match='frecuencia_medidor'):
        sync_frecuencias(path)
```

---

## Task 3: Módulo `planning.py` — funciones puras

**Files:**
- Create: `planning.py`
- Create: `tests/test_planning_parser.py`
- Create: `tests/test_planning_calc.py`
- Create: `tests/test_planning_repuestos.py`

**Interfaces:**
- `parse_desviacion(s) -> dict | None`: parsea string desviación a `{'tipo': 'dias'|'horas'|'km', 'valor': float, 'vencido': bool}`
- `calcular_fecha_estimada(parsed, familia, promedios_map, today=None) -> dict`: retorna `{'fecha': date|None, 'tipo': str|None, 'sin_dato': bool, 'vencido': bool}`
- `calcular_planeacion(conn, fecha_desde, fecha_hasta, incluir_vencidos, today=None) -> dict`
- `agregar_repuestos(conn, vehiculos) -> list`

- [ ] **Step 1: Crear `planning.py`**

```python
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

    # Detectar dirección
    sl = s.lower()
    if sl.startswith('falta'):
        vencido = False
        resto = s[5:].strip()
    elif sl.startswith('hace'):
        vencido = True
        resto = s[4:].strip()
    else:
        return None

    # Extraer todos los tokens numérico+unidad
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
            # unidad desconocida → asumir días
            total_dias += num

    # Determinar tipo dominante
    if total_km > 0 and total_horas == 0 and total_dias == 0:
        return {'tipo': 'km', 'valor': total_km, 'vencido': vencido}
    if total_horas > 0 and total_km == 0 and total_dias == 0:
        return {'tipo': 'horas', 'valor': total_horas, 'vencido': vencido}
    if total_dias > 0:
        # Si también hay horas, convertir horas a días y sumar
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
        if vencido:
            fecha = today - delta
        else:
            fecha = today + delta
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
        'en_rango': [...],           # equipos con fecha estimada en [fd, fh]
        'sin_dato': [...],           # equipos sin promedio para calcular fecha
        'vencidos_pendientes': [...],# si incluir_vencidos: equipos vencidos sin respuesta
        'kpis': {
          'total_en_rango': int,
          'sin_dato': int,
          'vencidos_pendientes': int,
          'familias': int,
        }
      }

    Cada equipo: {'id', 'vehiculo', 'familia', 'rutina', 'desviacion',
                  'ind_desviacion', 'estado_mp', 'fecha_estimada': date|None,
                  'tipo_medidor': str, 'sin_dato': bool, 'vencido_actual': bool}
    """
    if today is None:
        today = date.today()

    # Construir promedios_map
    promedios_map = {}
    for row in conn.execute("SELECT familia, horas_promedio_dia, km_promedio_dia FROM promedios_familia").fetchall():
        promedios_map[row['familia']] = {
            'horas_promedio_dia': row['horas_promedio_dia'],
            'km_promedio_dia': row['km_promedio_dia'],
        }

    # Obtener último sync_id
    row = conn.execute("SELECT MAX(sync_id) AS msid FROM equipos").fetchone()
    if not row or not row['msid']:
        return {'en_rango': [], 'sin_dato': [], 'vencidos_pendientes': [],
                'kpis': {'total_en_rango': 0, 'sin_dato': 0, 'vencidos_pendientes': 0, 'familias': 0}}

    last_sync = row['msid']

    # IDs de equipos ya con respuesta en este ciclo (ejecutados o con motivo registrado)
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

    # Ordenar en_rango por fecha_estimada ASC
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
    donde homologos es lista de {'codigo_sap', 'descripcion', 'estado'}
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

    # Agrupar por codigo_sap
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

    # Obtener homólogos para cada SAP
    all_saps = list(grupos.keys())
    homo_map = {}
    if all_saps:
        ph2 = ','.join('?' * len(all_saps))
        # Buscar grupo de cada SAP y luego todos los homólogos del grupo
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
```

- [ ] **Step 2: Crear `tests/test_planning_parser.py`**

```python
import pytest
from planning import parse_desviacion


def test_hoy():
    r = parse_desviacion('Hoy')
    assert r == {'tipo': 'dias', 'valor': 0, 'vencido': False}


def test_falta_dias():
    r = parse_desviacion('Falta 17d')
    assert r['tipo'] == 'dias'
    assert r['valor'] == 17
    assert r['vencido'] is False


def test_falta_horas_largo():
    r = parse_desviacion('Falta 43.9 Horas')
    assert r['tipo'] == 'horas'
    assert abs(r['valor'] - 43.9) < 0.01
    assert r['vencido'] is False


def test_falta_horas_corto():
    r = parse_desviacion('Falta 28 H')
    assert r['tipo'] == 'horas'
    assert r['valor'] == 28


def test_falta_hora_singular():
    r = parse_desviacion('Falta 1 Hora')
    assert r['tipo'] == 'horas'
    assert r['valor'] == 1


def test_hace_horas():
    r = parse_desviacion('Hace 46 Horas')
    assert r['tipo'] == 'horas'
    assert r['valor'] == 46
    assert r['vencido'] is True


def test_hace_compuesto():
    r = parse_desviacion('Hace 2y 7M 1d')
    assert r['tipo'] == 'dias'
    assert r['vencido'] is True
    # 2*365 + 7*30 + 1 = 730 + 210 + 1 = 941
    assert abs(r['valor'] - 941) < 1


def test_falta_km():
    r = parse_desviacion('Falta 120 km')
    assert r['tipo'] == 'km'
    assert r['valor'] == 120


def test_none_input():
    assert parse_desviacion(None) is None


def test_empty_string():
    assert parse_desviacion('') is None


def test_unparseable():
    assert parse_desviacion('Sin información') is None


def test_hoy_case_insensitive():
    r = parse_desviacion('hoy')
    assert r is not None
    assert r['valor'] == 0
```

- [ ] **Step 3: Crear `tests/test_planning_calc.py`**

```python
import pytest
from datetime import date
from planning import calcular_fecha_estimada, calcular_planeacion
from models import get_db


TODAY = date(2026, 6, 21)

PROMEDIOS = {
    'PAYMOVER': {'horas_promedio_dia': 8.0, 'km_promedio_dia': None},
    'TRACTOR': {'horas_promedio_dia': None, 'km_promedio_dia': 120.0},
}


def test_fecha_dias_falta():
    parsed = {'tipo': 'dias', 'valor': 10, 'vencido': False}
    r = calcular_fecha_estimada(parsed, 'PAYMOVER', PROMEDIOS, today=TODAY)
    assert r['fecha'] == date(2026, 7, 1)
    assert not r['sin_dato']
    assert not r['vencido']


def test_fecha_dias_hace():
    parsed = {'tipo': 'dias', 'valor': 5, 'vencido': True}
    r = calcular_fecha_estimada(parsed, 'PAYMOVER', PROMEDIOS, today=TODAY)
    assert r['fecha'] == date(2026, 6, 16)
    assert r['vencido'] is True


def test_fecha_horas_con_promedio():
    parsed = {'tipo': 'horas', 'valor': 80, 'vencido': False}
    r = calcular_fecha_estimada(parsed, 'PAYMOVER', PROMEDIOS, today=TODAY)
    # 80h / 8h/dia = 10 dias → 2026-07-01
    assert r['fecha'] == date(2026, 7, 1)
    assert not r['sin_dato']


def test_fecha_horas_sin_promedio():
    parsed = {'tipo': 'horas', 'valor': 80, 'vencido': False}
    r = calcular_fecha_estimada(parsed, 'FAMILIA_SIN_DATO', PROMEDIOS, today=TODAY)
    assert r['fecha'] is None
    assert r['sin_dato'] is True


def test_fecha_none_parsed():
    r = calcular_fecha_estimada(None, 'PAYMOVER', PROMEDIOS, today=TODAY)
    assert r['fecha'] is None
    assert r['sin_dato'] is True


def test_calcular_planeacion_vacio(temp_db):
    conn = get_db()
    r = calcular_planeacion(conn, date(2026, 7, 1), date(2026, 8, 31), False, today=TODAY)
    conn.close()
    assert r['en_rango'] == []
    assert r['kpis']['total_en_rango'] == 0
```

- [ ] **Step 4: Crear `tests/test_planning_repuestos.py`**

```python
import pytest
from planning import agregar_repuestos
from models import get_db


@pytest.fixture
def db_con_filtros(temp_db):
    conn = get_db()
    conn.execute("INSERT INTO filtros_equipo (equipo, tipo, nombre_articulo, codigo_sap, tipo_filtro) VALUES (?, ?, ?, ?, ?)",
                 ('AGPU 21', 'GPU', 'FILTRO ACEITE', '10001', 'Fleetguard'))
    conn.execute("INSERT INTO filtros_equipo (equipo, tipo, nombre_articulo, codigo_sap, tipo_filtro) VALUES (?, ?, ?, ?, ?)",
                 ('AGPU 22', 'GPU', 'FILTRO ACEITE', '10001', 'Fleetguard'))
    conn.execute("INSERT INTO filtros_equipo (equipo, tipo, nombre_articulo, codigo_sap, tipo_filtro) VALUES (?, ?, ?, ?, ?)",
                 ('AGPU 21', 'GPU', 'FILTRO AIRE', '20002', 'Fleetguard'))
    conn.commit()
    yield conn
    conn.close()


def test_agrega_por_sap(db_con_filtros):
    r = agregar_repuestos(db_con_filtros, ['AGPU 21', 'AGPU 22'])
    saps = [x['codigo_sap'] for x in r]
    assert '10001' in saps
    aceite = next(x for x in r if x['codigo_sap'] == '10001')
    assert aceite['cantidad'] == 2


def test_lista_vacia(db_con_filtros):
    r = agregar_repuestos(db_con_filtros, [])
    assert r == []


def test_vehiculo_inexistente(db_con_filtros):
    r = agregar_repuestos(db_con_filtros, ['EQUIPO 99'])
    assert r == []


def test_orden_descendente(db_con_filtros):
    r = agregar_repuestos(db_con_filtros, ['AGPU 21', 'AGPU 22'])
    cantidades = [x['cantidad'] for x in r]
    assert cantidades == sorted(cantidades, reverse=True)
```

- [ ] **Step 5: Correr tests**

```bash
python -m pytest tests/test_planning_parser.py tests/test_planning_calc.py tests/test_planning_repuestos.py -v
```

Todos deben pasar.

---

## Task 4: Ruta y template `/admin/planeacion`

**Files:**
- Modify: `app.py` (agregar rutas)
- Create: `templates/admin/planeacion.html`
- Modify: `templates/base.html` (navbar link)

**Interfaces:**
- `GET /admin/planeacion` — renderiza template con estado vacío (sin resultados)
- `GET /admin/planeacion?fd=2026-07-01&fh=2026-09-30&iv=1` — renderiza con resultados calculados
- `POST /admin/planeacion/promedio/<familia>` — AJAX, actualiza promedio, retorna JSON `{'ok': true}`

- [ ] **Step 1: Agregar rutas en `app.py`**

Agregar imports al inicio del archivo si no existen:

```python
from planning import calcular_planeacion, agregar_repuestos
from datetime import date as date_type
```

Agregar rutas antes de `if __name__ == '__main__':`:

```python
@app.route('/admin/planeacion')
@login_required
@admin_required
def admin_planeacion():
    from datetime import date as d_type, datetime
    today = d_type.today()

    # Leer parámetros de calculadora
    fd_str = request.args.get('fd', '')
    fh_str = request.args.get('fh', '')
    iv = request.args.get('iv', '0') == '1'

    resultados = None
    repuestos = []
    fecha_desde = None
    fecha_hasta = None
    error_calc = None

    conn = get_db()

    # Promedios para la sección editable
    promedios = conn.execute(
        """SELECT familia, horas_promedio_dia, km_promedio_dia, updated_at
           FROM promedios_familia ORDER BY familia"""
    ).fetchall()

    # Familias sin promedio (para mostrar badge)
    familias_sin_prom = conn.execute(
        """SELECT DISTINCT familia FROM equipos
           WHERE sync_id = (SELECT MAX(sync_id) FROM equipos)
             AND familia NOT IN (SELECT familia FROM promedios_familia
                                  WHERE horas_promedio_dia IS NOT NULL
                                     OR km_promedio_dia IS NOT NULL)
           ORDER BY familia"""
    ).fetchall()

    if fd_str and fh_str:
        try:
            fecha_desde = datetime.strptime(fd_str, '%Y-%m-%d').date()
            fecha_hasta = datetime.strptime(fh_str, '%Y-%m-%d').date()
            if fecha_desde > fecha_hasta:
                error_calc = 'La fecha desde no puede ser posterior a la fecha hasta.'
            else:
                resultados = calcular_planeacion(conn, fecha_desde, fecha_hasta, iv)
                vehiculos = [e['vehiculo'] for e in resultados['en_rango']]
                if iv:
                    vehiculos += [e['vehiculo'] for e in resultados['vencidos_pendientes']]
                repuestos = agregar_repuestos(conn, list(dict.fromkeys(vehiculos)))
        except ValueError:
            error_calc = 'Formato de fecha inválido. Use YYYY-MM-DD.'

    conn.close()

    return render_template(
        'admin/planeacion.html',
        today=today,
        promedios=promedios,
        familias_sin_prom=[r['familia'] for r in familias_sin_prom],
        fd_str=fd_str,
        fh_str=fh_str,
        iv=iv,
        resultados=resultados,
        repuestos=repuestos,
        error_calc=error_calc,
    )


@app.route('/admin/planeacion/promedio/<familia>', methods=['POST'])
@login_required
@admin_required
def admin_planeacion_promedio(familia):
    from datetime import datetime
    data = request.get_json(silent=True) or {}
    hpd_raw = data.get('horas_promedio_dia')
    kpd_raw = data.get('km_promedio_dia')

    def to_float(v):
        if v is None or str(v).strip() == '':
            return None
        try:
            f = float(v)
            return f if f > 0 else None
        except (ValueError, TypeError):
            return None

    hpd = to_float(hpd_raw)
    kpd = to_float(kpd_raw)
    now = datetime.now().isoformat()

    conn = get_db()
    conn.execute(
        """INSERT INTO promedios_familia (familia, horas_promedio_dia, km_promedio_dia, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(familia) DO UPDATE SET
               horas_promedio_dia = excluded.horas_promedio_dia,
               km_promedio_dia    = excluded.km_promedio_dia,
               updated_at         = excluded.updated_at""",
        (familia, hpd, kpd, now)
    )
    conn.commit()
    conn.close()
    return {'ok': True, 'familia': familia}


@app.route('/admin/planeacion/exportar')
@login_required
@admin_required
def admin_planeacion_exportar():
    from datetime import date as d_type, datetime
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    today = d_type.today()
    fd_str = request.args.get('fd', '')
    fh_str = request.args.get('fh', '')
    iv = request.args.get('iv', '0') == '1'

    try:
        fecha_desde = datetime.strptime(fd_str, '%Y-%m-%d').date()
        fecha_hasta = datetime.strptime(fh_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Fechas inválidas para exportar.', 'error')
        return redirect(url_for('admin_planeacion'))

    conn = get_db()
    resultados = calcular_planeacion(conn, fecha_desde, fecha_hasta, iv)
    vehiculos = [e['vehiculo'] for e in resultados['en_rango']]
    if iv:
        vehiculos += [e['vehiculo'] for e in resultados['vencidos_pendientes']]
    repuestos = agregar_repuestos(conn, list(dict.fromkeys(vehiculos)))
    conn.close()

    wb = Workbook()
    azul = PatternFill('solid', fgColor='002D6E')
    wfont = Font(color='FFFFFF', bold=True, size=11)
    ctr = Alignment(horizontal='center', vertical='center', wrap_text=True)

    # Hoja 1 — Equipos en rango
    ws1 = wb.active
    ws1.title = 'Equipos en Rango'
    ws1.append(['Vehículo', 'Familia', 'Rutina', 'Desviación', 'Ind. Desviación', 'Estado MP', 'Fecha Estimada', 'Tipo Medidor'])
    for cell in ws1[1]:
        cell.fill = azul; cell.font = wfont; cell.alignment = ctr
    for eq in resultados['en_rango']:
        ws1.append([
            eq['vehiculo'], eq['familia'], eq['rutina'], eq['desviacion'],
            eq['ind_desviacion'], eq['estado_mp'],
            eq['fecha_estimada'].isoformat() if eq['fecha_estimada'] else '',
            eq['tipo_medidor'] or '',
        ])

    # Hoja 2 — Vencidos pendientes (si aplica)
    if iv and resultados['vencidos_pendientes']:
        ws2 = wb.create_sheet('Vencidos Pendientes')
        ws2.append(['Vehículo', 'Familia', 'Rutina', 'Desviación', 'Ind. Desviación', 'Estado MP'])
        for cell in ws2[1]:
            cell.fill = azul; cell.font = wfont; cell.alignment = ctr
        for eq in resultados['vencidos_pendientes']:
            ws2.append([
                eq['vehiculo'], eq['familia'], eq['rutina'],
                eq['desviacion'], eq['ind_desviacion'], eq['estado_mp'],
            ])

    # Hoja 3 — Repuestos agregados
    ws3 = wb.create_sheet('Repuestos')
    ws3.append(['Código SAP', 'Artículo', 'Tipo Filtro', 'Cantidad', 'Equipos', 'Homólogos SAP'])
    for cell in ws3[1]:
        cell.fill = azul; cell.font = wfont; cell.alignment = ctr
    for rep in repuestos:
        homos = ', '.join(h['codigo_sap'] for h in rep['homologos'] if h['codigo_sap'] != rep['codigo_sap'])
        ws3.append([
            rep['codigo_sap'], rep['nombre_articulo'], rep['tipo_filtro'],
            rep['cantidad'], ', '.join(rep['equipos']), homos,
        ])

    for ws in [ws1, ws3]:
        for col in ws.columns:
            mx = max((len(str(c.value or '')) for c in col), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(mx + 4, 55)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nombre = f"planeacion_repuestos_{fd_str}_{fh_str}.xlsx"
    return send_file(buf, download_name=nombre, as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
```

- [ ] **Step 2: Agregar link en navbar de `base.html`**

Buscar el bloque del navbar donde están los links de admin (cerca de "Sincronizar", "Usuarios", etc.) y agregar:

```html
{% if current_user.rol in ('admin', 'superadmin') %}
<a href="{{ url_for('admin_planeacion') }}" class="nav-link {% if request.endpoint == 'admin_planeacion' %}active{% endif %}">
  Planeación
</a>
{% endif %}
```

- [ ] **Step 3: Crear `templates/admin/planeacion.html`**

```html
{% extends "base.html" %}

{% block title %}Planeación de Repuestos — Seguimiento MP GET{% endblock %}

{% block styles %}
<style>
  :root {
    --azul: #002D6E; --verde: #80AE3F; --cielo: #1E88E5;
    --ambar: #E67E22; --fondo: #F0F2F5; --gris: #6b7280;
    --rojo: #dc2626;
  }
  .plan-page { max-width: 1100px; margin: 28px auto 60px; padding: 0 20px; }

  .back-link {
    display: inline-flex; align-items: center; gap: 5px;
    color: var(--cielo); text-decoration: none; font-size: 13px;
    font-weight: 500; margin-bottom: 14px;
  }
  .back-link:hover { text-decoration: underline; }
  .back-link svg { width:14px; height:14px; stroke:currentColor; fill:none; stroke-width:2.5; stroke-linecap:round; stroke-linejoin:round; }

  .page-title { font-size:22px; font-weight:700; color:var(--azul); letter-spacing:-0.3px; }
  .page-sub { font-size:13.5px; color:var(--gris); margin-top:5px; line-height:1.5; }

  /* Cards generales */
  .card {
    background:#fff; border-radius:12px;
    box-shadow: 0 2px 16px rgba(0,45,110,0.09);
    margin-top:20px; overflow:hidden;
  }
  .card-header {
    padding:18px 24px 14px; border-bottom:1px solid #f3f4f6;
    display:flex; align-items:center; gap:10px;
  }
  .card-header h2 { font-size:15px; font-weight:700; color:var(--azul); margin:0; }
  .card-body { padding:20px 24px; }

  /* KPI cards */
  .kpi-row { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-bottom:20px; }
  .kpi-card {
    background:#f8faff; border:1px solid #e0e7ef; border-radius:10px;
    padding:14px 16px; text-align:center;
  }
  .kpi-card .kpi-val { font-size:28px; font-weight:800; color:var(--azul); line-height:1; }
  .kpi-card .kpi-val.warn { color: var(--ambar); }
  .kpi-card .kpi-lbl { font-size:11.5px; color:var(--gris); margin-top:4px; }

  /* Promedios inline */
  .prom-table { width:100%; border-collapse:collapse; font-size:13px; }
  .prom-table th { background:var(--azul); color:#fff; padding:8px 12px; text-align:left; font-weight:600; font-size:12px; }
  .prom-table td { padding:8px 12px; border-bottom:1px solid #f3f4f6; vertical-align:middle; }
  .prom-table tr:last-child td { border-bottom:none; }
  .prom-input {
    width:90px; padding:5px 8px; font-size:13px;
    border:1px solid #d1d5db; border-radius:6px;
    text-align:right; outline:none; transition:border-color 0.15s;
  }
  .prom-input:focus { border-color:var(--cielo); box-shadow:0 0 0 2px rgba(30,136,229,0.15); }
  .btn-save-prom {
    padding:5px 12px; font-size:12px; font-weight:600;
    background:var(--azul); color:#fff; border:none;
    border-radius:6px; cursor:pointer; transition:background 0.15s;
  }
  .btn-save-prom:hover { background:#003580; }
  .save-status { font-size:11.5px; margin-left:6px; }
  .save-ok { color:var(--verde); }
  .save-err { color:var(--rojo); }
  .badge-sin-prom {
    display:inline-block; background:#fef3c7; color:#92400e;
    font-size:10px; font-weight:700; padding:1px 7px;
    border-radius:10px; letter-spacing:0.3px; margin-left:5px;
  }

  /* Calculadora */
  .calc-form { display:flex; flex-wrap:wrap; gap:14px; align-items:flex-end; }
  .calc-field { display:flex; flex-direction:column; gap:5px; }
  .calc-field label { font-size:12px; font-weight:600; color:#374151; }
  .calc-field input[type="date"] {
    padding:8px 12px; font-size:13.5px;
    border:1px solid #d1d5db; border-radius:8px;
    outline:none; transition:border-color 0.15s;
  }
  .calc-field input[type="date"]:focus { border-color:var(--cielo); box-shadow:0 0 0 2px rgba(30,136,229,0.15); }
  .calc-check { display:flex; align-items:center; gap:8px; font-size:13px; color:#374151; cursor:pointer; padding-bottom:2px; }
  .calc-check input[type="checkbox"] { width:15px; height:15px; accent-color:var(--azul); cursor:pointer; }
  .btn-calc {
    padding:9px 22px; font-size:14px; font-weight:600;
    background:var(--azul); color:#fff; border:none;
    border-radius:8px; cursor:pointer; transition:background 0.15s, transform 0.1s;
  }
  .btn-calc:hover { background:#003580; }
  .btn-calc:active { transform:scale(0.98); }
  .badge-warn-90 {
    display:inline-flex; align-items:center; gap:5px;
    background:#fffbeb; border:1px solid #fcd34d;
    color:#92400e; font-size:12px; font-weight:600;
    padding:4px 10px; border-radius:8px; margin-left:10px;
  }
  .calc-error { background:#fef2f2; border:1px solid #fca5a5; color:var(--rojo); font-size:13px; padding:10px 14px; border-radius:8px; margin-top:12px; }

  /* Tabla resultados */
  .res-table-wrap { overflow-x:auto; margin-top:4px; }
  .res-table { width:100%; border-collapse:collapse; font-size:13px; }
  .res-table th { background:var(--azul); color:#fff; padding:9px 12px; text-align:left; font-weight:600; font-size:12px; white-space:nowrap; }
  .res-table td { padding:8px 12px; border-bottom:1px solid #f3f4f6; vertical-align:middle; }
  .res-table tr:hover td { background:#f0f7ff; }
  .chip-vencido { background:#fee2e2; color:var(--rojo); font-size:11px; font-weight:700; padding:2px 7px; border-radius:8px; }
  .chip-sin-dato { background:#fef3c7; color:#92400e; font-size:11px; font-weight:700; padding:2px 7px; border-radius:8px; }
  .chip-ok { background:#f0fdf4; color:#166534; font-size:11px; font-weight:700; padding:2px 7px; border-radius:8px; }

  /* Repuestos */
  .rep-table { width:100%; border-collapse:collapse; font-size:13px; }
  .rep-table th { background:var(--azul); color:#fff; padding:9px 12px; text-align:left; font-weight:600; font-size:12px; }
  .rep-table td { padding:8px 12px; border-bottom:1px solid #f3f4f6; vertical-align:middle; }
  .rep-table tr:hover td { background:#f0f7ff; }
  .qty-badge {
    display:inline-block; background:var(--azul); color:#fff;
    font-size:13px; font-weight:800; min-width:28px; text-align:center;
    padding:2px 8px; border-radius:6px;
  }
  .btn-homo-small {
    padding:3px 10px; font-size:11px; font-weight:600;
    background:#f0f7ff; color:var(--azul); border:1px solid #bfdbfe;
    border-radius:6px; cursor:pointer; transition:background 0.15s;
  }
  .btn-homo-small:hover { background:#dbeafe; }
  .homo-inline { display:none; }
  .homo-inner { background:#f8faff; border:1px solid #e0e7ef; border-radius:8px; padding:10px 14px; margin-top:6px; font-size:12px; }
  .homo-inner table { width:100%; border-collapse:collapse; }
  .homo-inner td { padding:4px 8px; border-bottom:1px solid #f0f0f0; }
  .homo-inner tr:last-child td { border-bottom:none; }

  /* Botón exportar */
  .btn-export {
    display:inline-flex; align-items:center; gap:7px;
    padding:9px 20px; font-size:13.5px; font-weight:600;
    background:var(--verde); color:#fff; border:none;
    border-radius:8px; cursor:pointer; text-decoration:none;
    transition:background 0.15s;
  }
  .btn-export:hover { background:#6a9433; }
  .btn-export svg { width:16px; height:16px; stroke:currentColor; fill:none; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }

  .empty-state { text-align:center; padding:40px 24px; color:var(--gris); font-size:13.5px; }
  .empty-state .empty-icon { font-size:36px; margin-bottom:10px; }
</style>
{% endblock %}

{% block content %}
<div class="plan-page">

  <a href="{{ url_for('admin_dashboard') }}" class="back-link">
    <svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>
    Volver al panel
  </a>

  <h1 class="page-title">Planeación de Repuestos Predictiva</h1>
  <p class="page-sub">Calcula fechas estimadas de próximo MP y agrega los repuestos necesarios para un rango de fechas.</p>

  <!-- ===== SECCIÓN 1: Promedios por familia ===== -->
  <div class="card">
    <div class="card-header">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#002D6E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
      </svg>
      <h2>Promedios de Consumo por Familia</h2>
    </div>
    <div class="card-body">
      <p style="font-size:12.5px;color:var(--gris);margin-bottom:14px;">
        Ingrese el promedio diario de horas o km por familia. Se usa para convertir desviaciones en horas/km a fechas estimadas.
      </p>

      {% if familias_sin_prom %}
      <div style="background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;padding:10px 14px;margin-bottom:14px;font-size:12.5px;color:#92400e;">
        <strong>Familias sin promedio configurado:</strong>
        {% for f in familias_sin_prom %}<span class="badge-sin-prom">{{ f }}</span>{% endfor %}
      </div>
      {% endif %}

      {% if promedios %}
      <table class="prom-table">
        <thead>
          <tr>
            <th>Familia</th>
            <th>Horas / día</th>
            <th>Km / día</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {% for p in promedios %}
          <tr id="prom-row-{{ loop.index }}">
            <td><strong>{{ p.familia }}</strong></td>
            <td>
              <input class="prom-input" type="number" step="0.1" min="0"
                     id="hpd-{{ loop.index }}"
                     value="{{ p.horas_promedio_dia if p.horas_promedio_dia else '' }}"
                     placeholder="—">
            </td>
            <td>
              <input class="prom-input" type="number" step="1" min="0"
                     id="kpd-{{ loop.index }}"
                     value="{{ p.km_promedio_dia if p.km_promedio_dia else '' }}"
                     placeholder="—">
            </td>
            <td>
              <button class="btn-save-prom" onclick="saveProm('{{ p.familia | e }}', {{ loop.index }})">Guardar</button>
              <span class="save-status" id="st-{{ loop.index }}"></span>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      {% else %}
      <div class="empty-state">
        <div class="empty-icon">📊</div>
        <p>No hay familias registradas aún. Sincronice la programación MP para poblar las familias.</p>
      </div>
      {% endif %}
    </div>
  </div>

  <!-- ===== SECCIÓN 2: Calculadora ===== -->
  <div class="card">
    <div class="card-header">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#002D6E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
      </svg>
      <h2>Calculadora de Rango</h2>
    </div>
    <div class="card-body">
      <form method="GET" action="{{ url_for('admin_planeacion') }}">
        <div class="calc-form">
          <div class="calc-field">
            <label>Fecha desde</label>
            <input type="date" name="fd" value="{{ fd_str }}" required>
          </div>
          <div class="calc-field">
            <label>Fecha hasta</label>
            <input type="date" name="fh" value="{{ fh_str }}" required>
          </div>
          <label class="calc-check">
            <input type="checkbox" name="iv" value="1" {% if iv %}checked{% endif %}>
            Incluir equipos vencidos pendientes
          </label>
          <button type="submit" class="btn-calc">Calcular</button>

          {% if fd_str and fh_str %}
          {% set dias_rango = ((fh_str | string) | length) %}
          <span class="badge-warn-90" title="Rango seleccionado">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {{ fd_str }} → {{ fh_str }}
          </span>
          {% endif %}
        </div>
      </form>

      {% if error_calc %}
      <div class="calc-error">{{ error_calc }}</div>
      {% endif %}
    </div>
  </div>

  {% if resultados %}
  <!-- ===== SECCIÓN 3: KPIs + Tabla resultados ===== -->
  <div class="card">
    <div class="card-header">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#002D6E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
      </svg>
      <h2>Resultados — {{ fd_str }} al {{ fh_str }}</h2>

      <a href="{{ url_for('admin_planeacion_exportar', fd=fd_str, fh=fh_str, iv='1' if iv else '0') }}"
         class="btn-export" style="margin-left:auto;">
        <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        Exportar Excel
      </a>
    </div>
    <div class="card-body">

      <!-- KPIs -->
      <div class="kpi-row">
        <div class="kpi-card">
          <div class="kpi-val">{{ resultados.kpis.total_en_rango }}</div>
          <div class="kpi-lbl">Equipos en rango</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val">{{ resultados.kpis.familias }}</div>
          <div class="kpi-lbl">Familias</div>
        </div>
        {% if iv %}
        <div class="kpi-card">
          <div class="kpi-val warn">{{ resultados.kpis.vencidos_pendientes }}</div>
          <div class="kpi-lbl">Vencidos pendientes</div>
        </div>
        {% endif %}
        <div class="kpi-card">
          <div class="kpi-val warn">{{ resultados.kpis.sin_dato }}</div>
          <div class="kpi-lbl">Sin dato de promedio</div>
        </div>
      </div>

      <!-- Tabla en rango -->
      {% if resultados.en_rango %}
      <div class="res-table-wrap">
        <table class="res-table">
          <thead>
            <tr>
              <th>Vehículo</th><th>Familia</th><th>Rutina</th>
              <th>Desviación</th><th>Estado MP</th>
              <th>Fecha Estimada</th><th>Medidor</th>
            </tr>
          </thead>
          <tbody>
            {% for eq in resultados.en_rango %}
            <tr>
              <td><strong>{{ eq.vehiculo }}</strong></td>
              <td>{{ eq.familia }}</td>
              <td style="font-size:12px;max-width:260px;">{{ eq.rutina }}</td>
              <td>{{ eq.desviacion }}</td>
              <td>{{ eq.estado_mp }}</td>
              <td>
                {% if eq.fecha_estimada %}
                  {% if eq.vencido_actual %}
                    <span class="chip-vencido">{{ eq.fecha_estimada }}</span>
                  {% else %}
                    <span class="chip-ok">{{ eq.fecha_estimada }}</span>
                  {% endif %}
                {% else %}
                  <span class="chip-sin-dato">Sin dato</span>
                {% endif %}
              </td>
              <td>{{ eq.tipo_medidor or '—' }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% else %}
      <div class="empty-state">
        <div class="empty-icon">📅</div>
        <p>No hay equipos en el rango de fechas seleccionado.</p>
      </div>
      {% endif %}

      <!-- Vencidos pendientes -->
      {% if iv and resultados.vencidos_pendientes %}
      <h3 style="font-size:14px;font-weight:700;color:var(--rojo);margin:20px 0 10px;">
        Vencidos Pendientes ({{ resultados.vencidos_pendientes | length }})
      </h3>
      <div class="res-table-wrap">
        <table class="res-table">
          <thead>
            <tr>
              <th>Vehículo</th><th>Familia</th><th>Rutina</th>
              <th>Desviación</th><th>Estado MP</th><th>Fecha Estimada</th>
            </tr>
          </thead>
          <tbody>
            {% for eq in resultados.vencidos_pendientes %}
            <tr>
              <td><strong>{{ eq.vehiculo }}</strong></td>
              <td>{{ eq.familia }}</td>
              <td style="font-size:12px;">{{ eq.rutina }}</td>
              <td>{{ eq.desviacion }}</td>
              <td>{{ eq.estado_mp }}</td>
              <td><span class="chip-vencido">{{ eq.fecha_estimada or 'Vencido' }}</span></td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% endif %}

    </div>
  </div>

  <!-- ===== SECCIÓN 4: Repuestos agregados ===== -->
  {% if repuestos %}
  <div class="card">
    <div class="card-header">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#002D6E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
      </svg>
      <h2>Repuestos Requeridos — Agregado por SAP</h2>
    </div>
    <div class="card-body">
      <table class="rep-table">
        <thead>
          <tr>
            <th>#</th><th>Código SAP</th><th>Artículo</th>
            <th>Tipo</th><th>Cant.</th><th>Equipos</th><th>Homólogos</th>
          </tr>
        </thead>
        <tbody>
          {% for rep in repuestos %}
          <tr>
            <td style="color:var(--gris);font-size:12px;">{{ loop.index }}</td>
            <td style="font-family:monospace;font-size:13px;">{{ rep.codigo_sap }}</td>
            <td>{{ rep.nombre_articulo }}</td>
            <td>{{ rep.tipo_filtro }}</td>
            <td><span class="qty-badge">{{ rep.cantidad }}</span></td>
            <td style="font-size:12px;color:var(--gris);">{{ rep.equipos | join(', ') }}</td>
            <td>
              {% if rep.homologos | length > 1 %}
              <button class="btn-homo-small" id="hbtn-{{ loop.index }}"
                      onclick="toggleHomRep({{ loop.index }}, {{ rep.homologos | length - 1 }})">
                Ver ({{ rep.homologos | length - 1 }})
              </button>
              <div class="homo-inline" id="homo-rep-{{ loop.index }}">
                <div class="homo-inner">
                  <table>
                    {% for h in rep.homologos %}
                    {% if h.codigo_sap != rep.codigo_sap %}
                    <tr>
                      <td style="font-family:monospace;font-size:12px;">{{ h.codigo_sap }}</td>
                      <td style="font-size:12px;">{{ h.descripcion or '—' }}</td>
                      <td style="font-size:11px;color:var(--gris);">{{ h.estado or '' }}</td>
                    </tr>
                    {% endif %}
                    {% endfor %}
                  </table>
                </div>
              </div>
              {% else %}
              <span style="font-size:12px;color:var(--gris);">—</span>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  {% endif %}

  {% endif %}{# /if resultados #}

</div>
{% endblock %}

{% block scripts %}
<script>
function getCsrfToken() {
  var m = document.querySelector('meta[name="csrf-token"]');
  return m ? m.getAttribute('content') : '';
}

function saveProm(familia, idx) {
  var hpd = document.getElementById('hpd-' + idx).value;
  var kpd = document.getElementById('kpd-' + idx).value;
  var st  = document.getElementById('st-' + idx);
  st.textContent = 'Guardando...';
  st.className = 'save-status';

  fetch('/admin/planeacion/promedio/' + encodeURIComponent(familia), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken()
    },
    body: JSON.stringify({ horas_promedio_dia: hpd || null, km_promedio_dia: kpd || null })
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.ok) {
      st.textContent = 'Guardado';
      st.className = 'save-status save-ok';
    } else {
      st.textContent = 'Error';
      st.className = 'save-status save-err';
    }
    setTimeout(function() { st.textContent = ''; }, 2500);
  })
  .catch(function() {
    st.textContent = 'Error de red';
    st.className = 'save-status save-err';
  });
}

function toggleHomRep(idx, count) {
  var div = document.getElementById('homo-rep-' + idx);
  var btn = document.getElementById('hbtn-' + idx);
  if (!div) return;
  var open = div.style.display === 'block';
  div.style.display = open ? 'none' : 'block';
  if (btn) btn.textContent = open ? ('Ver (' + count + ')') : ('Ocultar (' + count + ')');
}
</script>
{% endblock %}

{% block help_tips %}
<li>Configure los promedios de horas o km por día por familia para calcular fechas</li>
<li>Seleccione un rango de fechas y presione Calcular para ver los equipos</li>
<li>Active "Incluir vencidos" para agregar equipos ya vencidos sin respuesta</li>
<li>Use Exportar Excel para descargar la tabla de repuestos consolidada</li>
{% endblock %}
```

---

## Task 5: Promedios auto-poblados desde familias activas

**Files:**
- Modify: `app.py` (ruta `admin_planeacion`, sección de promedios)

**Nota:** El template ya muestra familias sin promedio. Este task asegura que todas las familias activas del último sync aparezcan como filas editables, incluso si no tienen promedio guardado.

- [ ] **Step 1: Ampliar query de promedios en `admin_planeacion`**

Reemplazar la query de promedios por una que hace FULL OUTER JOIN (simulado con UNION en SQLite):

```python
    # Promedios: incluye todas las familias del último sync, con o sin promedio
    promedios = conn.execute(
        """SELECT f.familia,
                  p.horas_promedio_dia,
                  p.km_promedio_dia,
                  p.updated_at
           FROM (
               SELECT DISTINCT familia FROM equipos
               WHERE sync_id = (SELECT MAX(sync_id) FROM equipos)
                 AND familia IS NOT NULL
           ) f
           LEFT JOIN promedios_familia p ON p.familia = f.familia
           ORDER BY f.familia"""
    ).fetchall()
```

Con esto, todas las familias activas aparecen como filas (con o sin dato), eliminando la necesidad del badge de "familias_sin_prom" separado — aunque se puede mantener para el aviso visual.

---

## Task 6: Verificación E2E y commit

**Files:** Solo verificación, sin cambios de código.

- [ ] **Step 1: Correr todos los tests**

```bash
python -m pytest tests/ -v
```

Todos deben pasar.

- [ ] **Step 2: Iniciar servidor y verificar manualmente**

```bash
python app.py
```

Verificar:
1. Login como admin → navbar muestra "Planeación"
2. Ir a `/admin/planeacion` → muestra tabla de promedios con familias
3. Editar un promedio → botón Guardar muestra "Guardado" sin recargar
4. Seleccionar rango de fechas → presionar Calcular → tabla de resultados aparece
5. Activar "Incluir vencidos" → sección de vencidos aparece
6. Botón "Exportar Excel" → descarga archivo con 3 hojas
7. Ir a `/admin/sync` → cuarta sección de upload "Frecuencias de Rutinas" aparece

- [ ] **Step 3: Commit**

```bash
git add planning.py models.py sync_data.py app.py templates/admin/planeacion.html templates/admin/sync.html templates/base.html tests/
git commit -m "Planeación de Repuestos Predictiva: calculadora fecha estimada MP + agregado repuestos por SAP"
```
