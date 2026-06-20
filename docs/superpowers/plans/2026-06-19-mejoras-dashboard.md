# Mejoras Dashboard MP (5 features) — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar 5 mejoras al sistema de seguimiento MP: días sin gestionar (CIO), alertas admin, export Excel 2 hojas, timeline vehículo, y búsqueda global.

**Architecture:** Flask + SQLite + openpyxl + Jinja2. Todo el CSS/JS embebido, zero CDN. Cada mejora toca `app.py` (lógica/rutas) y el/los template(s) correspondientes. Mejoras 1–4 son modificaciones de rutas y templates existentes; Mejora 5 agrega una nueva ruta de API y modifica `base.html`.

**Tech Stack:** Python 3.11+, Flask, SQLite (JULIANDAY para aritmética de fechas), openpyxl (export), Jinja2, vanilla JS (fetch, debounce).

## Global Constraints

- Branding: Azul `#002D6E`, Verde `#80AE3F`, Cielo `#1E88E5`, Ámbar `#E67E22`, Rojo `#dc2626`, Fondo `#F0F2F5`
- Zero CDN externos — todo CSS/JS embebido en templates
- Python 3.11+, Flask, SQLite, openpyxl
- `TZ_COL = ZoneInfo('America/Bogota')` para timestamps
- `get_db()` / `conn.close()` siempre pareados
- `datetime.now(TZ_COL).isoformat()` para timestamps
- No modificar datos fuente (tabla `equipos` es de solo lectura desde la app)
- Español en UI, inglés en variables/funciones
- Responsive — laptop/tablet, con media queries ≤768px

---

### Task 1: Mejora 1 — Días sin gestionar (CIO Dashboard backend)

**Files:**
- Modify: `app.py` — función `cio_dashboard()` (líneas 621–784)

**Interfaces:**
- Consumes: `all_equipos` (lista de sqlite Row con campo `fecha_programacion` tipo string ISO), `vehicles` dict, `sol_state` por vehículo
- Produces: cada entrada de `vehicles.values()` tendrá una clave `dias_sin_gestionar: int` (0 si no aplica)

- [ ] **Step 1: Localizar el loop de construcción del vehicles dict**

En `app.py`, dentro de `cio_dashboard()`, el loop `for equipo in all_equipos:` construye el dict `vehicles[v]`. Agregar el campo `fecha_programacion` al dict inicial del vehículo:

```python
# Dentro del bloque `if v not in vehicles:`, agregar al dict:
'fecha_programacion': equipo['fecha_programacion'],
```

El bloque completo queda así (cambio solo en el fragmento `if v not in vehicles:`):

```python
if v not in vehicles:
    vehicles[v] = {
        'vehiculo':           v,
        'familia':            equipo['familia'],
        'categoria':          equipo['categoria'],
        'estado_vehiculo':    equipo['estado_vehiculo'],
        'rutinas':            [],
        'ind_desviacion':     equipo['ind_desviacion'],
        'desviacion':         equipo['desviacion'],
        'estado_mp':          equipo['estado_mp'],
        'equipo_ids':         [],
        'sol_ids_pendientes': [],
        'motivos_no_ej':      [],
        '_has_pendiente':     False,
        '_has_no_ej':         False,
        'fecha_programacion': equipo['fecha_programacion'],  # NUEVO
    }
```

- [ ] **Step 2: Calcular dias_sin_gestionar después del loop de construcción de vehicles**

Insertar el bloque de cálculo JUSTO ANTES de la sección `for vd in vehicles.values():` que construye `sol_state` (buscar el comentario implícito donde se hace `if vd['_has_pendiente']`):

```python
# Calcular días sin gestionar para vehículos vencidos sin solicitud
_today = datetime.now(TZ_COL).date()
for _v, _vd in vehicles.items():
    _vd['dias_sin_gestionar'] = 0
    # Solo aplica si no solicitado y estado MP contiene "vencido"
    if _vd.get('_has_pendiente') or _vd.get('_has_no_ej'):
        continue
    if 'vencido' not in (_vd['estado_mp'] or '').lower():
        continue
    fp = _vd.get('fecha_programacion')
    if not fp:
        continue
    try:
        d = datetime.strptime(str(fp)[:10], '%Y-%m-%d').date()
        diff = (_today - d).days
        if diff > 0:
            _vd['dias_sin_gestionar'] = diff
    except (ValueError, TypeError):
        pass
```

- [ ] **Step 3: Limpiar fecha_programacion del dict final (no necesaria en template)**

Justo después del loop que hace `del vd['_has_pendiente'], vd['_has_no_ej']`, agregar:

```python
del vd['fecha_programacion']
```

- [ ] **Step 4: Verificar manualmente en Python (sin servidor)**

Abrir Python shell:
```python
from datetime import datetime
from zoneinfo import ZoneInfo
TZ_COL = ZoneInfo('America/Bogota')
today = datetime.now(TZ_COL).date()
fp = '2026-06-10T08:31:00'
d = datetime.strptime(str(fp)[:10], '%Y-%m-%d').date()
print((today - d).days)  # debe ser 9 si hoy es 2026-06-19
```
Expected output: `9`

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: calcular dias_sin_gestionar en dashboard CIO"
```

---

### Task 2: Mejora 1 — Badge días sin gestionar (CIO Dashboard template)

**Files:**
- Modify: `templates/cio/dashboard.html` — sección `{% block styles %}` y tbody de la tabla

**Interfaces:**
- Consumes: `equipo.dias_sin_gestionar` (int, 0 si no aplica) de cada elemento en `equipos`
- Produces: badge visible en columna "Resultado" para vehículos vencidos sin solicitud

- [ ] **Step 1: Agregar estilos para el badge al bloque `<style>` del template**

Insertar justo antes del cierre `</style>` del bloque styles (antes del `@media (max-width: 768px)` final):

```css
/* ── Días sin gestionar ── */
.badge-dias {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border-radius: 10px;
  font-size: 11.5px;
  font-weight: 700;
  white-space: nowrap;
  margin-left: 4px;
}
.badge-dias-rojo {
  background: #fff2f2;
  color: #991b1b;
  border: 1px solid #fca5a5;
  animation: parpadeo 1.2s infinite;
}
.badge-dias-ambar {
  background: #fffbeb;
  color: #92400e;
  border: 1px solid #fde68a;
}
@keyframes parpadeo {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.45; }
}
```

- [ ] **Step 2: Agregar el badge en la columna de la tabla**

En la celda `<td>` de Vehículo (la que contiene el `vehiculo-link`), agregar el badge justo después del enlace del vehículo:

Buscar:
```html
              <td>
                <a href="{{ url_for('equipo_detalle', vehiculo=equipo.vehiculo) }}"
                   class="vehiculo-link">{{ equipo.vehiculo }}</a>
              </td>
```

Reemplazar con:
```html
              <td>
                <a href="{{ url_for('equipo_detalle', vehiculo=equipo.vehiculo) }}"
                   class="vehiculo-link">{{ equipo.vehiculo }}</a>
                {% if equipo.dias_sin_gestionar and equipo.dias_sin_gestionar >= 3 %}
                  <span class="badge-dias badge-dias-rojo"
                        title="{{ equipo.dias_sin_gestionar }} días sin gestionar">
                    ⚠ {{ equipo.dias_sin_gestionar }}d
                  </span>
                {% elif equipo.dias_sin_gestionar and equipo.dias_sin_gestionar >= 1 %}
                  <span class="badge-dias badge-dias-ambar"
                        title="{{ equipo.dias_sin_gestionar }} días sin gestionar">
                    {{ equipo.dias_sin_gestionar }}d
                  </span>
                {% endif %}
              </td>
```

- [ ] **Step 3: Verificar visualmente que el badge aparece**

Iniciar el servidor (`python app.py`) y navegar a `/cio`. Verificar:
- Vehículos sin solicitud + estado vencido + fecha_programacion > 3 días → badge rojo parpadeante
- Vehículos sin solicitud + estado vencido + 1-2 días → badge amarillo
- Vehículos solicitados o próximos → sin badge

- [ ] **Step 4: Commit**

```bash
git add templates/cio/dashboard.html
git commit -m "feat: badge dias sin gestionar en dashboard CIO"
```

---

### Task 3: Mejora 2 — Alertas admin (backend)

**Files:**
- Modify: `app.py` — función `admin_dashboard()` (líneas 184–256)

**Interfaces:**
- Produces: variables `alerta_vencidos` (int), `alerta_pendientes` (int), `alerta_no_ej` (int) pasadas al template

- [ ] **Step 1: Agregar queries de alertas en admin_dashboard()**

Después del bloque `if sync_id:` que recupera `equipos_todos`, `categorias_admin`, `familias_admin`, agregar ANTES de `conn.close()`:

```python
    # ── Alertas ──
    alerta_vencidos = 0      # vencidos sin solicitud por >7 días
    alerta_pendientes = 0    # solicitados sin respuesta CIO >3 días
    alerta_no_ej = 0         # respondidos como no_ejecutado en ciclo actual

    if sync_id:
        alerta_vencidos = conn.execute(
            """SELECT COUNT(DISTINCT e.vehiculo) AS c
               FROM equipos e
               WHERE e.sync_id = ?
               AND LOWER(e.estado_mp) LIKE '%vencido%'
               AND NOT EXISTS (
                   SELECT 1 FROM solicitudes s
                   WHERE s.equipo_id = e.id AND s.sync_id = e.sync_id
               )
               AND JULIANDAY('now') - JULIANDAY(e.fecha_programacion) > 7""",
            (sync_id,)
        ).fetchone()['c'] or 0

        alerta_pendientes = conn.execute(
            """SELECT COUNT(*) AS c
               FROM solicitudes s
               WHERE s.sync_id = ?
               AND s.estado = 'pendiente'
               AND JULIANDAY('now') - JULIANDAY(s.fecha_solicitud) > 3""",
            (sync_id,)
        ).fetchone()['c'] or 0

        alerta_no_ej = conn.execute(
            """SELECT COUNT(DISTINCT e.vehiculo) AS c
               FROM solicitudes s
               JOIN equipos e ON e.id = s.equipo_id
               JOIN respuestas r ON r.solicitud_id = s.id
               WHERE s.sync_id = ?
               AND r.accion = 'no_ejecutado'""",
            (sync_id,)
        ).fetchone()['c'] or 0
```

- [ ] **Step 2: Agregar para las alertas el data de solicitudes en los equipos (para filtro en tabla)**

En la misma función, dentro del bloque `if sync_id:`, después de obtener `equipos_todos`, agregar:

```python
        # IDs de equipos con solicitud en ciclo actual (para badge en tabla)
        sol_equipo_ids = {
            r['equipo_id'] for r in conn.execute(
                "SELECT DISTINCT equipo_id FROM solicitudes WHERE sync_id = ?",
                (sync_id,)
            ).fetchall()
        }
```

Y también convertir `equipos_todos` a lista de dicts con el campo `tiene_solicitud`:

```python
        equipos_todos = [
            {**dict(eq), 'tiene_solicitud': eq['id'] in sol_equipo_ids}
            for eq in equipos_todos
        ]
```

- [ ] **Step 3: Actualizar el return de admin_dashboard para incluir nuevas variables**

En `return render_template('admin/dashboard.html', ...)`, agregar:

```python
        alerta_vencidos=alerta_vencidos,
        alerta_pendientes=alerta_pendientes,
        alerta_no_ej=alerta_no_ej,
```

Si `sync_id` es None, estas variables ya están inicializadas en 0 (del paso 1), así que el return de la ruta las pasa siempre. Verificar que el bloque `if sync_id:` no envuelva las variables iniciales.

Después de la inicialización `total_equipos = 0; solicitados = 0; ...`, agregar:
```python
    alerta_vencidos = 0
    alerta_pendientes = 0
    alerta_no_ej = 0
```

Y en el `return render_template(...)` agregar las tres variables.

- [ ] **Step 4: Verificar que no hay error 500 en /admin**

```bash
python app.py
# Navegar a /admin — debe cargar sin error
```

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: calcular alertas de gestion para dashboard admin"
```

---

### Task 4: Mejora 2 — Sección alertas (Admin Dashboard template)

**Files:**
- Modify: `templates/admin/dashboard.html` — añadir sección alertas arriba de KPIs

**Interfaces:**
- Consumes: `alerta_vencidos` (int), `alerta_pendientes` (int), `alerta_no_ej` (int) del contexto Jinja2
- Consumes: cada row de `equipos_todos` tiene clave `tiene_solicitud` (bool)

- [ ] **Step 1: Agregar CSS para alertas en el bloque styles**

Insertar antes de `/* Empty state */` en el bloque `<style>`:

```css
/* ── Alertas ── */
.alertas-section {
  margin-bottom: 24px;
}
.alertas-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
@media (max-width: 900px) { .alertas-grid { grid-template-columns: 1fr; } }

.alerta-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  border-radius: 10px;
  border: 1.5px solid;
  text-decoration: none;
  cursor: pointer;
  transition: filter 0.15s, transform 0.12s;
}
.alerta-card:hover { filter: brightness(0.96); transform: translateY(-1px); }
.alerta-card-rojo  { background: #fff2f2; border-color: #fca5a5; color: #991b1b; }
.alerta-card-ambar { background: #fffbeb; border-color: #fde68a; color: #92400e; }
.alerta-card-naranja { background: #fff7ed; border-color: #fdba74; color: #9a3412; }
.alerta-card-ok    { background: #f0fdf4; border-color: #86efac; color: #14532d;
                     cursor: default; grid-column: 1 / -1; justify-content: center; }

.alerta-icon {
  font-size: 22px;
  flex-shrink: 0;
  line-height: 1;
}
.alerta-content {}
.alerta-count {
  font-size: 22px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.5px;
}
.alerta-text {
  font-size: 12.5px;
  font-weight: 600;
  line-height: 1.3;
  margin-top: 2px;
}
.alerta-action {
  font-size: 11.5px;
  font-weight: 500;
  opacity: 0.7;
  margin-top: 3px;
}
```

- [ ] **Step 2: Insertar la sección HTML de alertas antes del bloque KPI**

Justo antes de `<!-- KPI cards -->`, insertar:

```html
  <!-- ── Alertas de gestión ── -->
  <div class="alertas-section">
    <div class="alertas-grid">
      {% set hay_alertas = alerta_vencidos > 0 or alerta_pendientes > 0 or alerta_no_ej > 0 %}
      {% if hay_alertas %}

        {% if alerta_vencidos > 0 %}
        <a href="{{ url_for('admin_dashboard') }}?highlight=vencidos_sin_sol"
           class="alerta-card alerta-card-rojo"
           title="Ver equipos vencidos sin solicitar">
          <div class="alerta-icon">🔴</div>
          <div class="alerta-content">
            <div class="alerta-count">{{ alerta_vencidos }}</div>
            <div class="alerta-text">equipo(s) llevan +7 días vencidos sin solicitud</div>
            <div class="alerta-action">Clic para ver en tabla →</div>
          </div>
        </a>
        {% endif %}

        {% if alerta_pendientes > 0 %}
        <a href="{{ url_for('admin_historial') }}?accion=pendiente"
           class="alerta-card alerta-card-ambar">
          <div class="alerta-icon">🟡</div>
          <div class="alerta-content">
            <div class="alerta-count">{{ alerta_pendientes }}</div>
            <div class="alerta-text">solicitud(es) llevan +3 días sin respuesta del CIO</div>
            <div class="alerta-action">Ver en historial →</div>
          </div>
        </a>
        {% endif %}

        {% if alerta_no_ej > 0 %}
        <a href="{{ url_for('admin_historial') }}?accion=no_ejecutado"
           class="alerta-card alerta-card-naranja">
          <div class="alerta-icon">🟠</div>
          <div class="alerta-content">
            <div class="alerta-count">{{ alerta_no_ej }}</div>
            <div class="alerta-text">equipo(s) marcados como no ejecutados</div>
            <div class="alerta-action">Ver en historial →</div>
          </div>
        </a>
        {% endif %}

      {% else %}
        <div class="alerta-card alerta-card-ok">
          <div class="alerta-icon">✅</div>
          <div class="alerta-content">
            <div class="alerta-text" style="font-size:14px;">Sin alertas pendientes — todo al día</div>
          </div>
        </div>
      {% endif %}
    </div>
  </div>
```

- [ ] **Step 3: Agregar data-tiene-solicitud a las filas de la tabla admin y JS para highlight**

En la tabla `#adm-equipos-body`, buscar el `<tr` con los `data-categoria` etc. y agregar:
```html
data-tiene-solicitud="{{ 'si' if eq.tiene_solicitud else 'no' }}"
data-estado-mp="{{ eq.estado_mp or '' }}"
```

En el bloque `{% block scripts %}`, actualizar la función JS para leer el URL param `highlight`:

```javascript
// Al inicio de la IIFE, después de las declaraciones de variables, agregar:
  var urlParams = new URLSearchParams(window.location.search);
  var highlight = urlParams.get('highlight');

  if (highlight === 'vencidos_sin_sol' && filBus) {
    // Scroll a la tabla
    var tableSection = document.querySelector('.section-hdr');
    if (tableSection) {
      setTimeout(function() {
        tableSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 200);
    }
    // Aplicar filtro: mostrar solo vencidos sin solicitud
    rows.forEach(function(tr) {
      var tieneSol = (tr.dataset.tieneSolicitud || '') === 'si';
      var estadoMp = (tr.dataset.estadoMp || '').toLowerCase();
      var esVencido = estadoMp.includes('vencido');
      tr.style.display = (!tieneSol && esVencido) ? '' : 'none';
    });
    var visible = Array.from(rows).filter(function(tr) { return tr.style.display !== 'none'; }).length;
    if (noRes)   noRes.style.display   = visible === 0 ? '' : 'none';
    if (counter) counter.textContent   = visible + ' equipo(s) — ⚠ Vencidos sin solicitar';
  }
```

- [ ] **Step 4: Verificar que la sección de alertas aparece correctamente**

```bash
python app.py
# Navegar a /admin — debe ver sección de alertas arriba de KPIs
# Si no hay alertas → "Sin alertas pendientes" en verde
# Si hay alertas → tarjetas de color con contadores
# Clic en alerta de historial → redirige a /admin/historial?accion=pendiente con filtro pre-aplicado
```

- [ ] **Step 5: Commit**

```bash
git add templates/admin/dashboard.html
git commit -m "feat: seccion de alertas en dashboard admin"
```

---

### Task 5: Mejora 3 — Export Excel 2 hojas

**Files:**
- Modify: `app.py` — función `admin_export()` (líneas 403–491)

**Interfaces:**
- Produces: archivo Excel con 2 hojas: "Resumen Ejecutivo" y "Detalle"

- [ ] **Step 1: Agregar imports necesarios al inicio del bloque admin_export**

Los imports `openpyxl`, `io`, `PatternFill`, `Font`, `Alignment`, `Border`, `Side` ya están en el código original dentro de la función. Agregar también:

```python
    from openpyxl.utils import get_column_letter
```

- [ ] **Step 2: Reemplazar completamente el cuerpo de admin_export()**

La función actual tiene un único sheet. Reemplazar todo desde `wb = openpyxl.Workbook()` hasta el final por el siguiente código:

```python
    # ── Datos para resumen ejecutivo ──
    stats = conn.execute(
        """SELECT
               COUNT(s.id) AS total_sol,
               SUM(CASE WHEN r.accion = 'ejecutado'    THEN 1 ELSE 0 END) AS ejecutados,
               SUM(CASE WHEN r.accion = 'no_ejecutado' THEN 1 ELSE 0 END) AS no_ejecutados
           FROM solicitudes s
           LEFT JOIN respuestas r ON r.solicitud_id = s.id"""
    ).fetchone()
    total_sol  = stats['total_sol']  or 0
    ejecutados = stats['ejecutados'] or 0
    no_ej      = stats['no_ejecutados'] or 0
    pct_ej     = round(ejecutados / total_sol * 100) if total_sol else 0

    familias_data = conn.execute(
        """SELECT e.familia,
                  COUNT(s.id) AS solicitados,
                  SUM(CASE WHEN r.accion = 'ejecutado'    THEN 1 ELSE 0 END) AS ejecutados,
                  SUM(CASE WHEN r.accion = 'no_ejecutado' THEN 1 ELSE 0 END) AS no_ejecutados
           FROM solicitudes s
           JOIN equipos e ON e.id = s.equipo_id
           LEFT JOIN respuestas r ON r.solicitud_id = s.id
           WHERE e.familia IS NOT NULL
           GROUP BY e.familia
           ORDER BY e.familia"""
    ).fetchall()

    top_motivos = conn.execute(
        """SELECT CASE WHEN r.motivo_id IS NOT NULL
                       THEN COALESCE(m.descripcion, 'Desconocido')
                       ELSE 'Comentario libre'
                  END AS motivo,
                  COUNT(*) AS cantidad
           FROM respuestas r
           LEFT JOIN catalogo_motivos m ON m.id = r.motivo_id
           WHERE r.accion = 'no_ejecutado'
           GROUP BY r.motivo_id
           ORDER BY cantidad DESC
           LIMIT 10"""
    ).fetchall()

    wb = openpyxl.Workbook()

    # ── Estilos comunes ──
    from openpyxl.utils import get_column_letter
    thin      = Side(style='thin', color='CCCCCC')
    brd       = Border(left=thin, right=thin, top=thin, bottom=thin)
    brd_thick = Border(
        left=Side(style='medium', color='002D6E'),
        right=Side(style='medium', color='002D6E'),
        top=Side(style='medium', color='002D6E'),
        bottom=Side(style='medium', color='002D6E'),
    )
    fill_azul      = PatternFill('solid', fgColor='002D6E')
    fill_verde     = PatternFill('solid', fgColor='80AE3F')
    fill_cielo     = PatternFill('solid', fgColor='1E88E5')
    fill_ambar     = PatternFill('solid', fgColor='E67E22')
    fill_gris_claro = PatternFill('solid', fgColor='F0F2F5')
    fill_seccion   = PatternFill('solid', fgColor='E8EDF5')
    font_titulo    = Font(bold=True, color='FFFFFF', size=13)
    font_sub       = Font(bold=False, color='FFFFFF', size=10)
    font_seccion   = Font(bold=True, color='002D6E', size=11)
    font_hdr       = Font(bold=True, color='FFFFFF', size=10)
    font_body      = Font(size=10)
    font_kpi_val   = Font(bold=True, color='002D6E', size=22)
    font_kpi_lbl   = Font(bold=True, color='6B7280', size=9)
    center         = Alignment(horizontal='center', vertical='center', wrap_text=True)
    left           = Alignment(horizontal='left',   vertical='center', wrap_text=False)
    center_wrap    = Alignment(horizontal='center', vertical='center', wrap_text=True)

    # ════════════════════════════════════════════════════
    # HOJA 1 — Resumen Ejecutivo
    # ════════════════════════════════════════════════════
    ws1 = wb.active
    ws1.title = 'Resumen Ejecutivo'

    # -- Encabezado corporativo (fila 1-3) --
    ws1.merge_cells('A1:F1')
    c = ws1['A1']
    c.value       = 'GET — Talma Servicios Aeroportuarios'
    c.fill        = fill_azul
    c.font        = Font(bold=True, color='FFFFFF', size=16)
    c.alignment   = center
    ws1.row_dimensions[1].height = 36

    ws1.merge_cells('A2:F2')
    c2 = ws1['A2']
    c2.value     = 'Reporte Seguimiento Mantenimiento Preventivo GSE — BOG'
    c2.fill      = PatternFill('solid', fgColor='80AE3F')
    c2.font      = Font(bold=True, color='FFFFFF', size=11)
    c2.alignment = center
    ws1.row_dimensions[2].height = 22

    ws1.merge_cells('A3:F3')
    c3 = ws1['A3']
    fecha_gen = datetime.now(TZ_COL).strftime('%d/%m/%Y %H:%M')
    c3.value     = f'Generado: {fecha_gen} (hora Colombia)'
    c3.fill      = fill_gris_claro
    c3.font      = Font(italic=True, color='6B7280', size=9)
    c3.alignment = center
    ws1.row_dimensions[3].height = 16

    # -- Sección KPIs (fila 5-10) --
    ws1.row_dimensions[4].height = 10  # separador

    ws1.merge_cells('A5:F5')
    cs = ws1['A5']
    cs.value     = '■  INDICADORES GENERALES'
    cs.fill      = fill_seccion
    cs.font      = font_seccion
    cs.alignment = Alignment(horizontal='left', vertical='center', indent=1)
    ws1.row_dimensions[5].height = 20

    kpi_data = [
        ('Total Solicitados', total_sol,  fill_cielo),
        ('Ejecutados',        ejecutados, fill_verde),
        ('No Ejecutados',     no_ej,      fill_ambar),
        ('% Ejecución',       f'{pct_ej}%', fill_azul),
    ]
    kpi_cols = ['A', 'B', 'C', 'D']
    for col_letter, (lbl, val, fill) in zip(kpi_cols, kpi_data):
        # Header KPI
        hc = ws1[f'{col_letter}6']
        hc.value     = lbl
        hc.fill      = fill
        hc.font      = Font(bold=True, color='FFFFFF', size=9)
        hc.alignment = center
        ws1.row_dimensions[6].height = 18
        # Value KPI
        vc = ws1[f'{col_letter}7']
        vc.value     = val
        vc.fill      = PatternFill('solid', fgColor='FFFFFF')
        vc.font      = Font(bold=True, color='002D6E', size=24)
        vc.alignment = center
        ws1.row_dimensions[7].height = 40
        vc.border = brd

    # -- Sección Cumplimiento por Familia (fila 10+) --
    ws1.row_dimensions[8].height = 10

    ws1.merge_cells('A9:F9')
    cf = ws1['A9']
    cf.value     = '■  CUMPLIMIENTO POR FAMILIA'
    cf.fill      = fill_seccion
    cf.font      = font_seccion
    cf.alignment = Alignment(horizontal='left', vertical='center', indent=1)
    ws1.row_dimensions[9].height = 20

    fam_headers = ['Familia', 'Solicitados', 'Ejecutados', 'No Ejecutados', '% Ejecución']
    for ci, h in enumerate(fam_headers, 1):
        cell = ws1.cell(row=10, column=ci, value=h)
        cell.fill      = fill_azul
        cell.font      = font_hdr
        cell.alignment = center
        cell.border    = brd
    ws1.row_dimensions[10].height = 20

    for ri, fd in enumerate(familias_data, 11):
        sol_f = fd['solicitados'] or 0
        ej_f  = fd['ejecutados']  or 0
        nej_f = fd['no_ejecutados'] or 0
        pct_f = f"{round(ej_f/sol_f*100)}%" if sol_f else '—'
        vals = [fd['familia'] or '—', sol_f, ej_f, nej_f, pct_f]
        for ci, v in enumerate(vals, 1):
            cell = ws1.cell(row=ri, column=ci, value=v)
            cell.alignment = center
            cell.border    = brd
            cell.font      = font_body
            if ri % 2 == 0:
                cell.fill = fill_gris_claro
        ws1.row_dimensions[ri].height = 16

    last_fam_row = 10 + len(familias_data) + 1

    # -- Sección Top Motivos No Ejecución --
    ws1.row_dimensions[last_fam_row].height = 10

    mot_title_row = last_fam_row + 1
    ws1.merge_cells(f'A{mot_title_row}:F{mot_title_row}')
    cm = ws1[f'A{mot_title_row}']
    cm.value     = '■  TOP MOTIVOS DE NO EJECUCIÓN'
    cm.fill      = fill_seccion
    cm.font      = font_seccion
    cm.alignment = Alignment(horizontal='left', vertical='center', indent=1)
    ws1.row_dimensions[mot_title_row].height = 20

    mot_hdr_row = mot_title_row + 1
    for ci, h in enumerate(['Motivo', 'Cantidad'], 1):
        cell = ws1.cell(row=mot_hdr_row, column=ci, value=h)
        cell.fill      = fill_ambar
        cell.font      = font_hdr
        cell.alignment = center
        cell.border    = brd
    ws1.row_dimensions[mot_hdr_row].height = 20

    for ri, m in enumerate(top_motivos, mot_hdr_row + 1):
        vals = [m['motivo'] or 'Sin motivo', m['cantidad']]
        for ci, v in enumerate(vals, 1):
            cell = ws1.cell(row=ri, column=ci, value=v)
            cell.alignment = left if ci == 1 else center
            cell.border    = brd
            cell.font      = font_body
            if ri % 2 == 0:
                cell.fill = fill_gris_claro
        ws1.row_dimensions[ri].height = 16

    # Anchos columnas Sheet 1
    for col_letter, w in [('A', 36), ('B', 16), ('C', 16), ('D', 16), ('E', 14), ('F', 14)]:
        ws1.column_dimensions[col_letter].width = w

    # ════════════════════════════════════════════════════
    # HOJA 2 — Detalle
    # ════════════════════════════════════════════════════
    ws2 = wb.create_sheet(title='Detalle')

    det_headers = [
        'Fecha Solicitud', 'Vehículo', 'Familia', 'Categoría', 'Rutina',
        'Desviación', 'Ind. Desviación', 'Estado MP',
        'Solicitado por', 'Fecha Respuesta', 'Acción', 'Motivo', 'Comentario',
    ]

    hdr_fill_det  = PatternFill('solid', fgColor='002D6E')
    hdr_font_det  = Font(bold=True, color='FFFFFF', size=10)

    ws2.row_dimensions[1].height = 28
    for ci, h in enumerate(det_headers, 1):
        cell = ws2.cell(row=1, column=ci, value=h)
        cell.fill      = hdr_fill_det
        cell.font      = hdr_font_det
        cell.alignment = center
        cell.border    = brd

    body_align = Alignment(vertical='center', wrap_text=False)
    for ri, fila in enumerate(filas, 2):
        values = [
            fila['fecha_solicitud'],
            fila['vehiculo'],
            fila['familia'],
            fila['categoria'],
            fila['rutina'],
            fila['desviacion'],
            fila['ind_desviacion'],
            fila['estado_mp'],
            fila['solicitado_por'],
            fila['fecha_respuesta'],
            fila['accion'] or 'pendiente',
            fila['motivo'],
            fila['comentario_libre'],
        ]
        for ci, val in enumerate(values, 1):
            cell = ws2.cell(row=ri, column=ci, value=val)
            cell.border    = brd
            cell.alignment = body_align
            cell.font      = font_body
            if ri % 2 == 0:
                cell.fill = fill_gris_claro

    # Auto-filtros y freeze
    ws2.auto_filter.ref = ws2.dimensions
    ws2.freeze_panes    = 'A2'

    # Anchos columnas Sheet 2
    for col in ws2.columns:
        max_len = max(
            (len(str(c.value)) if c.value is not None else 0 for c in col),
            default=10
        )
        ws2.column_dimensions[col[0].column_letter].width = min(max_len + 4, 55)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"reporte_mp_{datetime.now(TZ_COL).strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename,
    )
```

- [ ] **Step 3: Verificar que el export funciona**

```bash
python app.py
# Navegar a /admin/export — debe descargar Excel
# Abrir el Excel: debe tener 2 hojas (Resumen Ejecutivo + Detalle)
# Hoja 1: header azul, KPIs, tabla familias, top motivos
# Hoja 2: header azul #002D6E, auto-filtros, freeze en fila 2
```

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: export Excel 2 hojas con resumen ejecutivo y detalle"
```

---

### Task 6: Mejora 4 — Timeline historial en equipo_detalle

**Files:**
- Modify: `app.py` — función `equipo_detalle()` (líneas 936–1003)
- Modify: `templates/equipo_detalle.html` — sección historial (líneas 517–584)

**Interfaces:**
- Produces: `hist_stats` dict con claves `total`, `ejecutados`, `no_ejecutados`, `pendientes`, `pct_ejecucion` pasado al template

- [ ] **Step 1: Calcular estadísticas del historial en app.py**

En `equipo_detalle()`, después de obtener `historial` (línea ~985), agregar:

```python
    hist_stats = {
        'total':        len(historial),
        'ejecutados':   sum(1 for h in historial if h['accion'] == 'ejecutado'),
        'no_ejecutados':sum(1 for h in historial if h['accion'] == 'no_ejecutado'),
        'pendientes':   sum(1 for h in historial if h['estado'] == 'pendiente'),
    }
    hist_stats['pct_ejecucion'] = (
        round(hist_stats['ejecutados'] / hist_stats['total'] * 100)
        if hist_stats['total'] else 0
    )
```

Y agregar `hist_stats=hist_stats` al `return render_template(...)`.

- [ ] **Step 2: Agregar CSS para timeline en equipo_detalle.html**

En el bloque `<style>`, añadir antes de `@media (max-width: 768px)`:

```css
/* ── Timeline historial ── */
.hist-stats-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}
.hist-stat-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 18px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 6px rgba(0,45,110,0.08);
  border-left: 3px solid transparent;
  min-width: 90px;
}
.hist-stat-chip.chip-total   { border-color: var(--azul); }
.hist-stat-chip.chip-ej      { border-color: var(--verde); }
.hist-stat-chip.chip-no-ej   { border-color: var(--rojo); }
.hist-stat-chip.chip-pct     { border-color: var(--cielo); }
.hist-stat-val {
  font-size: 22px;
  font-weight: 700;
  line-height: 1;
  color: var(--azul);
}
.hist-stat-chip.chip-ej    .hist-stat-val { color: var(--verde); }
.hist-stat-chip.chip-no-ej .hist-stat-val { color: var(--rojo); }
.hist-stat-chip.chip-pct   .hist-stat-val { color: var(--cielo); }
.hist-stat-lbl {
  font-size: 10.5px;
  font-weight: 700;
  color: var(--gris);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-top: 3px;
}

/* Timeline */
.timeline {
  position: relative;
  padding-left: 28px;
}
.timeline::before {
  content: '';
  position: absolute;
  left: 9px; top: 8px; bottom: 8px;
  width: 2px;
  background: var(--borde);
}
.tl-item {
  position: relative;
  margin-bottom: 16px;
}
.tl-dot {
  position: absolute;
  left: -23px; top: 6px;
  width: 14px; height: 14px;
  border-radius: 50%;
  border: 2px solid #fff;
  box-shadow: 0 0 0 2px currentColor;
}
.tl-dot-sol  { color: var(--cielo);  background: var(--cielo); }
.tl-dot-ej   { color: var(--verde);  background: var(--verde); }
.tl-dot-no   { color: var(--rojo);   background: var(--rojo);  }
.tl-dot-pend { color: var(--ambar);  background: var(--ambar); }

.tl-card {
  background: #fff;
  border-radius: 9px;
  border: 1px solid var(--borde);
  padding: 10px 14px;
}
.tl-card-ej   { border-left: 3px solid var(--verde);  }
.tl-card-no   { border-left: 3px solid var(--rojo);   }
.tl-card-pend { border-left: 3px solid var(--ambar);  }
.tl-card-sol  { border-left: 3px solid var(--cielo);  }

.tl-fecha {
  font-size: 11px;
  color: var(--gris);
  margin-bottom: 3px;
}
.tl-accion {
  font-size: 13px;
  font-weight: 700;
}
.tl-accion-ej   { color: var(--verde); }
.tl-accion-no   { color: var(--rojo);  }
.tl-accion-pend { color: var(--ambar); }
.tl-accion-sol  { color: var(--cielo); }
.tl-meta {
  font-size: 12px;
  color: var(--gris);
  margin-top: 2px;
}
```

- [ ] **Step 3: Reemplazar sección historial en equipo_detalle.html**

Buscar el bloque completo `<!-- ── Historial de solicitudes ── -->` (desde `<div class="section">` hasta su `</div>` de cierre) y reemplazar con:

```html
  <!-- ── Historial del Vehículo ── -->
  <div class="section">
    <div class="section-title">
      <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
      Historial del Vehículo
    </div>

    {% if historial %}
    <!-- Estadísticas -->
    <div class="hist-stats-row">
      <div class="hist-stat-chip chip-total">
        <div class="hist-stat-val">{{ hist_stats.total }}</div>
        <div class="hist-stat-lbl">Total sol.</div>
      </div>
      <div class="hist-stat-chip chip-ej">
        <div class="hist-stat-val">{{ hist_stats.ejecutados }}</div>
        <div class="hist-stat-lbl">Ejecutados</div>
      </div>
      <div class="hist-stat-chip chip-no-ej">
        <div class="hist-stat-val">{{ hist_stats.no_ejecutados }}</div>
        <div class="hist-stat-lbl">No ejec.</div>
      </div>
      <div class="hist-stat-chip chip-pct">
        <div class="hist-stat-val">{{ hist_stats.pct_ejecucion }}%</div>
        <div class="hist-stat-lbl">Ejecución</div>
      </div>
    </div>

    <!-- Línea de tiempo -->
    <div class="card-table" style="padding:18px 22px;">
      <div class="timeline">
        {% for h in historial %}
          {% if h.accion == 'ejecutado' %}
            {% set dot_cls = 'tl-dot-ej' %}
            {% set card_cls = 'tl-card-ej' %}
            {% set accion_cls = 'tl-accion-ej' %}
            {% set accion_lbl = '✓ Ejecutado' %}
          {% elif h.accion == 'no_ejecutado' %}
            {% set dot_cls = 'tl-dot-no' %}
            {% set card_cls = 'tl-card-no' %}
            {% set accion_cls = 'tl-accion-no' %}
            {% set accion_lbl = '✗ No Ejecutado' %}
          {% elif h.estado == 'pendiente' %}
            {% set dot_cls = 'tl-dot-pend' %}
            {% set card_cls = 'tl-card-pend' %}
            {% set accion_cls = 'tl-accion-pend' %}
            {% set accion_lbl = '⏳ Pendiente respuesta' %}
          {% else %}
            {% set dot_cls = 'tl-dot-sol' %}
            {% set card_cls = 'tl-card-sol' %}
            {% set accion_cls = 'tl-accion-sol' %}
            {% set accion_lbl = '→ Solicitado' %}
          {% endif %}

        <div class="tl-item">
          <div class="tl-dot {{ dot_cls }}"></div>
          <div class="tl-card {{ card_cls }}">
            <div class="tl-fecha">
              Solicitud: {{ h.fecha_solicitud[:16].replace('T', ' ') if h.fecha_solicitud else '—' }}
              {% if h.resp_timestamp %}
                · Respuesta: {{ h.resp_timestamp[:16].replace('T', ' ') }}
              {% endif %}
            </div>
            <div class="tl-accion {{ accion_cls }}">{{ accion_lbl }}</div>
            <div class="tl-meta">
              Solicitado por: {{ h.solicitado_por or '—' }}
              {% if h.motivo %}
                · Motivo: {{ h.motivo }}
              {% endif %}
              {% if h.comentario_libre %}
                · {{ h.comentario_libre }}
              {% endif %}
            </div>
          </div>
        </div>
        {% endfor %}
      </div>
    </div>

    {% else %}
    <div class="card-table">
      <div class="empty-inline">
        Sin historial de solicitudes para este vehículo.
      </div>
    </div>
    {% endif %}
  </div>
```

- [ ] **Step 4: Verificar el timeline visualmente**

```bash
python app.py
# Navegar a /equipo/TTT 04 (o cualquier vehículo con historial)
# Debe ver: chips de estadísticas arriba, luego línea de tiempo con puntos de color
# Verde=ejecutado, Rojo=no_ejecutado, Ámbar=pendiente
```

- [ ] **Step 5: Commit**

```bash
git add app.py templates/equipo_detalle.html
git commit -m "feat: timeline historial y estadisticas en detalle de vehiculo"
```

---

### Task 7: Mejora 5 — API búsqueda vehículos

**Files:**
- Modify: `app.py` — agregar ruta `/api/buscar-vehiculo`

**Interfaces:**
- Produces: endpoint `GET /api/buscar-vehiculo?q=<str>` → JSON `["VEH 01", "VEH 02", ...]`

- [ ] **Step 1: Agregar la ruta al final de app.py (antes del bloque `if __name__ == '__main__':`)**

```python
# ---------------------------------------------------------------------------
# API — búsqueda de vehículos (para autocomplete global)
# ---------------------------------------------------------------------------

@app.route('/api/buscar-vehiculo')
@login_required
def api_buscar_vehiculo():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    q_upper = q.upper()
    like    = f'%{q_upper}%'
    conn    = get_db()

    from_equipos = conn.execute(
        """SELECT DISTINCT vehiculo FROM equipos
           WHERE UPPER(vehiculo) LIKE ?
           ORDER BY vehiculo LIMIT 15""",
        (like,)
    ).fetchall()

    from_filtros = conn.execute(
        """SELECT DISTINCT equipo AS vehiculo FROM filtros_equipo
           WHERE UPPER(equipo) LIKE ?
           ORDER BY equipo LIMIT 15""",
        (like,)
    ).fetchall()

    conn.close()

    seen = set()
    results = []
    for r in list(from_equipos) + list(from_filtros):
        v = r['vehiculo']
        if v and v not in seen:
            seen.add(v)
            results.append(v)

    return jsonify(sorted(results)[:12])
```

- [ ] **Step 2: Verificar la API con curl o navegador**

```bash
python app.py
# En otra terminal (con la sesión activa) o directamente en el navegador logueado:
# GET /api/buscar-vehiculo?q=TT  → debe retornar JSON con vehículos que contienen "TT"
# GET /api/buscar-vehiculo?q=X   → debe retornar [] (menos de 2 chars)
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: API endpoint buscar-vehiculo para autocomplete"
```

---

### Task 8: Mejora 5 — Búsqueda global en navbar

**Files:**
- Modify: `templates/base.html` — navbar + CSS + JS

**Interfaces:**
- Consumes: `GET /api/buscar-vehiculo?q=<str>` → JSON array
- Produces: campo de búsqueda en topbar con dropdown de sugerencias; Enter → `/equipo/<vehiculo>`

- [ ] **Step 1: Agregar CSS para la búsqueda global en base.html**

Insertar antes del cierre `</style>` del bloque de estilos en base.html (antes de `/* ── Hamburger ── */`):

```css
/* ── Búsqueda global ── */
.topbar-search-wrap {
  position: relative;
  margin-left: 16px;
  flex-shrink: 0;
}
.topbar-search-input {
  padding: 5px 12px 5px 30px;
  background: rgba(255,255,255,0.12);
  border: 1px solid rgba(255,255,255,0.22);
  border-radius: 18px;
  color: #fff;
  font-size: 13px;
  width: 200px;
  outline: none;
  transition: background 0.15s, border-color 0.15s, width 0.2s;
}
.topbar-search-input::placeholder { color: rgba(255,255,255,0.5); }
.topbar-search-input:focus {
  background: rgba(255,255,255,0.18);
  border-color: rgba(255,255,255,0.5);
  width: 240px;
}
.topbar-search-icon {
  position: absolute;
  left: 9px; top: 50%;
  transform: translateY(-50%);
  width: 13px; height: 13px;
  stroke: rgba(255,255,255,0.55); fill: none;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
  pointer-events: none;
}
.topbar-search-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 220px;
  background: #fff;
  border-radius: 9px;
  box-shadow: 0 8px 28px rgba(0,45,110,0.2);
  overflow: hidden;
  z-index: 300;
  display: none;
  list-style: none;
}
.topbar-search-dropdown.open { display: block; }
.topbar-search-dropdown li {
  padding: 9px 14px;
  font-size: 13px;
  color: var(--texto);
  cursor: pointer;
  transition: background 0.1s;
  border-bottom: 1px solid #f3f4f6;
}
.topbar-search-dropdown li:last-child { border-bottom: none; }
.topbar-search-dropdown li:hover { background: #eff6ff; color: var(--azul); }
.topbar-search-dropdown li.no-result {
  color: var(--gris); font-style: italic; cursor: default;
}
.topbar-search-dropdown li.no-result:hover { background: #fff; }
@media (max-width: 768px) {
  .topbar-search-wrap {
    display: none;
    margin-left: 0;
    width: 100%;
  }
  .topbar-search-wrap.mobile-open { display: block; }
  .topbar-search-input { width: 100%; border-radius: 7px; }
  .topbar-search-input:focus { width: 100%; }
  .topbar-search-dropdown { min-width: 100%; }
}
```

- [ ] **Step 2: Insertar el HTML de búsqueda en la topbar de base.html**

Dentro del `<nav class="topbar">`, DESPUÉS del bloque `<div class="topbar-nav" id="topbar-nav">...</div>` y ANTES del `<button class="hamburger"...>`, insertar:

```html
    <!-- Búsqueda global -->
    <div class="topbar-search-wrap" id="topbar-search-wrap">
      <svg class="topbar-search-icon" viewBox="0 0 24 24">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
      <input type="text" class="topbar-search-input" id="topbar-search-input"
             placeholder="Buscar vehículo..." autocomplete="off" spellcheck="false">
      <ul class="topbar-search-dropdown" id="topbar-search-dd"></ul>
    </div>
```

- [ ] **Step 3: Agregar el JS de búsqueda global al bloque scripts de base.html**

En el bloque `{% block scripts %}{% endblock %}`, el JS está en el bloque `<script>` del navbar. Reemplazar el bloque `<script>` existente (el que maneja el hamburger) con uno expandido que incluya también la búsqueda:

```html
  <script>
  (function(){
    /* ── Hamburger ── */
    var btn = document.getElementById('hamburger-btn');
    var nav = document.getElementById('topbar-nav');
    if (btn && nav) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var open = nav.classList.toggle('open');
        btn.setAttribute('aria-expanded', String(open));
      });
      document.addEventListener('click', function(e) {
        if (nav.classList.contains('open') && !btn.contains(e.target) && !nav.contains(e.target)) {
          nav.classList.remove('open');
          btn.setAttribute('aria-expanded', 'false');
        }
      });
    }

    /* ── Búsqueda global ── */
    var searchInput = document.getElementById('topbar-search-input');
    var searchDd    = document.getElementById('topbar-search-dd');
    if (!searchInput || !searchDd) return;

    var debounceTimer = null;
    var lastQuery     = '';

    function cerrarDropdown() {
      searchDd.classList.remove('open');
      searchDd.innerHTML = '';
    }

    function abrirDropdown(items) {
      searchDd.innerHTML = '';
      if (!items || items.length === 0) {
        var li = document.createElement('li');
        li.className   = 'no-result';
        li.textContent = 'Sin resultados para "' + lastQuery + '"';
        searchDd.appendChild(li);
      } else {
        items.forEach(function(vehiculo) {
          var li = document.createElement('li');
          li.textContent = vehiculo;
          li.addEventListener('mousedown', function(e) {
            e.preventDefault();
            window.location.href = '/equipo/' + encodeURIComponent(vehiculo);
          });
          searchDd.appendChild(li);
        });
      }
      searchDd.classList.add('open');
    }

    searchInput.addEventListener('input', function() {
      var q = searchInput.value.trim();
      if (q.length < 2) { cerrarDropdown(); return; }
      lastQuery = q;
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function() {
        fetch('/api/buscar-vehiculo?q=' + encodeURIComponent(q))
          .then(function(r) { return r.json(); })
          .then(function(data) {
            if (searchInput.value.trim().length >= 2) abrirDropdown(data);
          })
          .catch(function() { cerrarDropdown(); });
      }, 280);
    });

    searchInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        var q = searchInput.value.trim();
        if (!q) return;
        var first = searchDd.querySelector('li:not(.no-result)');
        if (first) {
          window.location.href = '/equipo/' + encodeURIComponent(first.textContent);
        } else if (q.length >= 2) {
          window.location.href = '/equipo/' + encodeURIComponent(q.toUpperCase());
        }
      }
      if (e.key === 'Escape') cerrarDropdown();
    });

    searchInput.addEventListener('blur', function() {
      setTimeout(cerrarDropdown, 180);
    });

    document.addEventListener('click', function(e) {
      if (!searchInput.contains(e.target) && !searchDd.contains(e.target)) {
        cerrarDropdown();
      }
    });
  })();
  </script>
```

- [ ] **Step 4: Verificar en navegador**

```bash
python app.py
# Navegar a cualquier página con el topbar
# Escribir 2+ caracteres en el campo de búsqueda de la navbar
# Debe aparecer dropdown con sugerencias de vehículos
# Enter en una sugerencia → navegar a /equipo/<vehiculo>
# En móvil (<768px): campo de búsqueda oculto (solo en desktop)
```

- [ ] **Step 5: Commit final**

```bash
git add templates/base.html
git commit -m "feat: busqueda global con autocomplete en navbar"
```

---

## Self-Review

**Spec coverage check:**

| Requisito | Task que lo implementa |
|-----------|----------------------|
| Badge días sin gestionar (CIO, vencidos sin solicitar) | Task 1+2 |
| Badge rojo parpadeante 3+ días | Task 2 |
| Badge amarillo 1-2 días | Task 2 |
| Solo aplica a no-solicitados | Task 1 (condición `_has_pendiente or _has_no_ej`) |
| Alertas admin encima de todo | Task 4 |
| 3 tipos de alerta + colores | Task 4 |
| Alertas clickeables con filtro | Task 3+4 (link a historial filtrado / dashboard) |
| Estado "sin alertas" en verde | Task 4 |
| Export 2 hojas | Task 5 |
| Hoja 1 Resumen Ejecutivo: KPIs, tabla familias, top motivos | Task 5 |
| Hoja 1: logo text GET-Talma, fecha generación, colores corporativos | Task 5 |
| Hoja 2 Detalle: header azul, auto-filtros, freeze panes | Task 5 |
| Timeline visual en /equipo/<vehiculo> | Task 6+7 |
| Puntos de color (verde/rojo/azul) en timeline | Task 7 |
| Estadísticas del vehículo (total, ejecutado, no ej, %) | Task 6+7 |
| Búsqueda en navbar visible para todos los roles | Task 8 |
| Dropdown sugerencias con 2+ chars | Task 8 |
| API /api/buscar-vehiculo | Task 7 |
| Búsqueda parcial | Task 7 |
| Responsive | Tasks 2, 4, 8 incluyen media queries |
| Zero CDN | Verificado — todo CSS/JS embebido |

**Placeholder scan:** Ninguno encontrado. Todos los pasos tienen código concreto.

**Type consistency:** 
- `dias_sin_gestionar` es `int` (0 si no aplica) — consistente en Task 1 y 2
- `hist_stats` es dict con claves `total`, `ejecutados`, `no_ejecutados`, `pendientes`, `pct_ejecucion` — consistente en Task 6 y 7
- `/api/buscar-vehiculo` retorna `jsonify(list[str])` — consistente en Task 7 y 8
- `alerta_vencidos`, `alerta_pendientes`, `alerta_no_ej` son `int` — consistente en Tasks 3 y 4
