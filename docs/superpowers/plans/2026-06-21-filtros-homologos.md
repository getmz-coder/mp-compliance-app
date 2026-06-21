# Filtros Homólogos — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar catálogo de homólogos de filtros con sync desde Excel, visualización expandible en ficha de equipo, y hoja de exportación adicional.

**Architecture:** Server-rendered Jinja2. La ruta `equipo_detalle` carga los homólogos de una sola query JOIN y los pasa al template como dict `{filtro_id: [rows]}`. El toggle usa JS puro embebido, sin AJAX ni CDN.

**Tech Stack:** Python 3.11, Flask, SQLite (sqlite3), pandas + openpyxl para ETL, Jinja2 templates.

## Global Constraints

- Zero CDN — todo CSS/JS embebido en el template, nada externo
- Branding Talma: Azul `#002D6E`, Verde `#80AE3F`, Cielo `#1E88E5`, Ámbar `#E67E22`, Fondo `#F0F2F5`
- Español en UI y docstrings; inglés en variables y funciones de Python
- Commits en español, descriptivos
- La app no modifica datos fuente Excel (solo lectura)
- Base de datos: `data/app.db` vía `config.DATABASE_PATH`

---

## File Map

| Archivo | Cambio |
|---|---|
| `models.py` | Agregar `CREATE TABLE IF NOT EXISTS homologos` en `executescript` de `init_db()` |
| `sync_data.py` | Agregar `COLS_HOMOLOGOS` y función `sync_homologos(filepath)` |
| `app.py` | (1) Route `admin_sync`: agregar `file_homologos` handling; (2) Route `equipo_detalle`: agregar query + `homologos_map`; (3) Route `exportar_ficha_equipo`: agregar hoja Homólogos |
| `templates/admin/sync.html` | Agregar CSS `.section-icon.amber` + tercera sección de upload |
| `templates/equipo_detalle.html` | Agregar CSS homólogos + botón expand en celda SAP + fila expand + JS `toggleHomologos()` |
| `tests/conftest.py` | **Crear** — fixture de BD temporal para tests |
| `tests/test_homologos.py` | **Crear** — tests para tabla y ETL |

---

## Task 1: Tabla `homologos` en BD

**Files:**
- Modify: `models.py` (función `init_db`, bloque `executescript`)
- Create: `tests/conftest.py`
- Create: `tests/test_homologos.py`

**Interfaces:**
- Produces: tabla `homologos(id, grupo, codigo_sap, descripcion, estado)` en SQLite

- [ ] **Step 1: Crear `tests/conftest.py`**

```python
import os
import pytest
import config
import models


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'test.db')
    monkeypatch.setattr(config, 'DATABASE_PATH', db_path)
    models.init_db()
    yield db_path
```

- [ ] **Step 2: Escribir el test que falla**

Agregar a `tests/test_homologos.py`:

```python
from models import get_db


def test_tabla_homologos_existe():
    conn = get_db()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(homologos)")}
    conn.close()
    assert cols == {'id', 'grupo', 'codigo_sap', 'descripcion', 'estado'}
```

- [ ] **Step 3: Ejecutar para verificar que falla**

```
cd "C:/Users/Aprendiz Get MZ/OneDrive - LASA/Trabajo/Claude CODE/Proyecto_APP_Planeacion"
python -m pytest tests/test_homologos.py::test_tabla_homologos_existe -v
```

Resultado esperado: `FAILED` — tabla no existe aún.

- [ ] **Step 4: Agregar la tabla en `models.py`**

En `models.py`, dentro de `init_db()`, en el `executescript`, agregar **después del bloque `filtros_equipo`** (después de la línea `tipo_filtro     VARCHAR(50)` y antes de `CREATE TABLE IF NOT EXISTS solicitudes`):

```sql
        CREATE TABLE IF NOT EXISTS homologos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo       INTEGER,
            codigo_sap  VARCHAR(30),
            descripcion VARCHAR(200),
            estado      VARCHAR(50)
        );
```

El bloque completo queda así (mostrado con contexto):
```python
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

        CREATE TABLE IF NOT EXISTS solicitudes (
```

- [ ] **Step 5: Ejecutar tests para verificar que pasa**

```
python -m pytest tests/test_homologos.py::test_tabla_homologos_existe -v
```

Resultado esperado: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add models.py tests/conftest.py tests/test_homologos.py
git commit -m "feat: tabla homologos en BD e infraestructura de tests"
```

---

## Task 2: ETL `sync_homologos()`

**Files:**
- Modify: `sync_data.py`
- Modify: `tests/test_homologos.py`

**Interfaces:**
- Consumes: `get_db()` de `models`, `_clean()`, `_clean_sap()` (ya existen en `sync_data.py`)
- Produces: `sync_homologos(filepath: str) -> dict` con claves `total_registros: int`, `grupos: int`

- [ ] **Step 1: Agregar el test**

Al final de `tests/test_homologos.py`:

```python
import os
import openpyxl
from sync_data import sync_homologos
from models import get_db


def _make_homo_excel(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Grupos_Homologos'
    ws.append(['Grupo', 'Tamaño Grupo', 'Estado', 'Codigo SAP', 'Descripcion'])
    ws.append(['1', '2', 'Ya correcto', '10045678', 'FILTRO ACEITE MOTOR'])
    ws.append(['1', '2', 'Revisar',     '10045679', 'FILTRO ACEITE ALTERNATIVO'])
    ws.append(['2', '1', 'Ya correcto', '20001234', 'FILTRO HIDRAULICO'])
    wb.save(path)


def test_sync_homologos_inserta(tmp_path):
    path = str(tmp_path / 'homo.xlsx')
    _make_homo_excel(path)

    result = sync_homologos(path)

    assert result['total_registros'] == 3
    assert result['grupos'] == 2

    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM homologos ORDER BY grupo, codigo_sap'
    ).fetchall()
    conn.close()

    assert len(rows) == 3
    assert rows[0]['grupo'] == 1
    assert rows[0]['codigo_sap'] == '10045678'
    assert rows[0]['estado'] == 'Ya correcto'
    assert rows[2]['grupo'] == 2


def test_sync_homologos_reemplaza(tmp_path):
    """Segunda sync borra los anteriores y carga los nuevos."""
    path = str(tmp_path / 'homo.xlsx')
    _make_homo_excel(path)
    sync_homologos(path)

    # Segunda sync con datos distintos
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Grupos_Homologos'
    ws.append(['Grupo', 'Tamaño Grupo', 'Estado', 'Codigo SAP', 'Descripcion'])
    ws.append(['5', '1', 'Revisar', '99990001', 'FILTRO NUEVO'])
    wb.save(path)
    result = sync_homologos(path)

    assert result['total_registros'] == 1
    assert result['grupos'] == 1

    conn = get_db()
    count = conn.execute('SELECT COUNT(*) FROM homologos').fetchone()[0]
    conn.close()
    assert count == 1


def test_sync_homologos_columna_faltante(tmp_path):
    """Lanza ValueError si faltan columnas requeridas."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Grupos_Homologos'
    ws.append(['Grupo', 'Estado'])  # faltan Codigo SAP y Descripcion
    path = str(tmp_path / 'bad.xlsx')
    wb.save(path)

    import pytest as _pytest
    with _pytest.raises(ValueError, match='Columnas faltantes'):
        sync_homologos(path)
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

```
python -m pytest tests/test_homologos.py -v -k "sync"
```

Resultado esperado: 3 tests `FAILED` — función no existe aún.

- [ ] **Step 3: Implementar `sync_homologos()` en `sync_data.py`**

Agregar **después de la constante `COLS_FILTROS`** (línea 14):

```python
COLS_HOMOLOGOS = ['Grupo', 'Estado', 'Codigo SAP', 'Descripcion']
```

Agregar **al final de `sync_data.py`** (después de la función `sync_filtros`):

```python
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
```

- [ ] **Step 4: Ejecutar tests para verificar que pasan**

```
python -m pytest tests/test_homologos.py -v
```

Resultado esperado: todos `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add sync_data.py tests/test_homologos.py
git commit -m "feat: ETL sync_homologos desde hoja Grupos_Homologos del Excel"
```

---

## Task 3: Route `/admin/sync` + template

**Files:**
- Modify: `app.py` — route `admin_sync` (líneas 420–483)
- Modify: `templates/admin/sync.html`

**Interfaces:**
- Consumes: `sync_data.sync_homologos(filepath)` → `{'total_registros': int, 'grupos': int}`
- Produces: campo `file_homologos` en el formulario POST; flash de éxito/error

- [ ] **Step 1: Agregar CSS amber en `templates/admin/sync.html`**

Localizar en `templates/admin/sync.html` la línea:
```css
  .section-icon.green svg { stroke: var(--verde); }
```
Después de ella, agregar:
```css
  .section-icon.amber { background: #fffbeb; }
  .section-icon.amber svg { stroke: var(--ambar); }
```

- [ ] **Step 2: Agregar tercera sección de upload en `templates/admin/sync.html`**

Localizar el comentario `<!-- Maestro Filtración -->` y su `</div>` de cierre (el `</div>` que cierra ese `upload-section`, antes de `<div class="form-footer">`).

Después de ese `</div>`, antes de `<div class="form-footer">`, agregar:

```html
      <!-- Homólogos de Filtros -->
      <div class="upload-section">
        <div class="section-header">
          <div class="section-icon amber">
            <svg viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <div class="section-info">
            <h3>Homólogos de Filtros <span class="badge-optional">Opcional</span></h3>
            <p>Catálogo de equivalencias entre códigos SAP. Reemplaza completamente la tabla existente al subir un nuevo archivo.</p>
          </div>
        </div>

        <div class="file-zone" id="zone-homo">
          <input type="file" name="file_homologos" accept=".xlsx,.xls"
                 onchange="setFile(this,'zone-homo','name-homo')">
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
              <div class="fz-name" id="name-homo"></div>
            </div>
          </div>
        </div>

        <p class="cols-hint">
          Columnas requeridas: <code>Grupo</code> · <code>Tamaño Grupo</code> · <code>Estado</code> · <code>Codigo SAP</code> · <code>Descripcion</code>
        </p>
      </div>
```

- [ ] **Step 3: Actualizar el texto del pie en `templates/admin/sync.html`**

Localizar:
```html
        <span class="form-note">Se debe subir al menos uno de los dos archivos.</span>
```
Reemplazar con:
```html
        <span class="form-note">Se debe subir al menos uno de los tres archivos.</span>
```

- [ ] **Step 4: Actualizar route `admin_sync` en `app.py`**

Localizar en `app.py` (alrededor de la línea 427):
```python
    file_filt = request.files.get('file_filtros')

    has_prog = file_prog and file_prog.filename
    has_filt = file_filt and file_filt.filename

    if not has_prog and not has_filt:
```

Reemplazar con:
```python
    file_filt = request.files.get('file_filtros')
    file_homo = request.files.get('file_homologos')

    has_prog = file_prog and file_prog.filename
    has_filt = file_filt and file_filt.filename
    has_homo = file_homo and file_homo.filename

    if not has_prog and not has_filt and not has_homo:
```

- [ ] **Step 5: Agregar bloque de procesamiento para homólogos en `app.py`**

Localizar el bloque `if has_filt:` que cierra con:
```python
    return redirect(url_for('admin_sync'))
```

Antes de ese `return`, agregar:

```python
    if has_homo:
        if not _allowed_excel(file_homo.filename):
            flash('Homólogos: formato no válido. Solo se aceptan .xlsx o .xls', 'error')
        else:
            save_path = os.path.join(config.UPLOAD_FOLDER, 'maestro_homologos.xlsx')
            file_homo.save(save_path)
            try:
                res = sync_data.sync_homologos(save_path)
                msg = (f'Homólogos sincronizados: {res["total_registros"]} registros, '
                       f'{res["grupos"]} grupos')
                flash(msg, 'success')
            except Exception as exc:
                flash(f'Error en homólogos: {exc}', 'error')
            else:
                try:
                    os.remove(save_path)
                except Exception as exc:
                    app.logger.error('No se pudo eliminar maestro_homologos.xlsx: %s', exc)
```

- [ ] **Step 6: Verificación manual**

1. Arrancar la app: `python app.py`
2. Iniciar sesión como `admin`.
3. Ir a **Sincronizar Datos**.
4. Verificar que aparece la tercera sección "Homólogos de Filtros" con ícono ámbar.
5. Subir un Excel con hoja `Grupos_Homologos` (columnas: `Grupo`, `Tamaño Grupo`, `Estado`, `Codigo SAP`, `Descripcion`).
6. Verificar flash de éxito con conteo de registros y grupos.

- [ ] **Step 7: Commit**

```bash
git add app.py templates/admin/sync.html
git commit -m "feat: tercer campo de upload para homólogos en sync admin"
```

---

## Task 4: Route `equipo_detalle` — query + `homologos_map`

**Files:**
- Modify: `app.py` — función `equipo_detalle` (alrededor de la línea 1729)

**Interfaces:**
- Consumes: tabla `homologos`, tabla `filtros_equipo`
- Produces: `homologos_map: dict[int, list[sqlite3.Row]]` — keyed by `filtro_id`; pasado al template como `homologos_map`

- [ ] **Step 1: Agregar query y construcción de `homologos_map`**

En `app.py`, en la función `equipo_detalle`, localizar el bloque:
```python
    filtros = conn.execute(
        """SELECT * FROM filtros_equipo
           WHERE UPPER(equipo) = ?
           ORDER BY tipo_filtro, nombre_articulo""",
        (vehiculo,)
    ).fetchall()
```

Después de ese bloque (después de `.fetchall()`), agregar:

```python
    homologos_raw = conn.execute("""
        SELECT h.grupo, h.codigo_sap, h.descripcion, h.estado,
               f.id AS filtro_id
        FROM filtros_equipo f
        JOIN homologos h ON h.grupo = (
            SELECT grupo FROM homologos
            WHERE codigo_sap = f.codigo_sap LIMIT 1
        )
        WHERE UPPER(f.equipo) = ?
        ORDER BY h.grupo, h.estado DESC, h.codigo_sap
    """, (vehiculo,)).fetchall()

    homologos_map = {}
    for _hrow in homologos_raw:
        homologos_map.setdefault(_hrow['filtro_id'], []).append(_hrow)
```

- [ ] **Step 2: Pasar `homologos_map` al template**

Localizar la llamada `return render_template('equipo_detalle.html', ...)` en `equipo_detalle`. Agregar `homologos_map=homologos_map` a los argumentos. Ejemplo de cómo queda:

```python
    return render_template('equipo_detalle.html',
        vehiculo=vehiculo,
        equipo=equipo_base,
        rutinas=rutinas,
        filtros=filtros,
        homologos_map=homologos_map,
        historial=historial,
        sugerencias=sugerencias,
        cambios_filtros=cambios_filtros,
        from_page=from_page,
        hist_stats=hist_stats,
    )
```

- [ ] **Step 3: Verificación manual**

1. Arrancar la app y navegar a `/equipo/<VEHICULO>` de un equipo que tenga filtros con `codigo_sap` en la tabla `homologos`.
2. En el debugger o con `{{ homologos_map }}` temporal en el template, verificar que `homologos_map` llega con datos.
3. Si la tabla `homologos` está vacía (aún no se ha sincronizado), `homologos_map` debe ser `{}` — la página debe seguir cargando sin error.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: query homologos_map en equipo_detalle"
```

---

## Task 5: Template UI expandible

**Files:**
- Modify: `templates/equipo_detalle.html`

**Interfaces:**
- Consumes: `homologos_map` pasado desde `equipo_detalle`; variable de template `filtros`
- Produces: botón "▼ Ver homólogos (N)" en celda SAP; fila expandible con sub-tabla de homólogos

- [ ] **Step 1: Agregar CSS de homólogos**

En `templates/equipo_detalle.html`, localizar la línea:
```css
  @media (max-width: 768px) {
```
Antes de ella, agregar el bloque CSS:

```css
  /* ── Homólogos expandibles ── */
  .homo-expand-btn {
    background: none;
    border: 1px solid var(--borde);
    color: var(--cielo);
    font-size: 11.5px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 20px;
    cursor: pointer;
    white-space: nowrap;
    margin-top: 5px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    transition: background 0.15s, border-color 0.15s;
  }
  .homo-expand-btn:hover { background: #eff6ff; border-color: var(--cielo); }
  .homo-row-inner {
    padding: 10px 14px 14px;
    background: #f8fafc;
    border-top: 1px solid #e5e7eb;
  }
  .homo-inner-title {
    font-size: 11px;
    font-weight: 700;
    color: var(--gris);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
  }
  .homo-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  .homo-table th {
    text-align: left;
    font-size: 11px;
    font-weight: 700;
    color: var(--gris);
    text-transform: uppercase;
    letter-spacing: 0.4px;
    padding: 6px 10px;
    background: #f1f5f9;
    border-bottom: 1px solid var(--borde);
  }
  .homo-table td {
    padding: 7px 10px;
    border-bottom: 1px solid #f3f4f6;
    vertical-align: middle;
  }
  .homo-table tbody tr:last-child td { border-bottom: none; }
  .homo-table tr.homo-principal td { background: #f0fdf4; }
  .homo-principal-chip {
    display: inline-block;
    background: var(--verde);
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: 8px;
    letter-spacing: 0.3px;
    margin-left: 6px;
    vertical-align: middle;
  }
  .badge-ya-correcto {
    display: inline-block;
    background: #f0fdf4;
    color: #14532d;
    border: 1px solid #86efac;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
  }
  .badge-revisar {
    display: inline-block;
    background: #fffbeb;
    color: #92400e;
    border: 1px solid #fde68a;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
  }
```

- [ ] **Step 2: Agregar columna "Homólogos" en el thead de la tabla de filtros**

Localizar en `templates/equipo_detalle.html`:
```html
            <tr>
              <th>Tipo Filtro</th>
              <th>Nombre Artículo</th>
              <th>Código SAP</th>
              {% if current_user.rol in ('admin', 'superadmin') %}
              <th style="width:90px;"></th>
              {% endif %}
            </tr>
```

Reemplazar con:
```html
            <tr>
              <th>Tipo Filtro</th>
              <th>Nombre Artículo</th>
              <th>Código SAP</th>
              <th style="width:130px;">Homólogos</th>
              {% if current_user.rol in ('admin', 'superadmin') %}
              <th style="width:90px;"></th>
              {% endif %}
            </tr>
```

- [ ] **Step 3: Modificar la celda SAP para agregar botón expand**

Localizar:
```html
              <td id="fcell-sap-{{ f.id }}" style="font-family:monospace;font-size:12.5px;color:var(--gris);">{{ f.codigo_sap or '—' }}</td>
```

Reemplazar con:
```html
              <td id="fcell-sap-{{ f.id }}" style="font-family:monospace;font-size:12.5px;color:var(--gris);">{{ f.codigo_sap or '—' }}</td>
              <td>
                {% if f.id in homologos_map %}
                <button class="homo-expand-btn"
                        id="homo-btn-{{ f.id }}"
                        data-count="{{ homologos_map[f.id]|length }}"
                        onclick="toggleHomologos({{ f.id }})">
                  &#9660; Ver hom&#243;logos ({{ homologos_map[f.id]|length }})
                </button>
                {% endif %}
              </td>
```

- [ ] **Step 4: Ajustar la fila de edición admin para el colspan correcto**

Localizar:
```html
            {% if current_user.rol in ('admin', 'superadmin') %}
            <tr id="erow-{{ f.id }}" style="display:none;">
              <td colspan="4" style="padding:6px 10px;">
```

Reemplazar `colspan="4"` con `colspan="5"` (ahora son 5 columnas para admin):
```html
            {% if current_user.rol in ('admin', 'superadmin') %}
            <tr id="erow-{{ f.id }}" style="display:none;">
              <td colspan="5" style="padding:6px 10px;">
```

- [ ] **Step 5: Agregar la fila expandible de homólogos**

Localizar el bloque que cierra el `{% endfor %}` de filtros. Justo antes del `{% endfor %}` (después de `{% endif %}` que cierra el bloque admin de erow), agregar:

```html
            {% if f.id in homologos_map %}
            <tr id="homo-row-{{ f.id }}" style="display:none;">
              <td colspan="10" style="padding:0;">
                <div class="homo-row-inner">
                  <div class="homo-inner-title">Hom&#243;logos del grupo</div>
                  <table class="homo-table">
                    <thead>
                      <tr>
                        <th>C&#243;digo SAP</th>
                        <th>Descripci&#243;n</th>
                        <th>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {% for h in homologos_map[f.id] %}
                      <tr {% if h.codigo_sap == f.codigo_sap %}class="homo-principal"{% endif %}>
                        <td style="font-family:monospace;font-size:12.5px;">
                          {{ h.codigo_sap or '—' }}
                          {% if h.codigo_sap == f.codigo_sap %}
                            <span class="homo-principal-chip">Principal</span>
                          {% endif %}
                        </td>
                        <td>{{ h.descripcion or '—' }}</td>
                        <td>
                          {% if h.estado == 'Ya correcto' %}
                            <span class="badge-ya-correcto">Ya correcto</span>
                          {% elif h.estado == 'Revisar' %}
                            <span class="badge-revisar">Revisar</span>
                          {% else %}
                            <span style="color:var(--gris);font-size:12px;">{{ h.estado or '—' }}</span>
                          {% endif %}
                        </td>
                      </tr>
                      {% endfor %}
                    </tbody>
                  </table>
                </div>
              </td>
            </tr>
            {% endif %}
```

El orden completo del `{% for f in filtros %}` debe quedar:

```
{% for f in filtros %}
  <tr id="frow-{{ f.id }}"> ... </tr>         ← fila principal (siempre)
  {% if admin %}
  <tr id="erow-{{ f.id }}"> ... </tr>          ← fila edición (solo admin)
  {% endif %}
  {% if f.id in homologos_map %}
  <tr id="homo-row-{{ f.id }}"> ... </tr>      ← fila homólogos (si tiene)
  {% endif %}
{% endfor %}
```

- [ ] **Step 6: Agregar función JS `toggleHomologos`**

En `templates/equipo_detalle.html`, dentro del bloque `{% block scripts %}`, **al final del script existente** (antes del cierre `</script>`), agregar:

```javascript
  function toggleHomologos(filtroId) {
    var row = document.getElementById('homo-row-' + filtroId);
    var btn = document.getElementById('homo-btn-' + filtroId);
    var count = btn.getAttribute('data-count');
    if (row.style.display === 'none') {
      row.style.display = '';
      btn.innerHTML = '&#9650; Ocultar';
    } else {
      row.style.display = 'none';
      btn.innerHTML = '&#9660; Ver homólogos (' + count + ')';
    }
  }
```

- [ ] **Step 7: Verificación manual**

1. Arrancar la app: `python app.py`
2. Sincronizar un Excel de homólogos desde `/admin/sync` (con datos que matcheen `codigo_sap` de algún equipo existente en `filtros_equipo`).
3. Navegar a la ficha de ese equipo (`/equipo/<VEHICULO>`).
4. Verificar:
   - La columna "Homólogos" aparece en el thead de la tabla de filtros.
   - Los filtros con `codigo_sap` en el catálogo muestran el botón "▼ Ver homólogos (N)".
   - Al hacer clic, la fila expand aparece con la sub-tabla.
   - El filtro principal (mismo SAP que el de `filtros_equipo`) está resaltado en verde con chip "Principal".
   - Badges: "Ya correcto" verde, "Revisar" ámbar.
   - Al hacer clic de nuevo, la fila se oculta y el botón vuelve a "▼ Ver homólogos (N)".
   - Los filtros sin `codigo_sap` o sin homólogos en la tabla no muestran botón.
   - El formulario de edición admin sigue funcionando (colspan=5 correcto).

- [ ] **Step 8: Commit**

```bash
git add templates/equipo_detalle.html
git commit -m "feat: UI expandible de homólogos en ficha de equipo"
```

---

## Task 6: Export Excel — hoja `Homólogos`

**Files:**
- Modify: `app.py` — función `exportar_ficha_equipo` (alrededor de la línea 2133)

**Interfaces:**
- Consumes: tabla `homologos`, tabla `filtros_equipo`; variables `azul`, `wfont`, `ctr` ya definidas en la función
- Produces: tercera hoja `Homólogos` en el workbook Excel descargado (solo si hay datos)

- [ ] **Step 1: Agregar query de homólogos en `exportar_ficha_equipo`**

En `app.py`, en la función `exportar_ficha_equipo`, localizar el bloque:
```python
    conn.close()
```
(El `conn.close()` que viene después de que se cargan `filtros` y `cambios`.)

Antes de ese `conn.close()`, agregar:

```python
    homo_rows = conn.execute("""
        SELECT f.nombre_articulo AS filtro_original, f.codigo_sap AS sap_original,
               h.grupo, h.codigo_sap AS sap_homologo, h.descripcion, h.estado
        FROM filtros_equipo f
        JOIN homologos h ON h.grupo = (
            SELECT grupo FROM homologos WHERE codigo_sap = f.codigo_sap LIMIT 1
        )
        WHERE UPPER(f.equipo) = ?
        ORDER BY h.grupo, h.estado DESC, h.codigo_sap
    """, (vehiculo,)).fetchall()
```

- [ ] **Step 2: Agregar hoja `Homólogos` al workbook**

En `exportar_ficha_equipo`, localizar el bloque que construye `ws2` (`Historial Cambios`). Después del bucle que autoajusta las columnas de `ws2`, y antes de la llamada `wb.save(buf)`, agregar:

```python
    if homo_rows:
        ws3 = wb.create_sheet('Homólogos')
        ws3.append(['Filtro Original', 'SAP Original', 'Grupo', 'SAP Homólogo', 'Descripción', 'Estado'])
        for cell in ws3[1]:
            cell.fill = azul
            cell.font = wfont
            cell.alignment = ctr
        for r in homo_rows:
            ws3.append([
                r['filtro_original'] or '',
                r['sap_original'] or '',
                r['grupo'],
                r['sap_homologo'] or '',
                r['descripcion'] or '',
                r['estado'] or '',
            ])
        for col in ws3.columns:
            mx = max((len(str(c.value or '')) for c in col), default=8)
            ws3.column_dimensions[col[0].column_letter].width = min(mx + 4, 50)
```

- [ ] **Step 3: Verificación manual**

1. Con homólogos sincronizados, navegar a la ficha de un equipo que los tenga.
2. Hacer clic en "Descargar ficha".
3. Abrir el Excel descargado y verificar:
   - Hoja 1 "Filtros": sin cambios.
   - Hoja 2 "Historial Cambios": sin cambios.
   - Hoja 3 "Homólogos": columnas `Filtro Original`, `SAP Original`, `Grupo`, `SAP Homólogo`, `Descripción`, `Estado`; encabezados azul Talma; datos correctos.
4. Para un equipo sin homólogos: verificar que el Excel solo tiene 2 hojas (la hoja Homólogos no se crea).

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: hoja Homólogos en descarga Excel de ficha de equipo"
```

---

## Verificación Final

- [ ] Ejecutar suite de tests completa:
  ```
  python -m pytest tests/ -v
  ```
  Resultado esperado: todos `PASSED`.

- [ ] Flujo end-to-end:
  1. Login como admin → Sincronizar → subir Excel con hoja `Grupos_Homologos` → verificar flash de éxito
  2. Navegar a ficha de equipo con filtros que tengan SAP en el catálogo → verificar expand/collapse
  3. Descargar ficha → verificar hoja Homólogos en Excel
  4. Navegar desde Flota (`/taller/flota`) → hacer clic en equipo → verificar que la ficha muestra homólogos igual

- [ ] Verificar que equipos sin homólogos cargados no muestran errores ni botones fantasma.

- [ ] Commit final si todo pasa:
  ```bash
  git add .
  git commit -m "feat: filtros homólogos — sync, UI expandible, export Excel"
  ```
